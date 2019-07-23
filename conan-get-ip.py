#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import tempfile
import gzip
import shutil
from bisect import bisect_left
import pandas
import humanfriendly
import json
from datetime import datetime
from ipaddress import IPv4Address, IPv4Network
from bintray.bintray import Bintray


TOTAL_FRAMES = []
PROVIDERS = None


def uncompress(src, dst):
    with open(dst, "wb") as fd_dst:
        with gzip.open(src, "rb") as fd_src:
            bindata = fd_src.read()
            fd_dst.write(bindata)


def compress(file_name):
    file_gz = file_name + '.gz'
    with open(file_name, "rb") as f_in:
        with gzip.open(file_gz, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    return file_gz


def load_providers():
    global PROVIDERS
    with open("providers.json") as json_file:
        PROVIDERS = json.load(json_file)


def get_provider(ip_address):
    for provider, ips in PROVIDERS.items():
        index = bisect_left(ips, ip_address)
        if index != len(ips) and ips[index] == ip_address:
            return provider

        if provider == "Azure" or provider == "Amazon":
            for prefix_ip in ips:
                if IPv4Address(ip_address) in IPv4Network(prefix_ip):
                    return provider

    return "Unknown"


def show_quota(bintray, organization):
    response = bintray.get_organization(organization)
    print("Organization quota: {}".format(organization))
    print("Free Storage: {}".format(humanfriendly.format_size(response["free_storage"])))
    print("Quota Used: {}".format(humanfriendly.format_size(response["quota_used_bytes"])))
    print("Free Storage Quota Limit: {}".format(humanfriendly.format_size(response["free_storage_quota_limit"])))
    print("Last Month Free Downloads: {}".format(humanfriendly.format_size(response["last_month_free_downloads"])))
    print("Monthly Free Downloads Quota Limit: {}".format(humanfriendly.format_size(response["monthly_free_downloads_quota_limit"])))


def today():
    return datetime.now().strftime("%d-%m-%Y")


def show_total():
    pd_block = pandas.concat(TOTAL_FRAMES, axis=0, ignore_index=True)
    size = len(pd_block.index)
    print("=== TOTAL ===")
    print("Downloads Total: {}".format(size))
    #print("Providers: {}".format(pd_block.pivot_table(index=['provider'], aggfunc='size')))
    print("Countries: {}".format(pd_block.pivot_table(index=['country'], aggfunc='size')))
    print("IPs: {}".format(pd_block.pivot_table(index=['ip_address'], aggfunc='size')))
    file_name = "conan-center-{}.csv.gz".format(today())
    pd_block.to_csv(file_name, index=False, compression='gzip')
    return file_name


def show_package_downloads(bintray, organization, repo, package):
    try:
        global TOTAL_FRAMES
        to_be_downloaded = []
        print("Package {}".format(package))
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
                pd_frame.insert(1, 'package', package)
                #pd_frame.insert(2, 'provider', "Unknown")
                for index, row in pd_frame.iterrows():
                    pd_frame.at[index, 'path_information'] = os.path.basename(row.path_information)
                pd_list.append(pd_frame)
                TOTAL_FRAMES.append(pd_frame)
            pd_block = pandas.concat(pd_list, axis=0, ignore_index=True)
            pd_block.sort_values(by='date')

            #for ip, count in pd_block.pivot_table(index=['ip_address'], aggfunc='size').items():
            #    provider = get_provider(ip)
            #    pd_block.loc[pd_block.ip_address == ip, 'provider'] = provider

            size = len(pd_block.index)

            print("Package: {}".format(package))
            print("Downloads Total: {}".format(size))
            print("Date range {} - {}".format(pd_block.at[0, "date"], pd_block.at[size-1, "date"]))
            #print("Providers: {}".format(pd_block.pivot_table(index=['provider'], aggfunc='size')))
            print("Countries: {}".format(pd_block.pivot_table(index=['country'], aggfunc='size')))
            print("IPs: {}".format(pd_block.pivot_table(index=['ip_address'], aggfunc='size')))
    except:
        pass


def upload_file():
    pass


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
    packages = get_packages(bintray, "conan", "conan-center")
    for package in packages:
        name = package.get("name") or ""
        if ":conan" in name:
            show_package_downloads(bintray, "conan-community", "conan", name)
        elif ":bincrafters" in name:
            show_package_downloads(bintray, "bincrafters", "public-conan", name)
    file_name = show_total()
    bintray.upload_content("uilianries", "generic", "statistics", today(), file_name, file_name,
                           override=True)
