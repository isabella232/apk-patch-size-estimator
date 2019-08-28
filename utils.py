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
"""This file contains some general utilities used by other files."""

# Convenient sink for all output we don't care about.
import shutil
import subprocess
import os
import math
import logging

FNULL = open(os.devnull, "w")

dir_path = os.path.dirname(os.path.realpath(__file__))
logging.basicConfig()
logger = logging.getLogger("apk-patch-size-estimator")
logger.setLevel(20)


def find_binary(binary_name):
    """Finds the path of a binary."""

    try:
        return subprocess.check_output(['which', binary_name]).strip()
    except subprocess.CalledProcessError:
        raise Exception(
            'No "' + binary_name + '" on PATH, please install or fix PATH.')


def check_exists(*files):
    """Checks if the file exists and die if not."""
    for f in files:
        if not os.path.exists(f):
            raise Exception('File does not exist: %s' % f)


def human_file_size(size):
    """Converts a byte size number into a human readable value."""

    size = abs(size)
    if size == 0:
        return '0B'
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    p = math.floor(math.log(size, 2) / 10)
    return '%.3g%s' % (size / math.pow(1024, p), units[int(p)])


def cleanup(*files):
    """Remove files if exist."""
    for f in files:
        if os.path.exists(f):
            os.remove(f)


def run_command(command, **kwargs):
    """Run a command and die if it fails.

  Args:
    kwargs: extra arguments to subprocess.Popen
  """
    p = subprocess.Popen(command, shell=False, **kwargs)
    ret_code = p.wait()
    if ret_code != 0:
        raise Exception('Problem running "%s", returned code: %s' %
                        (" ".join(command), ret_code))


def create_temp_dir(path):
    remove_dir_if_exist(path)
    os.mkdir(path)


def remove_dir_if_exist(path):
    if os.path.exists(path):
        shutil.rmtree(path)


def copy(file):
    file_copy = file + ".copy"
    n = 0
    while os.path.exists(file_copy + str(n)):
        n += 1
    file_copy += str(n)
    run_command(["cp", file, file_copy])
    return file_copy


def get_size(file):
    """Gets the size of the file."""
    check_exists(file)
    size = os.stat(file).st_size
    return size
