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

"""Script used to run XCTest/XCUITest on iOS real device and simulator.

This script supports XCTest in Xcode 6+ and XCUITest in Xcode 8+. It can specify
a subset of test classes or test methods to run. It also supports passing
environment variables and arguments to the test.
"""

import argparse
import json
import logging
import subprocess
import sys

from shared import ios_constants
from shared import ios_errors
from shared import xcode_info_util
from simulator_control import simulator_util
from test_runner import runner_exit_codes
from test_runner import xctest_session

_XCTESTRUN_HELP = (
    """The path of the xctestrun file.

With this argument, test runner will use parameters in xctestrun file for
testing by default. The parameters' values can also be overwritten by launch
options.

This argument is only supported in Xcode 8+.""")


def _AddGeneralArguments(parser):
  """Adds general arguments to the parser."""
  parser.add_argument('-v', '--verbose', help='Increase output verbosity.',
                      action='store_true')

  basic_arguments = parser.add_argument_group(
      'Basic arguments',
      description="""The basic arguments for test runner.

      If the arg of xctestrun is not given, the args app_under_test_path and
      test_bundle_path will be required and used for generating a dummy project
      and a xctestrun file (in Xcode 8+). In xcuitest, the XCTRunner.app is also
      auto generated.
      Then test runner will use the generated dummy project or xctestrun file to
      launch test.

      If the arg of xctestrun is given, will skip the xctestrun file generation
      and launch test directly with the given xctestrun file.
      The args app_under_test_path and test_bundle_path won't be required and
      will be gnored.
      Some fields in the xctestrun file will be overwritten by launch options if
      launch options are provided.
      """)
  basic_arguments.add_argument(
      '--app_under_test_path',
      help='The path of the application to be tested.')
  basic_arguments.add_argument(
      '--test_bundle_path',
      help='The path of the test bundle that contains the tests.')
  basic_arguments.add_argument(
      '--xctestrun',
      help=_XCTESTRUN_HELP)

  optional_arguments = parser.add_argument_group('Optional arguments')
  optional_arguments.add_argument(
      '--launch_options_json_path',
      help=ios_constants.LAUNCH_OPTIONS_JSON_HELP)
  optional_arguments.add_argument(
      '--signing_options_json_path',
      help=ios_constants.SIGNING_OPTIONS_JSON_HELP)
  optional_arguments.add_argument(
      '--test_type',
      help='The type of test bundle. Supported test types are %s. If this arg '
           'is provided, will skip the test type detector.'
      % ios_constants.SUPPORTED_TEST_TYPES)
  optional_arguments.add_argument(
      '--work_dir',
      help='The directory of runfiles, including the bundles, generated '
           'xctestrun file. If directory is specified, the directory will not '
           'be deleted after test ends.')
  optional_arguments.add_argument(
      '--output_dir',
      help='The directory where derived data will go, including:\n'
           '1) the detailed test session log which includes test output and '
           'the communication log between host machine and device;\n'
           '2) the screenshots of every test stages (XCUITest).\n'
           'If directory is specified, the directory will not be deleted after '
           'test ends.')


def _AddTestSubParser(subparsers):
  """Adds sub parser for sub command `test`."""
  def _Test(args):
    """The function of sub command `test`."""
    sdk = _PlatformToSdk(args.platform) if args.platform else _GetSdk(args.id)
    with xctest_session.XctestSession(
        sdk=sdk, work_dir=args.work_dir, output_dir=args.output_dir) as session:
      session.Prepare(
          app_under_test=args.app_under_test_path,
          test_bundle=args.test_bundle_path,
          xctestrun_file_path=args.xctestrun,
          test_type=args.test_type,
          signing_options=_GetJson(args.signing_options_json_path))
      session.SetLaunchOptions(_GetJson(args.launch_options_json_path))
      return session.RunTest(args.id)

  test_parser = subparsers.add_parser(
      'test',
      help='Run test directly on connecting iOS real device or existing iOS '
           'simulator.')
  required_arguments = test_parser.add_argument_group('Required arguments')
  required_arguments.add_argument(
      '--id',
      required=True,
      help='The device id. The device can be iOS real device or simulator.')
  optional_arguments = test_parser.add_argument_group('Optional arguments')
  optional_arguments.add_argument(
      '--platform',
      help='The platform of the device. The value can be ios_device or '
           'ios_simulator.'
  )
  test_parser.set_defaults(func=_Test)


