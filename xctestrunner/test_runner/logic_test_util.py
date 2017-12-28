"""The helper classes to run logic test."""

import logging
import subprocess

from xctestrunner.shared import ios_constants
from xctestrunner.shared import xcode_info_util
from xctestrunner.test_runner import runner_exit_codes

_SIMCTL_ENV_VAR_PREFIX = 'SIMCTL_CHILD_'


def RunLogicTestOnSim(
    sim_id, test_bundle_path, env_vars=None, args=None, tests_to_run=None):
  """Runs logic tests on the simulator. The output prints on system stdout.

  Args:
    sim_id: string, the id of the simulator.
    test_bundle_path: string, the path of the logic test bundle.
    env_vars: dict, the additionl environment variables passing to test's
        process.
    args: array, the additional arguments passing to test's process.
    tests_to_run: array, the format of each item is TestClass[/TestMethod].
        If it is empty, then runs with All methods.

  Returns:
    exit_code: A value of type runner_exit_codes.EXITCODE.

  Raises:
    ios_errors.SimError: The command to launch logic test has error.
  """
  simctl_env_vars = {}
  if env_vars:
    for key in env_vars:
      simctl_env_vars[_SIMCTL_ENV_VAR_PREFIX + key] = env_vars[key]
  command = [
      'xcrun', 'simctl', 'spawn', sim_id,
      xcode_info_util.GetXctestToolPath(ios_constants.SDK.IPHONESIMULATOR)]
  if args:
    command += args
  if not tests_to_run:
    tests_to_run = ['All']
  for test_to_run in tests_to_run:
    try:
      subprocess.Popen(
          command + ['-XCTest', test_to_run, test_bundle_path],
          env=simctl_env_vars, stderr=subprocess.STDOUT).wait()
    except subprocess.CalledProcessError as e:
      logging.waring(
          'Failed to launch logic test on simulator %s: %s', sim_id, e.output)
      return runner_exit_codes.EXITCODE.SIM_ERROR
  return runner_exit_codes.EXITCODE.SUCCEEDED
