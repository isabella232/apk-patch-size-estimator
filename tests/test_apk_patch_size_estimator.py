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

import apk_patch_size_estimator
from mock import patch
import os
import subprocess
import unittest
import hashlib

BUF_SIZE = 1 << 16
RANDOM_FILE = 'tests/random_file'
RANDOM_FILE_SIZE = 1 << 16
ZIP1 = 'tests/1.zip'
ZIP2 = 'tests/2.zip'
TMP = '/tmp'


def sha1(filename):
  accumulator = hashlib.sha1()
  file = open(filename, "rb")
  data = file.read(BUF_SIZE)
  while data:
    accumulator.update(data)
    data = file.read(BUF_SIZE)
  return accumulator.hexdigest()


class TestCalculates(unittest.TestCase):
  def setUp(self):
    apk_patch_size_estimator.find_bins_or_die()

  def test_find_binary_success(self):
    with patch.object(subprocess, 'check_output', return_value=''):
      apk_patch_size_estimator.find_binary('ls')
      subprocess.check_output.assert_any_call(['which', 'ls'])

  def test_find_binary_fail(self):
    with self.assertRaises(Exception) as context:
      apk_patch_size_estimator.find_binary('does_not_extist_command')
    self.assertEqual(
        context.exception.message,
        'No "does_not_extist_command" on PATH, please install or fix PATH.')

  def test_bsdiff(self):
    bsdiff_patch_path = apk_patch_size_estimator.bsdiff(
        ZIP1,
        ZIP2,
        TMP)
    # Obtained by compute bsdiff of 1.zip and 2.zip
    # Strip first 32 bytes
    # bunzip2 the rest
    # attach the 32 bytes back
    # Compute sha1sum
    expected_sha1 = "bd7434d2fbdcca1d6e346cd9441ce1c7fbdc3200"

    self.assertTrue(os.path.exists(bsdiff_patch_path))
    self.assertEqual(sha1(bsdiff_patch_path), expected_sha1)
    os.remove(bsdiff_patch_path)

  def test_filebyfile(self):
    filebyfile_patch_path = apk_patch_size_estimator.filebyfile(
        ZIP1,
        ZIP2,
        TMP)
    # Obtained by running
    # java -jar lib/file-by-file-tools.jar --generate --old tests/1.zip \
    # --new tests/2.zip --patch patch && sha1sum patch && rm patch
    expected_sha1 = "6fd285a07a4d5256a8b46a233dbf7acb360e59c8"
    self.assertTrue(os.path.exists(filebyfile_patch_path))
    self.assertEqual(sha1(filebyfile_patch_path), expected_sha1)
    os.remove(filebyfile_patch_path)

  def test_gzip(self):
    gzipped_path = apk_patch_size_estimator.gzip(RANDOM_FILE)

    # Obtained by running
    # gzip -9 < tests/random_file | sha1sum
    expected_sha1 = "720ade7137c1ae830272a8a3d04e90f337edce5f"
    self.assertTrue(os.path.exists(gzipped_path))
    self.assertEqual(sha1(gzipped_path), expected_sha1)
    os.remove(gzipped_path)

  def test_brotli(self):
    brotlied_path = apk_patch_size_estimator.brotli(RANDOM_FILE)

    # Obtained by running
    # brotli -c tests/random_file | sha1sum
    expected_sha1 = "bf1f64442ca5f0c6d58874dcdccc0b4045521823"
    self.assertTrue(os.path.exists(brotlied_path))
    self.assertEqual(sha1(brotlied_path), expected_sha1)
    os.remove(brotlied_path)

  def test_get_size(self):
    self.assertEqual(apk_patch_size_estimator.get_size(RANDOM_FILE),
                     RANDOM_FILE_SIZE)

  def test_no_diff(self):
    no_diff_patch_path = apk_patch_size_estimator.no_diff(ZIP1, ZIP2, TMP)

    self.assertTrue(os.path.exists(no_diff_patch_path))
    self.assertEqual(sha1(no_diff_patch_path), sha1(ZIP2))
    self.assertNotEqual(no_diff_patch_path, ZIP2)
    os.remove(no_diff_patch_path)

  def test_no_compress(self):
    no_compress_path = apk_patch_size_estimator.no_compress(RANDOM_FILE)

    self.assertTrue(os.path.exists(no_compress_path))
    self.assertEqual(sha1(no_compress_path), sha1(RANDOM_FILE))
    self.assertNotEqual(no_compress_path, RANDOM_FILE)
    os.remove(no_compress_path)

  def test_human_file_size(self):
    self.assertEqual(
        apk_patch_size_estimator.human_file_size(0), '0B')
    self.assertEqual(
        apk_patch_size_estimator.human_file_size(100), '100B')
    self.assertEqual(
        apk_patch_size_estimator.human_file_size(1024), '1KB')
    self.assertEqual(
        apk_patch_size_estimator.human_file_size(1048576), '1MB')
    self.assertEqual(
        apk_patch_size_estimator.human_file_size(1073741824), '1GB')
    self.assertEqual(
        apk_patch_size_estimator.human_file_size(1099511627776), '1TB')
    self.assertEqual(
        apk_patch_size_estimator.human_file_size(1981633), '1.89MB')
    self.assertEqual(
        apk_patch_size_estimator.human_file_size(15654267), '14.9MB')
    self.assertEqual(
        apk_patch_size_estimator.human_file_size(353244297), '337MB')


if __name__ == '__main__':
  unittest.main()
