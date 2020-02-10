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

from xctestrunner.shared import ios_constants

_xcode_version_number = None


def GetXcodeDeveloperPath():
  """Gets the active developer path of Xcode command line tools."""
  return subprocess.check_output(('xcode-select', '-p')).strip()


# Xcode 11+'s Swift dylibs are configured in a way that does not allow them to load the correct
# libswiftFoundation.dylib file from libXCTestSwiftSupport.dylib. This bug only affects tests that
# run on simulators running iOS 12.1 or lower. To fix this bug, we need to provide explicit
# fallbacks to the correct Swift dylibs that have been packaged with Xcode. This method returns the
# path to that fallback directory.
# See https://github.com/bazelbuild/rules_apple/issues/684 for context.
def GetSwift5FallbackLibsDir():
  relativePath = "Toolchains/XcodeDefault.xctoolchain/usr/lib/swift-5.0"
  swiftLibsDir = os.path.join(GetXcodeDeveloperPath(), relativePath)
  swiftLibPlatformDir = os.path.join(swiftLibsDir, ios_constants.SDK.IPHONESIMULATOR)
  if os.path.exists(swiftLibPlatformDir):
    return swiftLibPlatformDir
  return None


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
  output = subprocess.check_output(('xcodebuild', '-version'))
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


def GetSdkPlatformPath(sdk):
  """Gets the selected SDK platform path."""
  return subprocess.check_output(
      ['xcrun', '--sdk', sdk, '--show-sdk-platform-path']).strip()


def GetSdkVersion(sdk):
  """Gets the selected SDK version."""
  return subprocess.check_output(
      ['xcrun', '--sdk', sdk, '--show-sdk-version']).strip()


def GetXctestToolPath(sdk):
  """Gets the path of xctest tool under the given SDK platform."""
  return os.path.join(
      GetSdkPlatformPath(sdk), 'Developer/Library/Xcode/Agents/xctest')


def GetDarwinUserCacheDir():
  """Gets the path of Darwin user cache directory."""
  return subprocess.check_output(('getconf', 'DARWIN_USER_CACHE_DIR')).rstrip()


def GetXcodeEmbeddedAppDeltasDir():
  """Gets the path of Xcode's EmbeddedAppDeltas directory."""
  return os.path.join(GetDarwinUserCacheDir(),
                      'com.apple.DeveloperTools/All/Xcode/EmbeddedAppDeltas')
