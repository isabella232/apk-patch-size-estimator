#!/usr/bin/python
#
# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Estimates the size of Google Play patches in all formats.

From two APKs it estimates the size of new patches produced by combinations of
delta and compression algorithms. Google Play uses multiple techniques to
generate patches and generally picks the best match for the device. The best
match is usually, but not always, the smallest patch file produced. The numbers
that this script produces are ESTIMATES that can be used to characterize the
impact of arbitrary changes to APKs. There is NO GUARANTEE that this tool
produces the same patches or patch sizes that Google Play generates, stores or
transmits, and the actual implementation within Google Play may change at any
time, without notice.
"""

from __future__ import unicode_literals
import logging
import sys
import argparse
import locale
import math
import os
import subprocess
import zipfile
from utils import *
from compression import *
from delta import *
from collections import namedtuple

Args = namedtuple('Args', [
    "old_file", "new_file", "save_patch", "temp_path", "compressions", "deltas",
    "csv_file"
])


def collect_data(args):
    old_file = args.old_file
    new_file = args.new_file
    save_patch = args.save_patch
    temp_path = args.temp_path
    compressions = args.compressions
    deltas = args.deltas

    temp_path = os.path.join(temp_path, "apk-path-size-estimator")
    create_temp_dir(temp_path)

    diffs = get_delta_algorithms(deltas)
    compressions = get_compression_algorithms(compressions)

    logger.info("Using delta algorithms: %s" %
                (",".join([x.name for x in diffs])))
    logger.info("Using compression algorithms: %s" %
                (','.join([x.name for x in compressions])))

    data = {}

    for diff in diffs:
        delta_path = diff.compute_delta(old_file, new_file, temp_path)
        data[diff.name] = {}
        for compress in compressions:
            compressed_path = compress.compress(delta_path)
            patch_size = get_size(compressed_path)
            data[diff.name][compress.name] = patch_size

            if save_patch:
                run_command([
                    "cp", compressed_path, save_patch +
                    diff.patch_file_extension + compress.archive_extension
                ])

    remove_dir_if_exist(temp_path)

    return data


def print_table(data):
    all_diff_name_in_order = ["Identity", "BSDIFF", "File-By-File-V1"] + ["fbfv2-stripped", "fbfv2"]
    diff_name_in_order = []
    for diff_name in all_diff_name_in_order:
      if diff_name in data:
        diff_name_in_order.append(diff_name)
    compression_name_in_order = ["Identity", "BROTLI"]
    column_width = max(map(len, diff_name_in_order)) + 5

    print("".join(
        [x.ljust(column_width) for x in [""] + compression_name_in_order]))
    for diff_name in diff_name_in_order:
        row = diff_name.ljust(column_width)
        for compression_name in compression_name_in_order:
            patch_size = data[diff_name][compression_name]
            row += human_file_size(patch_size).ljust(column_width)
        print row


def print_csv(data, args):
    target = sys.stdout
    if args.csv_file:
        target = open(args.csv_file, "w")

    for diff_name in data:
        for compression_name in data[diff_name]:
            patch_size = data[diff_name][compression_name]
            target.write(','.join([
                args.old_file, args.new_file, diff_name, compression_name,
                str(patch_size),
                human_file_size(patch_size)
            ]) + "\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description='Estimate the sizes of APK patches for Google Play')
    parser.add_argument(
        '--old-file',
        default=None,
        required=True,
        help='the path to the "old" file to generate patches from.')
    parser.add_argument(
        '--new-file',
        default=None,
        required=True,
        help='the path to the "new" file to generate patches from.')
    parser.add_argument(
        '--save-patch',
        default=None,
        help='the path prefix to save the generated patches.')
    parser.add_argument(
        '--temp-path',
        default='/tmp',
        help='the temp directory to use for patch generation; defaults to /tmp')
    parser.add_argument(
        '--deltas',
        default=None,
        help='limit the number of delta algorithms used; defaults to "%s"' %
        (','.join([algo.short_name for algo in get_delta_algorithms()])))
    parser.add_argument(
        '--compressions',
        default=None,
        help='limit the number of compression algorithms used; defaults to "%s"'
        %
        (','.join([algo.short_name for algo in get_compression_algorithms()])))
    parser.add_argument(
        '--csv-file',
        default=None,
        help=
        'target csv file to write to; if none is given, will print to STDOUT')
    if not sys.argv[1:]:
        parser.print_help()
        parser.exit()
    args = parser.parse_args()

    return Args(
        old_file=args.old_file,
        new_file=args.new_file,
        save_patch=args.save_patch,
        temp_path=args.temp_path,
        deltas=args.deltas,
        compressions=args.compressions,
        csv_file=args.csv_file)


def validate_args(args):
    check_exists(args.old_file, args.new_file)
    if args.save_patch and not os.access(
            os.path.dirname(os.path.abspath(args.save_patch)), os.W_OK):
        raise Exception(
            'The save patch path is not writable: %s' % args.save_patch)
    if args.save_patch and os.path.isdir(args.save_patch):
        raise Exception(
            'Please include the filename in the path: %s' % args.save_patch)
    if not os.path.isdir(args.temp_path):
        raise Exception('Temp directory does not exist: %s' % args.temp_path)

    if args.deltas:
        all_deltas = map(lambda x: x.short_name, get_delta_algorithms())
        for d in args.deltas.split(','):
            if d not in all_deltas:
                raise Exception('Unrecognized delta "%s". Choices are "%s"' %
                                (d, ",".join(all_deltas)))
    if args.compressions:
        all_compressions = map(lambda x: x.short_name,
                               get_compression_algorithms())
        for d in args.compressions.split(','):
            if d not in all_compressions:
                raise Exception(
                    'Unrecognized compression "%s". Choices are "%s"' %
                    (d, ",".join(all_compressions)))


if __name__ == '__main__':
    locale.setlocale(locale.LC_ALL, '')
    args = parse_args()
    validate_args(args)
    data = collect_data(args)
    print_table(data)
    # print_csv(data, args)
