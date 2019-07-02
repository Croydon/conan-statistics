#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import datetime
import json
from bintray.bintray import Bintray


def get_file_list():
    bintray = Bintray()
    remote = os.getenv("BINTRAY_REMOTE")
    subject, repo, package = remote.split('/')
    return bintray.get_package_files(subject, repo, package)


def filter_file_list(files):
    today = datetime.date.today()
    version = today.strftime("%Y%m%d")
    filtered_list = []
    for file in files:
        if file.get("version") == version and \
           ".json" in file.get("name") and \
           "statistics-total" not in file.get("name"):
            filtered_list.append(file)
    return filtered_list


def download_files(files):
    bintray = Bintray()
    remote = os.getenv("BINTRAY_REMOTE")
    subject, repo, package = remote.split('/')
    for file in files:
        file_path = file.get("path")
        file_name = file.get("name")
        bintray.download_content(subject, repo, file_path, file_name)


def merge_files(files):
    total = {}
    for file in files:
        name = file.get("name")
        with open(name, 'rb') as json_fd:
            json_content = json.load(json_fd)
            total = {k: total.get(k, 0) + json_content.get(k, 0) for k in set(total) | set(json_content)}
    today = datetime.date.today()
    version = today.strftime("%Y%m%d")
    file_name = "statistics-total-{}.json".format(version)
    with open(file_name, 'w') as json_file:
        json.dump(total, json_file)
    return file_name


def upload_file(file):
    remote = os.getenv("BINTRAY_REMOTE")
    subject, repo, package = remote.split('/')
    bintray = Bintray()
    today = datetime.date.today()
    version = today.strftime("%Y%m%d")
    basename = os.path.basename(file)
    bintray.upload_content(subject, repo, package, version, basename, file, override=True)


if __name__ == "__main__":
    files = get_file_list()
    filtered_files = filter_file_list(files)
    download_files(filtered_files)
    total_path = merge_files(filtered_files)
    upload_file(total_path)
