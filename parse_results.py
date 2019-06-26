import argparse
import csv
import re
import sys


def extract_projects(file):
    projects = {}
    log_file = open(args.file, 'r')
    title_pattern = re.compile("===== (.*) =====")
    title = None
    for line in log_file:
        if title_pattern.match(line):
            title = title_pattern.match(line).group(1)
            if title == "TOTAL":
                title = None
                continue
            elif title in projects:
                raise Exception("{} is duplicated".format(title))
            projects[title] = {}
        elif "Downloads" in line:
            continue
        elif line.startswith("| ") and title:
            line = line.split("|")
            key = line[1].lstrip().rstrip()
            value = int(line[2])
            projects[title][key] = value
        elif line.startswith("TOTAL:") and title:
            line = line.split("TOTAL:")
            value = int(line[1])
            projects[title]["Total"] = value
    return projects


if __name__ == "__main__":
    argparse = argparse.ArgumentParser()
    argparse.add_argument("file")
    args = argparse.parse_args()

    expected_keys = ["Packages","x86_64", "x86", "armv7", "armv7hf", "Visual Studio 12", "Visual Studio 14",
                     "Visual Studio 15", "Visual Studio 16", "apple-clang 10.0", "apple-clang 7.3",
                     "apple-clang 8.0", "apple-clang 8.1", "apple-clang 9.0", "apple-clang 9.1",
                     "clang 3.9", "clang 4.0", "clang 5.0", "clang 6.0", "clang 7.0", "clang 8",
                     "gcc 4.6", "gcc 4.8", "gcc 4.9", "gcc 5", "gcc 6", "gcc 6.3", "gcc 7",
                     "gcc 7.1", "gcc 8", "gcc 9", "Linux", "Macos", "Windows", "Total"]

    csv_file = open("downloads.csv", 'w')
    writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(expected_keys)
    expected_keys.pop(0)

    projects = extract_projects(args.file)
    for project, attributes in projects.items():
        row = [project]
        for expected_key in expected_keys:
            if expected_key not in attributes:
                row.append(0)
            else:
                row.append(attributes[expected_key])
        writer.writerow(row)
