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

from xctestrunner.shared import ios_constants
from xctestrunner.shared import ios_errors
from xctestrunner.shared import xcode_info_util
from xctestrunner.simulator_control import simulator_util
from xctestrunner.test_runner import runner_exit_codes


_XCODEBUILD_TEST_STARTUP_TIMEOUT_SEC = 150
_SIM_TEST_MAX_ATTEMPTS = 2
_TAIL_SIM_LOG_LINE = 200
_BACKGROUND_TEST_RUNNER_ERROR = 'Failed to background test runner'
_PROCESS_EXISTED_OR_CRASHED_ERROR = ('The process did launch, but has since '
                                     'exited or crashed.')
_REQUEST_DENIED_ERROR = ('The request was denied by service delegate '
                         '(SBMainWorkspace) for reason')
_APP_UNKNOWN_TO_FRONTEND_PATTERN = re.compile(
    'Application ".*" is unknown to FrontBoard.')


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

  def __init__(self, command, sdk=None, test_type=None, device_id=None,
               succeeded_signal=None, failed_signal=None):
    """Initializes the XcodebuildTestExecutor object.

    The optional argument sdk, test_type and device_id can provide more
    specific handler.

    Args:
      command: array, the testing command of `xcodebuild`.
      sdk: ios_constants.SDK, the sdk of the target device to run test.
      test_type: ios_constants.TestType, the type of the test.
      device_id: string, the id of the device to run test.
      succeeded_signal: string, the signal of command succeeded.
      failed_signal: string, the signal of command failed.
    """
    self._command = command
    self._sdk = sdk
    self._test_type = test_type
    self._device_id = device_id
    self._succeeded_signal = succeeded_signal
    self._failed_signal = failed_signal

  def Execute(self, return_output=True):
    """Executes the xcodebuild test command.

    Args:
      return_output: bool, whether save output in the execution result.

    Returns:
      a tuple of two fields:
        exit_code: A value of type runner_exit_codes.EXITCODE.
        output: the output of xcodebuild test command or None if return_output
            is False.
    """
    run_env = dict(os.environ)
    run_env['NSUnbufferedIO'] = 'YES'
    max_attempts = 1
    sim_log_path = None
    if self._sdk == ios_constants.SDK.IPHONESIMULATOR:
      max_attempts = _SIM_TEST_MAX_ATTEMPTS
      if self._device_id:
        sim_log_path = simulator_util.Simulator(
            self._device_id).simulator_system_log_path

    test_started = False
    test_succeeded = False
    test_failed = False

    for i in range(max_attempts):
      process = subprocess.Popen(
          self._command, env=run_env, stdout=subprocess.PIPE,
          stderr=subprocess.STDOUT)
      check_xcodebuild_stuck = CheckXcodebuildStuckThread(process)
      check_xcodebuild_stuck.start()
      output = io.BytesIO()
      for stdout_line in iter(process.stdout.readline, ''):
        if not test_started:
          if ios_constants.TEST_STARTED_SIGNAL in stdout_line:
            test_started = True
            check_xcodebuild_stuck.Terminate()
        else:
          if self._succeeded_signal and self._succeeded_signal in stdout_line:
            test_succeeded = True
          if self._failed_signal and self._failed_signal in stdout_line:
            test_failed = True

        sys.stdout.write(stdout_line)
        sys.stdout.flush()
        # If return_output is false, the output is only used for checking error
        # cause and deleting cached files (_DeleteTestCacheFileDirs method).
        if return_output or not test_started:
          output.write(stdout_line)

      try:
        if test_started:
          if test_succeeded:
            exit_code = runner_exit_codes.EXITCODE.SUCCEEDED
          elif test_failed:
            exit_code = runner_exit_codes.EXITCODE.FAILED
          else:
            exit_code = runner_exit_codes.EXITCODE.ERROR
          return exit_code, output.getvalue() if return_output else None

        check_xcodebuild_stuck.Terminate()
        if check_xcodebuild_stuck.is_xcodebuild_stuck:
          return self._GetResultForXcodebuildStuck(output, return_output)

        if self._sdk == ios_constants.SDK.IPHONESIMULATOR:
          output_str = output.getvalue()
          if self._NeedRecreateSim(output_str):
            return (runner_exit_codes.EXITCODE.NEED_RECREATE_SIM,
                    output_str if return_output else None)

          # The following error can be fixed by relaunching the test again.
          try:
            if sim_log_path:
              tail_sim_log = _ReadFileTailInShell(
                  sim_log_path, _TAIL_SIM_LOG_LINE)
              if (self._test_type == ios_constants.TestType.LOGIC_TEST and
                  simulator_util.IsXctestFailedToLaunchOnSim(tail_sim_log) or
                  self._test_type != ios_constants.TestType.LOGIC_TEST and
                  simulator_util.IsAppFailedToLaunchOnSim(tail_sim_log)):
                raise ios_errors.SimError('')
            if _PROCESS_EXISTED_OR_CRASHED_ERROR in output_str:
              raise ios_errors.SimError('')
          except ios_errors.SimError:
            if i < max_attempts - 1:
              logging.warning(
                  'Failed to launch test on simulator. Will relaunch again.')
              # Triggers the retry.
              continue
            else:
              return (runner_exit_codes.EXITCODE.TEST_NOT_START,
                      output_str if return_output else None)

        return (runner_exit_codes.EXITCODE.TEST_NOT_START,
                output_str if return_output else None)
      finally:
        _DeleteTestCacheFileDirs(output.getvalue(), self._sdk, self._test_type)

  def _GetResultForXcodebuildStuck(self, output, return_output):
    """Gets the execution result for the xcodebuild stuck case."""
    error_message = ('xcodebuild command can not launch test on '
                     'device/simulator in %ss.'
                     % _XCODEBUILD_TEST_STARTUP_TIMEOUT_SEC)
    logging.error(error_message)
    output.write(error_message)
    output_str = output.getvalue()
    if self._sdk == ios_constants.SDK.IPHONEOS:
      return (runner_exit_codes.EXITCODE.NEED_REBOOT_DEVICE,
              output_str if return_output else None)
    return (runner_exit_codes.EXITCODE.TEST_NOT_START,
            output_str if return_output else None)

  def _NeedRecreateSim(self, output_str):
    """Checks if need recreate a new simulator."""
    if (self._test_type == ios_constants.TestType.XCUITEST and
        _BACKGROUND_TEST_RUNNER_ERROR in output_str):
      return True
    if re.search(_APP_UNKNOWN_TO_FRONTEND_PATTERN, output_str):
      return True
    if _REQUEST_DENIED_ERROR in output_str:
      return True
    return False


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


def _ReadFileTailInShell(file_path, line):
  """Tails the file in the last several lines."""
  return subprocess.check_output(['tail', '-%d' % line, file_path])
