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
"""This file contains implementations of various delta algorithms."""

import os
import zipfile
from utils import *


class DeltaAlgorithm(object):
    """Wrapper class around delta methods to provide some convenient metadata."""

    def __init__(self, name, patch_file_extension, delta_method, short_name,
                 sorting_priority):
        self.name = name
        self.patch_file_extension = patch_file_extension
        self.delta_method = delta_method
        self.short_name = short_name
        self.sorting_priority = sorting_priority

    def compute_delta(self, old_file, new_file, temp_path):
        """Compute a patch with this delta algorithm. Will not cleanup temp_path afterwards

    Args:
      old_file: the old file
      new_file: the new file
      temp_path: the path to the temporary folder to use.

    Returns:
      the path of the patch generated
    """
        check_exists(old_file, new_file, temp_path)

        new_temp_path = os.path.join(temp_path, self.name)
        create_temp_dir(new_temp_path)

        return self.delta_method(old_file, new_file, temp_path)


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
    bsdiff_path = find_binary("bsdiff")
    head_path = find_binary("head")
    tail_path = find_binary("tail")
    bunzip2_path = find_binary("bunzip2")

    # bsdiff paths
    bsdiff_patch_path = os.path.join(temp_path, 'patch.bsdiff')
    raw_bsdiff_path = os.path.join(temp_path, 'patch.raw_bsdiff')
    bzipped_bsdiff_path = raw_bsdiff_path + '.bz2'
    bsdiff_header_path = os.path.join(temp_path, 'patch.raw_bsdiff_header')

    # Create the bsdiff of the two APKs
    run_command([bsdiff_path, old_file, new_file, bsdiff_patch_path])

    # Strip the first 32 bytes the bsdiff file, which is a bsdiff-specific header.
    bsdiff_header = open(bsdiff_header_path, 'w')
    run_command(
        [head_path, '-c', '32', bsdiff_patch_path], stdout=bsdiff_header)
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
        ['cat', bsdiff_header_path, raw_bsdiff_path], stdout=rebuilt_bsdiff)
    rebuilt_bsdiff.flush()
    rebuilt_bsdiff.close()

    return rebuilt_bsdiff_path


def filebyfile(old_file, new_file, temp_path):
    """File-by-file diffing.

  Args:
    old_file: the old APK file
    new_file: the new APK file
    temp_path: the directory to use for the process

  Returns:
    the size the File-by-File patch gzipped

  Raises:
    Exception: if there is a problem calling the binaries needed in the process
  """
    java_path = find_binary("java")

    filebyfile_patch_path = os.path.join(temp_path, 'patch.filebyfile')
    cleanup(filebyfile_patch_path)

    # file by file patch
    # We use a jar from https://github.com/andrewhayden/archive-patcher
    run_command([
        java_path, '-jar', dir_path + '/lib/file-by-file-tools.jar',
        '--generate', '--old', old_file, '--new', new_file, '--patch',
        filebyfile_patch_path
    ])
    return filebyfile_patch_path

def filebyfilev2(old_file, new_file, temp_path):
    """File-by-file v2 diffing.

  Args:
    old_file: the old APK file
    new_file: the new APK file
    temp_path: the directory to use for the process

  Returns:
    the size the File-by-File patch gzipped

  Raises:
    Exception: if there is a problem calling the binaries needed in the process
  """
    java_path = find_binary("java")

    filebyfile_patch_path = os.path.join(temp_path, 'patch.filebyfilev2')
    cleanup(filebyfile_patch_path)

    # file by file patch
    # We use a jar from https://github.com/andrewhayden/archive-patcher
    run_command([
        java_path, '-jar', dir_path + '/lib/file-by-file-tools.jar',
        '--generate', '--v2', '--old', old_file, '--new', new_file, '--patch',
        filebyfile_patch_path
    ])
    return filebyfile_patch_path


def is_archive(filename):
    extensions = [".apk", ".jar", ".zip"]
    for ext in extensions:
        if filename.endswith(ext):
            return True
    return False


