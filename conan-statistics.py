#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import magic
import os
import sys
import requests
import logging
import gzip
import glob
import time
import datetime
import time
import pandas
import tempfile
import ntplib
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
from selenium.common.exceptions import NoSuchElementException
from bintray.bintray import Bintray


TOTAL_DOWNLOADS = 0
IP_ADDRESSES = []
TOTAL_ARCH = defaultdict(int)
TOTAL_COMPILER = defaultdict(int)
TOTAL_OS = defaultdict(int)
TOTAL_CLIENT = defaultdict(int)
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


def paginate_recipe_list(recipe_list):
    total_pages = int(os.getenv("CONAN_TOTAL_PAGES", 0))
    current_page = int(os.getenv("CONAN_CURRENT_PAGE", 0))
    if total_pages and current_page:
        names = set()
        for recipe in recipe_list:
            conan_ref = ConanFileReference.loads(recipe)
            names.add(conan_ref.name)

        names = list(names)
        avg = len(names) / float(total_pages)
        chunks = []
        last = 0.0
        while last < len(names):
            chunks.append(names[int(last):int(last + avg)])
            last += avg
        chunk = chunks[current_page - 1]

        filtered_list = []
        for name in chunk:
            for recipe in recipe_list:
                if name in recipe:
                    filtered_list.append(recipe)
        recipe_list = filtered_list
    return recipe_list


def filter_recipe_list_by_name(recipe_list):
    recipes = defaultdict(list)
    recipe_list = paginate_recipe_list(recipe_list)
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
        # [{'recipe': {'id': 'protobuf/3.6.1@bincrafters/stable'}, 'packages' ...F
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

    print("TOTAL: {}\n".format(TOTAL_DOWNLOADS))

    print(TOTAL_ARCH)
    print(TOTAL_COMPILER)
    print(TOTAL_OS)


def upload_total_statistics():
    total_address = defaultdict(int)
    for address in IP_ADDRESSES:
        total_address[get_ip_owner(address)] += 1

    total = [
        TOTAL_ARCH,
        TOTAL_COMPILER,
        TOTAL_OS,
        total_address,
        {"total": TOTAL_DOWNLOADS},
    ]

    today = datetime.date.today()
    date = today.strftime("%Y%m%d")
    client = ntplib.NTPClient()
    response = client.request('pool.ntp.org')
    now = time.strftime('%H%M%S',time.localtime(response.tx_time)
    job = os.getenv("CIRCLE_JOB", now)
    filename = "statistics-{}_{}.json".format(date, job)

    with open(filename, 'w') as outfile:
        json.dump(total, outfile)

    upload_file(filename)


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
    retry_limit = 10
    while True:
        retry = 0
        browser.get(login_url)
        browser_title = browser.title
        browser.find_element_by_id("username").send_keys(username)
        browser.find_element_by_id("password").send_keys(password)
        browser.find_element_by_class_name("btn").click()

        while browser_title == browser.title:
            time.sleep(1)
            retry += 1
            if retry == retry_limit:
                break

        if browser_title != browser.title:
            break

    return browser


def download_file(browser, url):
    while True:
        url_path = os.path.join("/tmp", url)
        if os.path.exists(url_path):
            os.remove(url_path)

        while True:
            try:
                browser.find_element_by_link_text(url).click()
                break
            except NoSuchElementException:
                browser.refresh()
                WebDriverWait(browser, 60).until(EC.presence_of_element_located((By.LINK_TEXT, 'Download Logs'))).click()

        # wait for download
        while not os.path.exists(url_path):
            time.sleep(1)
        while os.path.exists(url_path + ".crdownload"):
            time.sleep(1)
        while os.path.exists(url_path + ".part"):
            time.sleep(1)
        if magic.from_file(url_path, mime=True) == 'application/gzip':
            break


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
            href = link.attrs['href']
            # extract file name
            url = href[href.rfind('=') + 1:]
            download_file(browser, url)
            with gzip.open(os.path.join("/tmp", url), 'rb') as gzip_file:
                content = gzip_file.read()
                with open("temp.csv", 'wb') as temp_csv:
                    temp_csv.write(content)
                values = content.decode().split(',')
                # filter only package download
                values = [value for value in values if "conan_package.tgz" in value]
                for value in values:
                    # /bincrafters/public-conan/bincrafters/protobuf/3.5.1/stable/0/package/8cf01e2f50fcd6b63525e70584df0326550364e1/0/conan_package.tgz
                    value = value.split('/')
                    version = value[5]
                    package_id = value[9]
                    packages[version][package_id] = packages[version].get(package_id, 0) + 1
                global IP_ADDRESSES
                IP_ADDRESSES = collect_ips("temp.csv")

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


def get_ip_owner(ip_address):
    appveyor = ["67.225.164.53", "67.225.164.54", "67.225.164.96", "67.225.165.66", "67.225.165.168", "67.225.165.171",
                "67.225.165.175", "67.225.165.183", "67.225.165.185", "67.225.165.193", "67.225.165.198",
                "67.225.165.200", "104.197.110.30", "104.197.145.181", "34.208.156.238", "34.209.164.53",
                "34.216.199.18", "52.43.29.82", "52.89.56.249", "54.200.227.141", "13.83.108.89", "138.91.141.243"]
    travis = ["207.254.16.35", "207.254.16.36", "207.254.16.37", "207.254.16.38", "207.254.16.39", "34.66.178.120",
              "34.68.144.114", "35.184.96.71", "35.184.226.236", "35.188.1.99", "35.188.73.34", "35.192.85.2",
              "35.192.136.167", "35.192.187.174", "35.193.7.13", "35.193.14.140", "35.202.145.110", "35.224.112.202",
              "104.154.113.151", "104.154.120.187", "104.198.131.58", "34.66.178.120", "34.68.144.114", "35.184.96.71",
              "35.184.226.236", "35.188.1.99", "35.188.73.34", "35.192.85.2", "35.192.136.167", "35.192.187.174",
              "35.193.7.13", "35.193.14.140", "35.202.145.110", "35.224.112.202", "104.154.113.151", "104.154.120.187",
              "104.198.131.58"]
    if ip_address in appveyor:
        return "Appveyor"
    elif ip_address in travis:
        return "Travis"
    else:
        return "Unknown"


def upload_file(file):
    remote = os.getenv("BINTRAY_REMOTE")
    username = os.getenv("BINTRAY_USERNAME")
    apikey = os.getenv("BINTRAY_API_KEY")
    if not username or not apikey or not remote:
        logging.error("Could not upload. Login missing")
        return

    subject, repo, package = remote.split('/')
    bintray = Bintray()
    today = datetime.date.today()
    version = today.strftime("%Y%m%d")
    basename = os.path.basename(file)
    try:
        logging.info("Uploading {}".format(basename))
        bintray.upload_content(subject, repo, package, version, basename, file, override=True)
        logging.info("Done!")
    except Exception as error:
        logging.error(str(error))


def collect_ips(file):
    data = pandas.read_csv(file)
    return data.ip_address


if __name__ == "__main__":
    browser = None
    try:
        logging.info("Retrieve all recipes from Conan center")
        official_recipes = get_recipe_list_from_bintray()
        # {"protobuf": ["protobuf/1.3.6@bincrafers/stable", ...], ...}
        official_recipes = filter_recipe_list_by_name(official_recipes)
        logging.info("Recipes to be analyzed({}): {}".format(len(official_recipes.keys()), official_recipes.keys()))
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
        upload_total_statistics()
    finally:
        if browser:
            browser.quit()
