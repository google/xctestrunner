# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utility methods for Xcode information."""

import os
import subprocess


_xcode_version_number = None


def GetXcodeDeveloperPath():
  """Gets the active developer path of Xcode command line tools."""
  return subprocess.check_output(['xcode-select', '-p']).strip()


def GetXcodeVersionNumber():
  """Gets the Xcode version number.

  E.g. if xcode version is 8.2.1, the xcode version number is 821.

  Returns:
    integer, xcode version number.
  """
  global _xcode_version_number
  if _xcode_version_number is not None:
    return _xcode_version_number

  # Example output:
  # Xcode 8.2.1
  # Build version 8C1002
  output = subprocess.check_output(['xcodebuild', '-version'])
  xcode_version = output.split('\n')[0].split(' ')[1]
  parts = xcode_version.split('.')
  xcode_version_number = int(parts[0]) * 100
  if len(parts) > 1:
    xcode_version_number += int(parts[1]) * 10
  if len(parts) > 2:
    xcode_version_number += int(parts[2])
  # Add cache xcode_version_number to avoid calling subprocess multiple times.
  # It is expected that no one changes xcode during the test runner working.
  _xcode_version_number = xcode_version_number
  return _xcode_version_number


def GetDarwinUserCacheDir():
  """Gets the path of Darwin user cache directory."""
  return subprocess.check_output(['getconf', 'DARWIN_USER_CACHE_DIR']).rstrip()


def GetXcodeEmbeddedAppDeltasDir():
  """Gets the path of Xcode's EmbeddedAppDeltas directory."""
  return os.path.join(GetDarwinUserCacheDir(),
                      'com.apple.DeveloperTools/All/Xcode/EmbeddedAppDeltas')
