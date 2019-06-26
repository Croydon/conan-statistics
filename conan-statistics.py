#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import time
import os
import requests
import logging
import gzip
import glob
import time
from collections import defaultdict

from tabulate import tabulate
from requests.auth import HTTPBasicAuth
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from selenium.webdriver.firefox.options import Options
from conans.client import conan_api
from conans.model.ref import ConanFileReference


TOTAL_DOWNLOADS = 0
TOTAL_ARCH = defaultdict(int)
TOTAL_COMPILER = defaultdict(int)
TOTAL_OS = defaultdict(int)
FORMAT = '%(asctime)-15s: %(message)s'
logging.basicConfig(format=FORMAT, level=logging.INFO)


def create_browser():
    profile = webdriver.FirefoxProfile()
    profile.set_preference('browser.download.folderList', 2)
    profile.set_preference('browser.download.manager.showWhenStarting', False)
    profile.set_preference('browser.download.dir', '/srv/download')
    profile.set_preference("browser.download.manager.alertOnEXEOpen", False)
    profile.set_preference("browser.download.manager.closeWhenDone", False)
    profile.set_preference("browser.download.manager.focusWhenStarting", False)
    profile.set_preference('browser.download.dir', '/tmp')
    profile.set_preference('browser.helperApps.neverAsk.saveToDisk', 'application/octet-stream')
    options = Options()
    options.headless = True
    browser = webdriver.Firefox(profile, options=options)
    return browser


def get_recipe_list_from_bintray(remote="conan-center"):
    instance, _, _ = conan_api.Conan.factory()
    packages = instance.search_recipes("*", remote_name=remote)
    return [recipe["recipe"]["id"] for recipe in packages["results"][0]["items"]]


def filter_recipe_list_by_name(recipe_list):
    recipes = defaultdict(list)
    for recipe in recipe_list:
        conan_ref = ConanFileReference.loads(recipe)
        recipes[conan_ref.name].append(conan_ref.full_repr())
    return recipes


def get_package_info_from_bintray(reference, remote="conan-center"):
    instance, _, _ = conan_api.Conan.factory()
    packages = instance.search_packages(reference, remote_name=remote)
    return packages["results"][0]["items"]


def filter_package_info_by_version(packages_from_logs, packages_from_api):
    settings = []
    # {'3.5.2': {'2bb76c9adac7b8cd7c5e3b377ac9f06934aba606': 17, ...
    # The bad
    for version in packages_from_logs.keys():
        # [{'recipe': {'id': 'protobuf/3.6.1@bincrafters/stable'}, 'packages' ...
        # The ugly
        for package in packages_from_api:
            ref = ConanFileReference.loads(package["recipe"]["id"])
            if ref.version == version:
                # The mess!
                for package_id in packages_from_logs[version].keys():
                    # binary package from conan api
                    for data in package['packages']:
                        if data['id'] == package_id:
                            data['settings']['downloads'] = packages_from_logs[version][package_id]
                            settings.append({
                                package_id: data['settings']
                            })
                            break
    return settings


def print_statistics(name, settings):
    global TOTAL_COMPILER
    global TOTAL_ARCH
    global TOTAL_OS
    global TOTAL_DOWNLOADS

    arch = defaultdict(int)
    compiler = defaultdict(int)
    os = defaultdict(int)
    total = 0
    for data in settings:
        for value in data.values():
            # in case of installer package
            arch_key = "arch_build" if "arch_build" in value else "arch"
            os_key = "os_build" if "os_build" in value else "os"

            downloads = value["downloads"]
            total += downloads
            TOTAL_DOWNLOADS += downloads

            # header-only
            if "arch" not in value and \
               "compiler" not in value and \
               "arch_build" not in value and \
               "os" not in value and \
               "os_build" not in value:
                continue

            if arch_key in value:
                arch[value[arch_key]] += downloads
                TOTAL_ARCH[value[arch_key]] += downloads

            if os_key in value:
                os[value[os_key]] += downloads
                TOTAL_OS[value[os_key]] += downloads

            if "compiler" in value:
                compiler_name = "{} {}".format(value["compiler"], value["compiler.version"])
                compiler[compiler_name] += downloads
                TOTAL_COMPILER[compiler_name] += downloads

    print("===== %s =====" % name.upper())
    generic_list = []
    for key, value in arch.items():
        generic_list.append([key, value])
    if generic_list:
        print(tabulate(generic_list, ["Arch", "Downloads"], tablefmt="grid"))

    generic_list = []
    for key, value in compiler.items():
        generic_list.append([key, value])
    if generic_list:
        print(tabulate(generic_list, ["Compiler", "Downloads"], tablefmt="grid"))

    generic_list = []
    for key, value in os.items():
        generic_list.append([key, value])
    if generic_list:
        print(tabulate(generic_list, ["OS", "Downloads"], tablefmt="grid"))

    print("TOTAL: {}".format(total))


def print_total_statistics():
    print("===== TOTAL =====")
    generic_list = []
    for key, value in TOTAL_ARCH.items():
        generic_list.append([key, value])
    print(tabulate(generic_list, ["Arch", "Downloads"], tablefmt="grid"))

    generic_list = []
    for key, value in TOTAL_COMPILER.items():
        generic_list.append([key, value])
    print(tabulate(generic_list, ["Compiler", "Downloads"], tablefmt="grid"))

    generic_list = []
    for key, value in TOTAL_OS.items():
        generic_list.append([key, value])
    print(tabulate(generic_list, ["OS", "Downloads"], tablefmt="grid"))

    print("TOTAL: {}".format(TOTAL_DOWNLOADS))


