#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import time
import os
import requests
import logging
import selenium
import gzip
import csv

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
from selenium.webdriver.firefox.options import Options
from conans.client import conan_api

FORMAT = '%(asctime)-15s: %(message)s'
logging.basicConfig(format=FORMAT, level=logging.DEBUG)


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
    browser.get("https://bintray.com/{}/{}/{}%3A{}#statistics".format(subject, repo, package, user))
    WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.LINK_TEXT, 'Download Logs'))).click()
    soup = BeautifulSoup(browser.page_source, 'html.parser')
    packages = {}
    for link in soup.find_all('a'):
        if "href" in link.attrs and "csv.gz" in link.attrs['href']:
            url = "https://bintray.com" + link.attrs['href']
            logging.info("Downloading %s" % url)
            href = link.attrs['href']
            url = href[href.rfind('=')+1:]
            browser.find_element_by_link_text(url).click()
            with gzip.open(os.path.join("/tmp", url), 'rb') as gzip_file:
                values = gzip_file.read().decode().split(',')
                values = [value for value in values if "conan_package.tgz" in value]
                for value in values:
                    logging.info("VALUE %s" % value)
                    key = "package/"
                    key_len = len(key)
                    pos = value.find(key)
                    package_id = value[pos + key_len:value.find('/', pos + key_len)]
                    logging.info("PACKAGE ID: %s" % package_id)
                    if packages.get(package_id) is None:
                        packages[package_id] = 1
                    else:
                        packages[package_id] = packages[package_id] + 1
                    print(packages)
            break
    return packages


if __name__ == "__main__":
    browser = create_browser()
    try:
        browser = login(browser)
        packages = get_package_logs(browser, "bincrafters", "public-conan", "protobuf", "bincrafters")
        json_data = json.dumps(packages)
        with open("packages.json", "w") as json_file:
            json_file.write(json_data)
    finally:
        if browser:
            browser.quit()
