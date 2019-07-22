#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import tempfile
import gzip
import pandas
import humanfriendly
import json
from datetime import datetime
from ipaddress import IPv4Address, IPv4Network
from bintray.bintray import Bintray


TOTAL_FRAMES = []


def uncompress(src, dst):
    with open(dst, "wb") as fd_dst:
        with gzip.open(src, "rb") as fd_src:
            bindata = fd_src.read()
            fd_dst.write(bindata)


def get_provider(ip_address):
    providers = {
        # https://docs.travis-ci.com/user/ip-addresses/
        "Travis": [
            "104.154.113.151",
            "104.154.120.187",
            "104.198.131.58",
            "207.254.16.35",
            "207.254.16.36",
            "207.254.16.37",
            "207.254.16.38",
            "207.254.16.39",
            "34.66.178.120",
            "34.66.200.49",
            "34.66.25.221",
            "34.66.50.208",
            "34.68.144.114",
            "35.184.226.236",
            "35.184.96.71",
            "35.188.1.99",
            "35.188.73.34",
            "35.192.136.167",
            "35.192.187.174",
            "35.192.85.2",
            "35.193.14.140",
            "35.193.7.13",
            "35.202.145.110",
            "35.202.245.105",
            "35.224.112.202"
        ],
        # https://www.appveyor.com/docs/build-environment/?origin_team=T2QUFRG2E#ip-addresses
        "Appveyor": [
            "104.197.110.30",
            "104.197.145.181",
            "67.225.164.53",
            "67.225.164.54",
            "67.225.164.96",
            "67.225.165.66",
            "67.225.165.168",
            "67.225.165.171",
            "67.225.165.175",
            "67.225.165.183",
            "67.225.165.185",
            "67.225.165.193",
            "67.225.165.198",
            "67.225.165.200",
            "34.208.156.238",
            "34.209.164.53",
            "34.216.199.18",
            "52.43.29.82",
            "52.89.56.249",
            "54.200.227.141",
            "13.83.108.89",
            "138.91.141.243"
        ]

    }
    for provider, ips in providers.items():
        if ip_address in ips:
            return provider

    with open('amazon_ip_range.json') as json_file:
        json_data = json.load(json_file)
        for prefix in json_data["prefixes"]:
            if ip_address in prefix["ip_prefix"] or \
               IPv4Address(ip_address) in IPv4Network(prefix["ip_prefix"]):
                return "Amazon (CircleCI)"

    with open('azure_ip_range.json') as json_file:
        json_data = json.load(json_file)
        for prefix in json_data["values"]:
            for address_prefix in prefix["properties"]["addressPrefixes"]:
                if ip_address in address_prefix or \
                   IPv4Address(ip_address) in IPv4Network(address_prefix):
                    return "Azure"

    return "Unknown"


def show_quota(bintray, organization):
    response = bintray.get_organization(organization)
    print("Organization quota: {}".format(organization))
    print("Free Storage: {}".format(humanfriendly.format_size(response["free_storage"])))
    print("Quota Used: {}".format(humanfriendly.format_size(response["quota_used_bytes"])))
    print("Free Storage Quota Limit: {}".format(humanfriendly.format_size(response["free_storage_quota_limit"])))
    print("Last Month Free Downloads: {}".format(humanfriendly.format_size(response["last_month_free_downloads"])))
    print("Monthly Free Downloads Quota Limit: {}".format(humanfriendly.format_size(response["monthly_free_downloads_quota_limit"])))


def show_total():
    pd_block = pandas.concat(TOTAL_FRAMES, axis=0, ignore_index=True)
    size = len(pd_block.index)
    print("Downloads Total: {}".format(size))
    print("Providers: {}".format(pd_block.pivot_table(index=['provider'], aggfunc='size')))
    print("Countries: {}".format(pd_block.pivot_table(index=['country'], aggfunc='size')))


def show_package_downloads(bintray, organization, repo, package):
    global TOTAL_FRAMES
    to_be_downloaded = []
    response = bintray.get_list_package_download_log_files(organization, repo, package)
    for log in response:
        if "name" in log and "csv.gz" in log["name"]:
            to_be_downloaded.append(log["name"])

    if to_be_downloaded:
        temp_folder = tempfile.mkdtemp(package, organization)
        pd_list = []
        for file in to_be_downloaded:
            local_name = os.path.join(temp_folder, file)
            dst_name = local_name[:-3]
            bintray.download_package_download_log_file(organization, repo, package, file, local_name)
            uncompress(local_name, dst_name)
            usecols = ['ip_address', 'country', 'path_information']
            pd_frame = pandas.read_csv(dst_name, usecols=usecols)
            date = os.path.basename(dst_name)[10:-4]
            date = datetime.strptime(date, '%d-%m-%Y')
            pd_frame.insert(0, 'date', date)
            pd_frame.insert(2, 'provider', "Unknown")
            for index, row in pd_frame.iterrows():
                pd_frame.at[index, 'path_information'] = os.path.basename(row.path_information)
                pd_frame.at[index, 'provider'] = get_provider(row.ip_address)
            pd_list.append(pd_frame)
            TOTAL_FRAMES.append(pd_frame)
        pd_block = pandas.concat(pd_list, axis=0, ignore_index=True)
        pd_block.sort_values(by='date')
        size = len(pd_block.index)

        print("Package: {}".format(package))
        print("Downloads Total: {}".format(size))
        print("Date range {} - {}".format(pd_block.at[0, "date"], pd_block.at[size-1, "date"]))
        print("Providers: {}".format(pd_block.pivot_table(index=['provider'], aggfunc='size')))
        print("Countries: {}".format(pd_block.pivot_table(index=['country'], aggfunc='size')))


def get_packages(bintray, organization, repo):
    page = 0
    old_temp = None
    packages = []
    while page is not None:
        curr_temp = bintray.get_packages(organization, repo, start_pos=page)
        if not curr_temp:
            break
        if old_temp == curr_temp:
            break
        old_temp = curr_temp
        page += len(curr_temp)
        packages.extend(curr_temp)
    return packages


if __name__ == "__main__":
    bintray = Bintray()
    packages = get_packages(bintray, "conan-community", "conan")
    for package in packages:
        show_package_downloads(bintray, "conan-community", "conan", package["name"])
    show_total()
