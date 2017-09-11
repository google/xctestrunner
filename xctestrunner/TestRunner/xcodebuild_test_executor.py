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

"""Helper class for running test by xcodebuild tool."""

import io
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time

from xctestrunner.Shared import ios_constants
from xctestrunner.Shared import ios_errors
from xctestrunner.Shared import xcode_info_util


_XCODEBUILD_TEST_STARTUP_TIMEOUT_SEC = 150


class CheckXcodebuildStuckThread(threading.Thread):
  """The thread class that checking if xcodebuild process stucks.

  The thread will stop gracefully when it is called Terminate() or the given
  process is terminated or reaching the given timeout. If reaching the given
  timeout, this thread will also kill the given xcodebuild process.
  """

  def __init__(self, xcodebuild_test_popen,
               timeout_sec=_XCODEBUILD_TEST_STARTUP_TIMEOUT_SEC):
    super(CheckXcodebuildStuckThread, self).__init__()
    self._xcodebuild_test_popen = xcodebuild_test_popen
    self._terminate = False
    self._is_xcodebuild_stuck = False
    self._timeout_sec = timeout_sec

  def run(self):
    start_time = time.time()
    while (not self._terminate and
           start_time + self._timeout_sec >= time.time() and
           self._xcodebuild_test_popen.poll() is None):
      time.sleep(2)
    if not self._terminate and start_time + self._timeout_sec < time.time():
      logging.warning(
          'The xcodebuild command got stuck and has not started test in %d. '
          'Will kill the command directly.', self._timeout_sec)
      self._is_xcodebuild_stuck = True
      self._xcodebuild_test_popen.terminate()

  def Terminate(self):
    """Terminates this thread."""
    self._terminate = True

  @property
  def is_xcodebuild_stuck(self):
    """If the xcodebuild test command is stuck in timeout."""
    return self._is_xcodebuild_stuck


class XcodebuildTestExecutor(object):
  """A class to execute testing command by xcodebuild tool."""

  def __init__(self, command, sdk=None, test_type=None):
    """Initializes the XcodebuildTestExecutor object.

    Args:
      command: array, the testing command of `xcodebuild`.
      sdk: ios_constants.SDK, the sdk of the target device to run test. If it
          is provided, the executor will have sdk specific handler. Otherwise,
          the executor won't have sdk specific handler.
      test_type: ios_constants.TestType, the type of the test. If it is
          provided, the executor will have test type specific handler.
          Otherwise, the executor won't have test_type specific handler.
    """
    self._command = command
    self._sdk = sdk
    self._test_type = test_type
    self._test_started = False
    self._need_device_reboot = False

  def Execute(self):
    """Executes the xcodebuild test command."""
    run_env = dict(os.environ)
    run_env['NSUnbufferedIO'] = 'YES'
    process = subprocess.Popen(
        self._command, env=run_env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    check_xcodebuild_stuck = CheckXcodebuildStuckThread(process)
    check_xcodebuild_stuck.start()

    output = io.BytesIO()
    for stdout_line in iter(process.stdout.readline, ''):
      if (not self._test_started and
          ios_constants.TEST_STARTED_SIGNAL in stdout_line):
        self._test_started = True
        check_xcodebuild_stuck.Terminate()
      sys.stdout.write(stdout_line)
      output.write(stdout_line)
    process.wait()

    try:
      if not self._test_started:
        check_xcodebuild_stuck.Terminate()
        if check_xcodebuild_stuck.is_xcodebuild_stuck:
          self._need_device_reboot = True
          raise ios_errors.XcodebuildTestError(
              'xcodebuild command can not launch test on device/simulator '
              'in %ss.'
              % _XCODEBUILD_TEST_STARTUP_TIMEOUT_SEC)
      return output.getvalue()
    finally:
      _DeleteTestCacheFileDirs(output.getvalue(), self._sdk, self._test_type)

  @property
  def need_device_reboot(self):
    return self._need_device_reboot

  @property
  def test_started(self):
    return self._test_started


def _DeleteTestCacheFileDirs(xcodebuild_test_output, sdk, test_type):
  """Deletes the cache files of the test session according to arguments."""
  if sdk == ios_constants.SDK.IPHONEOS:
    max_cache_dir_num = 1
    if test_type == ios_constants.TestType.XCUITEST:
      # Because XCUITest will install two apps (app under test and
      # XCTRunner.app) on the device.
      max_cache_dir_num = 2
    test_cache_file_dirs = _FetchTestCacheFileDirs(xcodebuild_test_output,
                                                   max_cache_dir_num)
    for cache_dir in test_cache_file_dirs:
      if os.path.exists(cache_dir):
        logging.info('Removing cache files directory: %s', cache_dir)
        shutil.rmtree(cache_dir)


def _FetchTestCacheFileDirs(xcodebuild_test_output, max_dir_num=1):
  """Fetches the cache file directories of this test session.

  When using `xcodebuild` to run test on iOS real device, it will generate some
  cache files under
  DARWIN_USER_CACHE_DIR/com.apple.DeveloperTools/All/Xcode/EmbeddedAppDeltas.

  Args:
    xcodebuild_test_output: string, the `xcodebuild test` output of this test
        session.
    max_dir_num: int, the max number of test cache files potentially.

  Returns:
    an array of this test's EmbeddedAppDeltas directories.
  """
  xcode_cache_dir = xcode_info_util.GetXcodeEmbeddedAppDeltasDir()
  pattern = re.compile('(%s/[a-z0-9]+)/' % re.escape(xcode_cache_dir))
  start_pos = 0
  cache_file_dirs = set()
  while (start_pos < len(xcodebuild_test_output) and
         len(cache_file_dirs) < max_dir_num):
    match = pattern.search(xcodebuild_test_output, start_pos)
    if not match:
      break
    cache_file_dirs.add(match.group(1))
    start_pos = match.end(1)
  return cache_file_dirs
