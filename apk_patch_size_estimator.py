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

"""Estimates the size of Google Play patches and the new gzipped APK.

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

import sys
import argparse
import locale
import math
import os
import subprocess

bsdiff_path = None
gzip_path = None
head_path = None
tail_path = None
bunzip2_path = None
java_path = None
brotli_path = None
dir_path = os.path.dirname(os.path.realpath(__file__))


def find_bins_or_die():
  """Checks that all the binaries needed are available.

  The script needs bsdiff, gzip, head, tail and bunzip2
  binaries availables in the system.
  """

  global bsdiff_path
  if not bsdiff_path:
    bsdiff_path = find_binary('bsdiff')
  global gzip_path
  if not gzip_path:
    gzip_path = find_binary('gzip')
  global head_path
  if not head_path:
    head_path = find_binary('head')
  global tail_path
  if not tail_path:
    tail_path = find_binary('tail')
  global bunzip2_path
  if not bunzip2_path:
    bunzip2_path = find_binary('bunzip2')
  global java_path
  if not java_path:
    java_path = find_binary('java')
  global brotli_path
  if not brotli_path:
    brotli_path = find_binary('brotli')


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
  p = subprocess.Popen(
      command,
      shell=False, **kwargs)
  ret_code = p.wait()
  if ret_code != 0:
    raise Exception(
        'Problem running "%s", returned code: %s' % (
        " ".join(command), ret_code))


def bsdiff(old_file, new_file, temp_path):
  """Compute a BSDIFF patch, uncompressing the bzip2 part.

  Args:
    old_file: the old APK file
    new_file: the new APK file
    temp_path: the directory to use for the process

  Returns:
    the path of the patch generated

  Raises:
    Exception: if there is a problem calling the binaries needed in the process
  """

  # Oddities:
  # Bsdiff forces bzip2 compression, which starts after byte 32. Bzip2 isn't
  # necessarily the best choice in all cases, and isn't necessarily what Google
  # Play uses, so it has to be uncompressed.

  # bsdiff paths
  bsdiff_patch_path = os.path.join(temp_path, 'patch.bsdiff')
  raw_bsdiff_path = os.path.join(temp_path, 'patch.raw_bsdiff')
  bzipped_bsdiff_path = raw_bsdiff_path + '.bz2'
  bsdiff_header_path = os.path.join(temp_path, 'patch.raw_bsdiff_header')
  cleanup(raw_bsdiff_path, bzipped_bsdiff_path, bsdiff_header_path)

  # Create the bsdiff of the two APKs
  run_command(
      [bsdiff_path, old_file, new_file, bsdiff_patch_path])

  # Strip the first 32 bytes the bsdiff file, which is a bsdiff-specific header.
  bsdiff_header = open(bsdiff_header_path, 'w')
  run_command(
      [head_path, '-c', '32', bsdiff_patch_path],
      stdout=bsdiff_header)
  bsdiff_header.flush()
  bsdiff_header.close()

  # Take the remainder of the file to gain an uncompressed copy.
  bzipped_bsdiff_patch = open(bzipped_bsdiff_path, 'w')
  run_command(
      [tail_path, '-c', '+33', bsdiff_patch_path],
      stdout=bzipped_bsdiff_patch)
  bzipped_bsdiff_patch.flush()
  bzipped_bsdiff_patch.close()
  run_command([bunzip2_path, '-d', '-q', bzipped_bsdiff_path])

  # Prepend the 32 bytes of bsdiff header back onto the uncompressed file.
  rebuilt_bsdiff_path = raw_bsdiff_path + '.rebuilt'
  if os.path.exists(rebuilt_bsdiff_path): os.remove(rebuilt_bsdiff_path)
  rebuilt_bsdiff = open(rebuilt_bsdiff_path, 'w')
  run_command(
      ['cat', bsdiff_header_path, raw_bsdiff_path],
      stdout=rebuilt_bsdiff)
  rebuilt_bsdiff.flush()
  rebuilt_bsdiff.close()

  # Clean up.
  cleanup(raw_bsdiff_path, bsdiff_header_path, bzipped_bsdiff_path)

  return rebuilt_bsdiff_path


def filebyfile(old_file, new_file, temp_path):
  """File-by-file diffing.

  Args:
    old_file: the old APK file
    new_file: the new APK file
    save_patch_path: the path including filename to save the generated patch.
    temp_path: the directory to use for the process

  Returns:
    the size the File-by-File patch gzipped

  Raises:
    Exception: if there is a problem calling the binaries needed in the process
  """

  filebyfile_patch_path = os.path.join(temp_path, '.filebyfile')
  cleanup(filebyfile_patch_path)

  # file by file patch
  # We use a jar from https://github.com/andrewhayden/archive-patcher
  run_command(
      [java_path, '-jar', dir_path + '/lib/file-by-file-tools.jar',
       '--generate',
       '--old', old_file, '--new', new_file, '--patch', filebyfile_patch_path])
  return filebyfile_patch_path


def gzip(patch_path):
  """Gzips the file on patch_path.

  Args:
    patch_path: path to the input file

  Returns:
    path to the gzipped input file
  """
  check_exists(patch_path)
  in_file = open(patch_path, 'r')

  gzipped_path = patch_path + ".gz"
  out_file = open(gzipped_path, 'w')
  run_command([gzip_path, '-9'], stdin=in_file, stdout=out_file)
  in_file.close()
  out_file.close()
  return gzipped_path


def brotli(patch_path):
  """Compresses the given file using BROTLI"""
  check_exists(patch_path)
  run_command([brotli_path, '-9', patch_path])
  return patch_path + ".br"


def get_size(file):
  """Gets the size of the file."""
  check_exists(file)
  size = os.stat(file).st_size
  return size


def no_diff(old_file, new_file, temp_path):
  """No-op diffing algorithm that just returns a copy of the new file."""
  check_exists(new_file)
  new_file_copy = os.path.join(temp_path, "new_apk.diff")
  run_command(["cp", new_file, new_file_copy])
  check_exists(new_file_copy)
  return new_file_copy


def no_compress(file):
  """No-op compression algorithm that returns a copy of input file."""
  check_exists(file)
  new_file = file + ".copy"
  run_command(["cp", file, new_file])
  return new_file


def main():
  locale.setlocale(locale.LC_ALL, '')

  # Parse arguments
  parser = argparse.ArgumentParser(
      description='Estimate the sizes of APK patches for Google Play')
  parser.add_argument(
      '--old-file', default=None, required=True,
      help='the path to the "old" file to generate patches from.')
  parser.add_argument(
      '--new-file', default=None, required=True,
      help='the path to the "new" file to generate patches from.')
  parser.add_argument(
      '--save-patch', default=None,
      help='the path prefix to save the generated patches.')
  parser.add_argument(
      '--temp-dir', default='/tmp',
      help='the temp directory to use for patch generation; defaults to /tmp')
  if not sys.argv[1:]:
    parser.print_help()
    parser.exit()
  args = parser.parse_args()

  # Validate arguments
  check_exists(args.old_file, args.new_file)
  if args.save_patch and not os.access(
      os.path.dirname(os.path.abspath(args.save_patch)), os.W_OK):
    raise Exception('The save patch path is not writable: %s' % args.save_patch)
  if args.save_patch and os.path.isdir(args.save_patch):
    raise Exception('Please include the filename in the path: %s'
                    % args.save_patch)
  save_patch_path = args.save_patch
  if not os.path.isdir(args.temp_dir):
    raise Exception('Temp directory does not exist: %s' % args.temp_dir)
  temp_path = args.temp_dir

  # Checks that the OS binaries needed are available
  find_bins_or_die()

  # Diff and compression modes
  diffs = {"None": no_diff, "BSDIFF": bsdiff, "File-By-File": filebyfile}
  compressions = {"None": no_compress, "GZIP": gzip, "BROTLI": brotli}
  diff_extension = {"None": "", "BSDIFF": ".bsdiff", "File-By-File": ".fbf"}
  compression_extension = {"None": "", "GZIP": ".gz", "BROTLI": ".br"}
  diff_name_in_order = ["None", "BSDIFF", "File-By-File"]
  compression_name_in_order = ["None", "GZIP", "BROTLI"]
  column_width = 15

  print(
    "".join([x.ljust(column_width) for x in [""] + compression_name_in_order]))

  for diff_name in diff_name_in_order:
    diff = diffs[diff_name]
    row = diff_name.ljust(column_width)
    delta_path = diff(args.old_file, args.new_file, temp_path)
    for compression_name in compression_name_in_order:
      compress = compressions[compression_name]
      compressed_path = compress(delta_path)
      patch_size = get_size(compressed_path)
      row += human_file_size(patch_size).ljust(column_width)

      # no point copying if we are not doing diffing or patching
      if save_patch_path and not (
          diff_name == "None" and compression_name == "None"):
        run_command(["cp", compressed_path,
                     save_patch_path + diff_extension[diff_name] +
                     compression_extension[compression_name]])
      cleanup(compressed_path)
    cleanup(delta_path)
    print row


if __name__ == '__main__':
  main()