def find_common_embedded_archives(old_file, new_file):

    def find_embedded_archives(zip_file):
        return filter(lambda name: is_archive(name),
                      map(lambda entry: entry.filename,
                          zipfile.ZipFile(zip_file, 'r').infolist()))

    old_embedded_archives = find_embedded_archives(old_file)
    new_embedded_archives = find_embedded_archives(new_file)
    common_entries = []
    for entry in new_embedded_archives:
      if entry in old_embedded_archives:
        common_entries.append(entry)
    return common_entries


def strip_embedded_files(file, entries_to_strip):
    file_copy = copy(file)
    for entry in entries_to_strip:
      run_command(["zip", "-d", file_copy, entry], stdout=FNULL)
    return file_copy


def filebyfilev2_stripped(old_file, new_file, temp_path, common_archives):
    filebyfile_patch_path = os.path.join(temp_path,
                                         'patch.filebyfilev2-stripped')
    stripped_apk_old = strip_embedded_files(old_file, common_archives)
    stripped_apk_new = strip_embedded_files(new_file, common_archives)
    stripped_patch = filebyfile(stripped_apk_old, stripped_apk_new, temp_path)
    return stripped_patch


def filebyfilev2_estimate(old_file, new_file, temp_path):

    filebyfile_patch_path = os.path.join(temp_path, 'patch.filebyfilev2.estimate')
    common_archives = find_common_embedded_archives(old_file, new_file)
    stripped_patch = filebyfilev2_stripped(old_file, new_file, temp_path, common_archives)

    tmp_dir_embedded_old = os.path.join(temp_path, "embedded_old")
    tmp_dir_embedded_new = os.path.join(temp_path, "embedded_new")
    run_command(["mkdir", "-p", tmp_dir_embedded_old, tmp_dir_embedded_new])
    for entry in common_archives:
      run_command(
          ["unzip", old_file, entry, "-d", tmp_dir_embedded_old], stdout=FNULL)
      run_command(
          ["unzip", new_file, entry, "-d", tmp_dir_embedded_new], stdout=FNULL)

    patch_paths = [copy(stripped_patch)]

    for root, _, filenames in os.walk(tmp_dir_embedded_old):
        for filename in filenames:
            old_file_path = os.path.join(root, filename)
            new_file_path = old_file_path.replace(tmp_dir_embedded_old,
                                                  tmp_dir_embedded_new)
            check_exists(old_file_path, new_file_path)
            embedded_apk_patch = filebyfile(old_file_path, new_file_path,
                                            temp_path)
            patch_paths.append(copy(embedded_apk_patch))

    final_patch_path = filebyfile_patch_path + ".final"
    final_patch = open(final_patch_path, 'w')
    run_command(["cat"] + patch_paths, stdout=final_patch)
    final_patch.flush()
    final_patch.close()

    cleanup(*patch_paths)
    import shutil
    shutil.rmtree(tmp_dir_embedded_new)
    shutil.rmtree(tmp_dir_embedded_old)
    return final_patch_path


