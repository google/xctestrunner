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

"""The helper class to get information from simulator device type's profile."""

import os

from shared import ios_constants
from shared import ios_errors
from shared import plist_util
from shared import xcode_info_util


class SimTypeProfile(object):
  """The object for simulator device type's profile."""

  def __init__(self, device_type):
    """Constructor of SimulatorProfile object.

    Args:
      device_type: string, device type of the new simulator. The value
          corresponds to the output of `xcrun simctl list devicetypes`.
          E.g., iPhone 6, iPad Air, etc.
    """
    self._device_type = device_type
    self._profile_plist_obj = None
    self._min_os_version = None
    self._max_os_version = None

  @property
  def profile_plist_obj(self):
    """Gets the Plist object of the simulator device type's profile.plist.

    Returns:
      plist_util.Plist, the Plist object of the simulator device type's
      profile.plist.
    """
    if not self._profile_plist_obj:
      if xcode_info_util.GetXcodeVersionNumber() >= 900:
        platform_path = xcode_info_util.GetSdkPlatformPath(
            ios_constants.SDK.IPHONEOS)
      else:
        platform_path = xcode_info_util.GetSdkPlatformPath(
            ios_constants.SDK.IPHONESIMULATOR)
      profile_plist_path = os.path.join(
          platform_path,
          'Developer/Library/CoreSimulator/Profiles/DeviceTypes/'
          '%s.simdevicetype/Contents/Resources/profile.plist'
          % self._device_type)
      self._profile_plist_obj = plist_util.Plist(profile_plist_path)
    return self._profile_plist_obj

  @property
  def min_os_version(self):
    """Gets the min supported OS version.

    Returns:
      string, the min supported OS version.
    """
    if not self._min_os_version:
      min_os_version = self.profile_plist_obj.GetPlistField('minRuntimeVersion')
      # Cut build version. E.g., cut 9.3.3 to 9.3.
      if min_os_version.count('.') > 1:
        min_os_version = min_os_version[:min_os_version.rfind('.')]
      self._min_os_version = min_os_version
    return self._min_os_version

  @property
  def max_os_version(self):
    """Gets the max supported OS version.

    Returns:
      string, the max supported OS version.
    """
    if not self._max_os_version:
      # If the profile.plist does not have maxRuntimeVersion field, it means
      # it supports the max OS version of current iphonesimulator platform.
      try:
        max_os_version = self.profile_plist_obj.GetPlistField(
            'maxRuntimeVersion')
      except ios_errors.PlistError:
        max_os_version = xcode_info_util.GetSdkVersion(
            ios_constants.SDK.IPHONESIMULATOR)
      # Cut build version. E.g., cut 9.3.3 to 9.3.
      if max_os_version.count('.') > 1:
        max_os_version = max_os_version[:max_os_version.rfind('.')]
      self._max_os_version = max_os_version
    return self._max_os_version