def _AddSimulatorTestSubParser(subparsers):
  """Adds sub parser for sub command `simulator_test`."""
  def _RunSimulatorTest(args):
    """The function of running test with new simulator."""
    with xctest_session.XctestSession(
        sdk=ios_constants.SDK.IPHONESIMULATOR,
        work_dir=args.work_dir, output_dir=args.output_dir) as session:
      session.Prepare(
          app_under_test=args.app_under_test_path,
          test_bundle=args.test_bundle_path,
          xctestrun_file_path=args.xctestrun,
          test_type=args.test_type,
          signing_options=_GetJson(args.signing_options_json_path))
      session.SetLaunchOptions(_GetJson(args.launch_options_json_path))

      # In prior of Xcode 9, `xcodebuild test` will launch the Simulator.app
      # process. If there is Simulator.app before running test, it will cause
      # error later.
      if xcode_info_util.GetXcodeVersionNumber() < 900:
        simulator_util.QuitSimulatorApp()
      max_attempts = 3
      reboot_sim = False
      for i in range(max_attempts):
        if not reboot_sim:
          simulator_id, _, _, _ = simulator_util.CreateNewSimulator(
              device_type=args.device_type, os_version=args.os_version,
              name_prefix=args.new_simulator_name_prefix)
        reboot_sim = False

        try:
          # Don't use command "{Xcode_developer_dir}Applications/ \
          # Simulator.app/Contents/MacOS/Simulator" to launch the Simulator.app.
          # 1) `xcodebuild test` will handle the launch Simulator.
          # 2) If there are two Simulator.app processes launched by command line
          # and `xcodebuild test` starts to run on one of Simulator, the another
          # Simulator.app will popup 'Unable to boot device in current state: \
          # Booted' dialog and may cause potential error.
          exit_code = session.RunTest(simulator_id)
          if i < max_attempts - 1:
            if exit_code == runner_exit_codes.EXITCODE.NEED_RECREATE_SIM:
              logging.warning(
                  'Will create a new simulator to retry running test.')
              continue
            if exit_code == runner_exit_codes.EXITCODE.NEED_REBOOT_DEVICE:
              reboot_sim = True
              logging.warning(
                  'Will reboot the simulator to retry running test.')
              continue
          return exit_code
        finally:
          # 1. In prior of Xcode 9, `xcodebuild test` will launch the
          # Simulator.app process. Quit the Simulator.app to avoid side effect.
          # 2. Quit Simulator.app can also shutdown the simulator. To make sure
          # the Simulator state to be SHUTDOWN, still call shutdown command
          # later.
          if xcode_info_util.GetXcodeVersionNumber() < 900:
            simulator_util.QuitSimulatorApp()
          simulator_obj = simulator_util.Simulator(simulator_id)
          if reboot_sim:
            simulator_obj.Shutdown()
          else:
            # In Xcode 9+, simctl can delete the Booted simulator.
            # In prior of Xcode 9, we have to shutdown the simulator first
            # before deleting it.
            if xcode_info_util.GetXcodeVersionNumber() < 900:
              simulator_obj.Shutdown()
            simulator_obj.Delete()

  def _SimulatorTest(args):
    """The function of sub command `simulator_test`."""
    try:
      return _RunSimulatorTest(args)
    except ios_errors.SimError:
      return runner_exit_codes.EXITCODE.SIM_ERROR

  test_parser = subparsers.add_parser(
      'simulator_test',
      help='Run test on a new created simulator, which will be deleted '
           'after test finishes.')
  test_parser.add_argument(
      '--device_type',
      help='The device type of the simulator to run test. The supported types '
           'correspond to the output of `xcrun simctl list devicetypes`. E.g., '
           'iPhone 6, iPad Air. By default, it is the latest supported iPhone.')
  test_parser.add_argument(
      '--os_version',
      help='The os version of the simulator to run test. The supported os '
           'versions correspond to the output of `xcrun simctl list runtimes`. '
           'E.g., 10.2, 9.3. By default, it is the latest supported version of '
           'the simulator type.')
  test_parser.add_argument(
      '--new_simulator_name_prefix',
      help='The name prefix of the new simulator. By default, it is "New".'
           'The new simulator name will be the value of concatenating name '
           'prefix with simulator type and os version. '
           'E.g., New-iPhone 6 Plus-10.2.')
  test_parser.set_defaults(func=_SimulatorTest)


def _BuildParser():
  """Builds a parser which is to parse arguments/sub commands of test runner.

  Returns:
    a argparse object.
  """
  parser = argparse.ArgumentParser(
      formatter_class=argparse.RawTextHelpFormatter)
  _AddGeneralArguments(parser)
  subparsers = parser.add_subparsers(help='Sub-commands help')
  _AddTestSubParser(subparsers)
  _AddSimulatorTestSubParser(subparsers)
  return parser


def _GetJson(json_path):
  """Gets the json dict from the file."""
  if json_path:
    with open(json_path) as input_file:
      try:
        return json.load(input_file)
      except ValueError as e:
        raise ios_errors.IllegalArgumentError(e)
  return None


def _PlatformToSdk(platform):
  """Gets the SDK of the given platform."""
  if platform == ios_constants.PLATFORM.IOS_DEVICE:
    return ios_constants.SDK.IPHONEOS
  if platform == ios_constants.PLATFORM.IOS_SIMULATOR:
    return ios_constants.SDK.IPHONESIMULATOR
  raise ios_errors.IllegalArgumentError(
      'The platform %s is not supported. The supported values are %s.' %
      (platform, ios_constants.SUPPORTED_PLATFORMS))


def _GetSdk(device_id):
  """Gets the sdk of the target device with the given device_id."""
  # The command `instruments -s devices` is much slower than
  # `xcrun simctl list devices`. So use `xcrun simctl list devices` to check
  # IPHONESIMULATOR SDK first.
  simlist_devices_output = simulator_util.RunSimctlCommand(
      ['xcrun', 'simctl', 'list', 'devices'])
  if device_id in simlist_devices_output:
    return ios_constants.SDK.IPHONESIMULATOR

  known_devices_output = subprocess.check_output(
      ['instruments', '-s', 'devices'])
  for line in known_devices_output.split('\n'):
    if device_id in line and '(Simulator)' not in line:
      return ios_constants.SDK.IPHONEOS

  raise ios_errors.IllegalArgumentError(
      'The device with id %s can not be found. The known devices are %s.' %
      (device_id, known_devices_output))


def main(argv):
  args = _BuildParser().parse_args(argv[1:])
  if args.verbose:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')
  else:
    logging.basicConfig(format='%(asctime)s %(message)s')
  exit_code = args.func(args)
  logging.info('Done.')
  return exit_code


if __name__ == '__main__':
  sys.exit(main(sys.argv))
