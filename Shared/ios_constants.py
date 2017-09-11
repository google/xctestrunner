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

"""The class contains the constants of iOS test runner."""


def enum(**enums):
  return type('Enum', (), enums)


SDK = enum(IPHONEOS='iphoneos', IPHONESIMULATOR='iphonesimulator')
OS = enum(IOS='iOS', WATCHOS='watchOS', TVOS='tvOS')
TestType = enum(XCUITEST='xcuitest', XCTEST='xctest')
SimState = enum(CREATING='Creating', SHUTDOWN='Shutdown', BOOTED='Booted',
                UNKNOWN='Unknown')

SUPPORTED_SDKS = [SDK.IPHONESIMULATOR, SDK.IPHONEOS]
SUPPORTED_TEST_TYPES = [TestType.XCUITEST, TestType.XCTEST]
SUPPORTED_SIM_OSS = [OS.IOS]

TEST_STARTED_SIGNAL = 'Test Suite'