def filebyfilev2_noreorder(old_file, new_file, temp_path):

    common_archives = find_common_embedded_archives(old_file, new_file)

    def print_file_block(file_block):
        return "%d files from '%s' to '%s'" % (len(file_block), file_block[0],
                                               file_block[-1])

    def print_file_blocks(file_blocks):
        return "[%s]" % (', '.join([print_file_block(f) for f in file_blocks]))

    def get_file_blocks(zip_file):
        zip_entries = zipfile.ZipFile(zip_file, 'r').infolist()
        file_blocks = [[]]

        for entry in zip_entries:
            if entry.filename in common_archives:
                file_blocks.append([])
            else:
                file_blocks[-1].append(entry.filename)

        file_blocks = filter(lambda x: x != [], file_blocks)

        return file_blocks

    def generate_sub_apks(file_blocks, zip_file, tmp_dir):

        def flatten(l):
            ret = []
            for i in l:
                for j in i:
                    ret.append(j)
            return ret

        for i in range(0, len(file_blocks)):
            new_archive = strip_embedded_files(zip_file, common_archives)
            all_files_to_delete = flatten(
                [file_blocks[j] for j in range(0, len(file_blocks)) if j != i])
            for f in all_files_to_delete:
                run_command(["zip", "-d", new_archive, f], stdout=FNULL)
            run_command(
                ['cp', new_archive,
                 os.path.join(tmp_dir,
                              str(i) + ".apk")])

    filebyfile_patch_path = os.path.join(temp_path,
                                         'patch.filebyfilev2.noreorder')
    tmp_dir_old = os.path.join(temp_path, "sub_apk_old")
    tmp_dir_new = os.path.join(temp_path, "sub_apk_new")
    run_command(["mkdir", "-p", tmp_dir_old, tmp_dir_new])

    for entry in common_archives:
      run_command(
          ["unzip", copy(old_file), entry, "-d", tmp_dir_old], stdout=FNULL)
      run_command(
          ["unzip", copy(new_file), entry, "-d", tmp_dir_new], stdout=FNULL)

    old_file_blocks = get_file_blocks(old_file)
    new_file_blocks = get_file_blocks(new_file)

    logger.info("Computing deltas between [%s] and [%s]" %
                (','.join([print_file_block(f) for f in old_file_blocks]),
                 ','.join([print_file_block(f) for f in new_file_blocks])))

    assert (len(old_file_blocks) == len(new_file_blocks))

    generate_sub_apks(old_file_blocks, old_file, tmp_dir_old)
    generate_sub_apks(new_file_blocks, new_file, tmp_dir_new)

    patch_paths = []

    for root, _, filenames in os.walk(tmp_dir_old):
        for filename in filenames:
            old_file_path = os.path.join(root, filename)
            new_file_path = old_file_path.replace(tmp_dir_old, tmp_dir_new)
            check_exists(old_file_path, new_file_path)
            logger.info("NOREORDER: generating patch between %s and %s" % (old_file_path, new_file_path))
            sub_apk_patch = filebyfile(old_file_path, new_file_path, temp_path)
            patch_paths.append(copy(sub_apk_patch))

    final_patch_path = filebyfile_patch_path + ".final"
    final_patch = open(final_patch_path, 'w')
    run_command(["cat"] + patch_paths, stdout=final_patch)
    final_patch.flush()
    final_patch.close()

    return final_patch_path


def no_diff(old_file, new_file, temp_path):
    """No-op diffing algorithm that just returns a copy of the new file."""
    check_exists(new_file)
    new_file_copy = os.path.join(temp_path, "new_apk.diff")
    run_command(["cp", new_file, new_file_copy])
    check_exists(new_file_copy)
    return new_file_copy


def get_delta_algorithms(deltas=None):
    all = [
        DeltaAlgorithm(
            name="Identity",
            short_name="identity",
            patch_file_extension=".identity",
            delta_method=no_diff,
            sorting_priority=0),
        DeltaAlgorithm(
            name="BSDIFF",
            short_name="bsdiff",
            patch_file_extension=".bsdiff",
            delta_method=bsdiff,
            sorting_priority=1),
        DeltaAlgorithm(
            name="File-By-File-V1",
            short_name="fbfv1",
            patch_file_extension=".fbf",
            delta_method=filebyfile,
            sorting_priority=2),
        DeltaAlgorithm(
            name="File-By-File-V2-w-Reorder",
            short_name="fbfv2-reorder",
            patch_file_extension=".fbfv2-reorder",
            delta_method=filebyfilev2_estimate,
            sorting_priority=3),
        DeltaAlgorithm(
            name="File-By-File-V2",
            short_name="fbfv2",
            patch_file_extension=".fbfv2",
            delta_method=filebyfilev2,
            sorting_priority=3),
        DeltaAlgorithm(
            name="File-By-File-V2-wo-Reorder",
            short_name="fbfv2-noreorder",
            patch_file_extension=".fbfv2-noreorder",
            delta_method=filebyfilev2_noreorder,
            sorting_priority=4)
    ]

    if deltas is None:
        return all

    return filter(lambda algo: algo.short_name in deltas, all)
