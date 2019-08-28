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
"""This file contains implementations of various compression algorithms."""

from utils import *


class CompressionAlgorithm(object):

    def __init__(self, name, archive_extension, compress_method, short_name,
                 sorting_priority):
        self.name = name
        self.archive_extension = archive_extension
        self.compress_method = compress_method
        self.short_name = short_name
        self.sorting_priority = sorting_priority

    def compress(self, patch_path):
        """Compress the given file using this algorithm

    Args:
      patch_patch: path to the input file

    Returns:
      path to the compressed file
    """
        return self.compress_method(patch_path)


def gzip(patch_path):
    """Gzips the file on patch_path.

  Args:
    patch_path: path to the input file

  Returns:
    path to the gzipped input file
  """
    check_exists(patch_path)
    gzip_path = find_binary("gzip")
    in_file = open(patch_path, 'r')

    gzipped_path = patch_path + ".gz"
    out_file = open(gzipped_path, 'w')
    run_command([gzip_path, '-9'], stdin=in_file, stdout=out_file)
    in_file.close()
    out_file.close()
    return gzipped_path


def brotli(patch_path):
    """Compresses the given file using BROTLI"""
    compressed_patch_path = patch_path + ".br"
    brotli_path = find_binary("brotli")
    cleanup(compressed_patch_path)
    check_exists(patch_path)
    run_command([brotli_path, '-9', patch_path])
    return compressed_patch_path


def no_compress(file):
    """No-op compression algorithm that returns a copy of input file."""
    check_exists(file)
    new_file = file + ".copy"
    run_command(["cp", file, new_file])
    return new_file


def get_compression_algorithms(compressions=None):
    all = [
        CompressionAlgorithm(
            name="Identity",
            short_name="identity",
            archive_extension=".identity",
            compress_method=no_compress,
            sorting_priority=0),
        CompressionAlgorithm(
            name="GZIP",
            short_name="gzip",
            archive_extension=".gzip",
            compress_method=gzip,
            sorting_priority=1),
        CompressionAlgorithm(
            name="BROTLI",
            short_name="brotli",
            archive_extension=".brotli",
            compress_method=brotli,
            sorting_priority=2)
    ]

    if compressions is None:
        return all

    return filter(lambda algo: algo.short_name in compressions, all)
