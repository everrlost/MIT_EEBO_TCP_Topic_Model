#!/usr/bin/env python3
"""
Build a CSV of (document, year) from a folder of files.
Linear version - no multiprocessing.

Usage:
    python date_extractor.py <input_folder> <output.csv>
"""

import csv
import os
import re
import sys

DATE_RE = re.compile(r"<date>.*?(\d{4}).*?</date>", re.IGNORECASE | re.DOTALL)


def process_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return None

    match = DATE_RE.search(text)
    if not match:
        return None

    document = os.path.splitext(os.path.basename(path))[0]
    return (document, match.group(1))


def main():
    if len(sys.argv) != 3:
        print("Usage: python date_extractor.py <input_folder> <output.csv>")
        sys.exit(1)

    input_folder, output_csv = sys.argv[1], sys.argv[2]

    paths = [
        os.path.join(input_folder, name)
        for name in os.listdir(input_folder)
        if os.path.isfile(os.path.join(input_folder, name))
    ]
    total = len(paths)
    found = 0

    with open(output_csv, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["document", "year"])

        for i, path in enumerate(paths, 1):
            row = process_file(path)
            if row is not None:
                writer.writerow(row)
                found += 1

            if i % 50 == 0 or i == total:
                pct = i / total * 100
                print(f"\rProcessed {i}/{total} ({pct:5.1f}%)  |  dates found: {found}",
                      end="", flush=True)

    print(f"\nDone. {found}/{total} files had a date -> {output_csv}")


if __name__ == "__main__":
    main()