def get_recipe_list_from_file(file_path):
    with open(file_path, "r") as json_file:
        data = json.load(json_file)
        return [recipe["recipe"]["id"] for recipe in data["results"][0]["items"]]


def login(browser):
    username = os.getenv("BINTRAY_USERNAME")
    password = os.getenv("BINTRAY_PASSWORD")
    if not username or not password:
        raise Exception("Login failed! BINTRAY_USERNAME and BINTRAY_PASSWORD must be configured!")

    login_url = "https://bintray.com/login?forwardedFrom=%2F"
    browser.get(login_url)
    browser_title = browser.title
    browser.find_element_by_id("username").send_keys(username)
    browser.find_element_by_id("password").send_keys(password)
    browser.find_element_by_class_name("btn").click()

    while browser_title == browser.title:
        time.sleep(1)

    return browser


def get_package_logs(browser, subject, repo, package, user):
    # remove temporary files
    for gz_file in glob.glob(os.path.join("/tmp", "*.csv.gz")):
        os.remove(gz_file)
    browser.get("https://bintray.com/{}/{}/{}%3A{}#statistics".format(subject, repo, package, user))
    WebDriverWait(browser, 60).until(
        EC.presence_of_element_located((By.LINK_TEXT, 'Download Logs'))).click()
    soup = BeautifulSoup(browser.page_source, 'html.parser')
    packages = defaultdict(dict)
    for link in soup.find_all('a'):
        # look for csv files on statistics page
        if "href" in link.attrs and "csv.gz" in link.attrs['href']:
            url = "https://bintray.com" + link.attrs['href']
            href = link.attrs['href']
            # extract file name
            url = href[href.rfind('=') + 1:]
            browser.find_element_by_link_text(url).click()
            # wait for download
            while not os.path.exists(os.path.join("/tmp", url)):
                time.sleep(1)
            while os.path.exists(os.path.join("/tmp", url + ".crdownload")):
                time.sleep(1)
            while os.path.exists(os.path.join("/tmp", url + ".part")):
                time.sleep(1)
            with gzip.open(os.path.join("/tmp", url), 'rb') as gzip_file:
                values = gzip_file.read().decode().split(',')
                # filter only package download
                values = [value for value in values if "conan_package.tgz" in value]
                for value in values:
                    # /bincrafters/public-conan/bincrafters/protobuf/3.5.1/stable/0/package/8cf01e2f50fcd6b63525e70584df0326550364e1/0/conan_package.tgz
                    value = value.split('/')
                    version = value[5]
                    package_id = value[9]
                    packages[version][package_id] = packages[version].get(package_id, 0) + 1
    return packages


def get_package_owner_repo(reference):
    username = os.getenv("BINTRAY_USERNAME")
    apikey = os.getenv("BINTRAY_API_KEY")
    if not username or not apikey:
        raise Exception("Login failed! BINTRAY_USERNAME and BINTRAY_API_KEY must be configured!")
    auth = HTTPBasicAuth(username, apikey)
    conan_ref = ConanFileReference.loads(reference)
    url = "https://api.bintray.com/packages/conan/conan-center/{}:{}".format(conan_ref.name, conan_ref.user)
    # FIXME = HTTPBasicAuth doesn't work for Bintray
    response = requests.get(url)
    if response.ok:
        return response.json()
    else:
        logging.error(response.text)
        return None


def get_allowed_owners():
    return os.getenv("BINTRAY_ALLOWED_OWNERS", "").split() if os.getenv("BINTRAY_ALLOWED_OWNERS") else ["conan-community", "bincrafters"]


if __name__ == "__main__":
    browser = None
    try:
        logging.info("Retrieve all recipes from Conan center")
        official_recipes = get_recipe_list_from_bintray()
        # {"protobuf": ["protobuf/1.3.6@bincrafers/stable", ...], ...}
        official_recipes = filter_recipe_list_by_name(official_recipes)
        # for each package name
        for key, values in official_recipes.items():
            # First package reference
            conan_ref = ConanFileReference.loads(values[0])
            # Retrieve linked repo name which is pointed by Conan center
            json_data = get_package_owner_repo(conan_ref.full_repr())
            if not json_data:
                continue
            # We can't retrieve statistics from any user
            if json_data["owner"] not in get_allowed_owners():
                continue
            logging.info("Bintray Browser login")
            browser = create_browser()
            browser = login(browser)
            logging.info("Retrieve all logs for package %s" % key)
            packages = get_package_logs(browser, json_data["owner"], json_data["repo"], conan_ref.name, conan_ref.user)
            # package settings
            settings = []
            # For each package version
            for reference in values:
                # Get package id and settings
                bintray_packages = get_package_info_from_bintray(reference)
                # Intersection between downloaded packages and package settings
                settings.extend(filter_package_info_by_version(packages, bintray_packages))
            # Print package statistics
            print_statistics(key, settings)
            browser.close()
        # Print TOTAL statistics
        print_total_statistics()
    finally:
        if browser:
            browser.quit()
