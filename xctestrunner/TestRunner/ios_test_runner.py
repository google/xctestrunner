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
import os
import shutil
import subprocess
import sys
import tempfile

from xctestrunner.Shared import bundle_util
from xctestrunner.Shared import ios_constants
from xctestrunner.Shared import ios_errors
from xctestrunner.Shared import xcode_info_util
from xctestrunner.SimulatorControl import simulator_util
from xctestrunner.TestRunner import dummy_project
from xctestrunner.TestRunner import xctestrun


_LAUNCH_OPTIONS_JSON_HELP = (
    """The path of json file, which contains options of launching test.
Available keys for the json:
  env_vars : dict
    Additional environment variables passing to test process. The key and value
    should be string.
  args : array
    Additional arguments passing to test process.
  tests_to_run : array
    The specific test classes or test methods to run. Each item should be
    string and its format is Test-Class-Name[/Test-Method-Name].""")


def _AddGeneralArguments(parser):
  """Adds general arguments to the parser."""
  parser.add_argument('-v', '--verbose', help='Increase output verbosity.',
                      action='store_true')
  required_arguments = parser.add_argument_group('Required arguments')
  required_arguments.add_argument(
      '--app_under_test_path',
      required=True,
      help='The path of the application to be tested.')
  required_arguments.add_argument(
      '--test_bundle_path',
      required=True,
      help='The path of the test bundle that contains the tests.')

  optional_arguments = parser.add_argument_group('Optional arguments')
  optional_arguments.add_argument(
      '--launch_options_json_path',
      help=_LAUNCH_OPTIONS_JSON_HELP)
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
    launch_options = _GetLaunchOptions(args.launch_options_json_path)
    _RunTest(
        args.id, args.app_under_test_path, args.test_bundle_path,
        launch_options=launch_options, test_type=args.test_type,
        work_dir=args.work_dir, output_dir=args.output_dir)

  test_parser = subparsers.add_parser(
      'test',
      help='Run test directly on connecting iOS real device or existing iOS '
           'simulator.')
  required_arguments = test_parser.add_argument_group('Required arguments')
  required_arguments.add_argument(
      '--id',
      required=True,
      help='The device id. The device can be iOS real device or simulator.')
  test_parser.set_defaults(func=_Test)


def _AddSimulatorTestSubParser(subparsers):
  """Adds sub parser for sub command `simulator_test`."""
  def _SimulatorTest(args):
    """The function of sub command `simulator_test`."""
    launch_options = _GetLaunchOptions(args.launch_options_json_path)
    simulator_id = simulator_util.CreateNewSimulator(
        simulator_type=args.simulator_type, os_version=args.os_version,
        name=args.new_simulator_name)
    xcode_version_num = xcode_info_util.GetXcodeVersionNumber()
    try:
      # Don't use command "{Xcode_developer_dir}Applications/Simulator.app/ \
      # Contents/MacOS/Simulator" to launch the Simulator.app.
      # 1) `xcodebuild test` will handle the launch Simulator.
      # 2) If there are two Simulator.app processes launched by command line and
      # `xcodebuild test` starts to run on one of Simulator, the another
      # Simulator.app will popup 'Unable to boot device in current state: \
      # Booted' dialog and may cause potential error.
      _RunTest(
          simulator_id, args.app_under_test_path, args.test_bundle_path,
          launch_options=launch_options, sdk=ios_constants.SDK.IPHONESIMULATOR,
          test_type=args.test_type, work_dir=args.work_dir,
          output_dir=args.output_dir)
    finally:
      # 1. Before Xcode 9, `xcodebuild test` will launch the Simulator.app
      # process. Quit the Simulator.app to avoid side effect.
      # 2. Quit Simulator.app can also shutdown the simulator. To make sure the
      # Simulator state to be SHUTDOWN, still call shutdown command later.
      if xcode_version_num < 900:
        simulator_util.QuitSimulatorApp()
      simulator_obj = simulator_util.Simulator(simulator_id)
      # Can only delete the "SHUTDOWN" state simulator.
      simulator_obj.Shutdown()
      # Deletes the new simulator to avoid side effect.
      simulator_obj.Delete()

  test_parser = subparsers.add_parser(
      'simulator_test',
      help='Run test on a new created simulator, which will be deleted '
           'after test finishes.')
  test_parser.add_argument(
      '--simulator_type',
      help='The type of the simulator to run test. The supported types '
           'correspond to the output of `xcrun simctl list devicetypes`. E.g., '
           'iPhone 6, iPad Air. By default, it is the latest supported iPhone.')
  test_parser.add_argument(
      '--os_version',
      help='The os version of the simulator to run test. The supported os '
           'versions correspond to the output of `xcrun simctl list runtimes`. '
           'E.g., 10.2, 9.3. By default, it is the latest supported version of '
           'the simulator type.')
  test_parser.add_argument(
      '--new_simulator_name',
      help='The name of the new simulator. By default, it will be the value of '
           'concatenating simulator type with os version. '
           'E.g., NEW_IPHONE_6_PLUS_10_2.')
  test_parser.set_defaults(func=_SimulatorTest)


def _BuildParser():
  """Build a parser which is to parse arguments/sub commands of iOS test runner.

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


def _GetLaunchOptions(launch_options_json_path):
  """Gets the launch options in json dict."""
  if launch_options_json_path:
    with open(launch_options_json_path) as input_file:
      try:
        return json.load(input_file)
      except ValueError as e:
        raise ios_errors.IllegalArgumentError(e)
  return None


def _PrepareBundles(working_dir, app_under_test_path, test_bundle_path):
  """Prepares the bundles in work directory.

  If the original bundle is .ipa, the .ipa file will be unzipped under
  working_dir. If the original bundle is .app/.xctest, the bundle file will be
  copied to working_dir.

  Args:
    working_dir: string, the working directory.
    app_under_test_path: string, the path of the application to be tested.
        It can be .ipa or .app.
    test_bundle_path: string, the path of the test bundle to be tested. It can
        be .ipa or .xctest.

  Returns:
    a path of app under test directory (.app) under work directory.
    a path of test bundle directory (.xctest) under work directory.

  Raises:
    ios_errors.IllegalArgumentError: if the app under test/test bundle does not
      exist or its extension is invaild.
  """
  if not os.path.exists(app_under_test_path):
    raise ios_errors.IllegalArgumentError(
        'The app under test does not exists: %s' % app_under_test_path)
  if not (app_under_test_path.endswith('.app') or
          app_under_test_path.endswith('.ipa')):
    raise ios_errors.IllegalArgumentError(
        'The app under test %s should be with .app or .ipa extension.'
        % app_under_test_path)

  if not os.path.exists(test_bundle_path):
    raise ios_errors.IllegalArgumentError(
        'The test bundle does not exists: %s' % test_bundle_path)
  if not (test_bundle_path.endswith('.xctest') or
          test_bundle_path.endswith('.ipa')):
    raise ios_errors.IllegalArgumentError(
        'The test bundle %s should be with .xctest or .ipa extension.'
        % test_bundle_path)

  if app_under_test_path.endswith('.ipa'):
    app_under_test_dir = bundle_util.ExtractIPA(
        app_under_test_path, working_dir, 'app')
  else:
    app_under_test_dir = os.path.join(
        working_dir, os.path.basename(app_under_test_path))
    if not os.path.exists(app_under_test_dir):
      shutil.copytree(app_under_test_path, app_under_test_dir)

  if test_bundle_path.endswith('.ipa'):
    test_bundle_dir = bundle_util.ExtractIPA(
        test_bundle_path, working_dir, 'xctest')
  else:
    test_bundle_dir = os.path.join(working_dir,
                                   os.path.basename(test_bundle_path))
    if not os.path.exists(test_bundle_dir):
      shutil.copytree(test_bundle_path, test_bundle_dir)

  return app_under_test_dir, test_bundle_dir


def _DetectTestType(test_bundle_dir):
  """Detects if the test bundle is XCUITest or XCTest."""
  test_bundle_exec_path = os.path.join(
      test_bundle_dir, os.path.basename(test_bundle_dir).split('.')[0])
  output = subprocess.check_output(['nm', test_bundle_exec_path])
  if 'XCUIApplication' in output:
    return ios_constants.TestType.XCUITEST
  else:
    return ios_constants.TestType.XCTEST


def _RunTest(device_id, app_under_test_path, test_bundle_path,
             launch_options=None, sdk=None, test_type=None, work_dir=None,
             output_dir=None):
  """Runs test according to arguments.

  If work_dir is not provdied, will create a temp direcotry to be work_dir and
  remove it after test ends. If output_dir is not provided, will create a temp
  direcotry to be output_dir and remove it after test ends.

  Args:
    device_id: string, id of device/simulator.
    app_under_test_path: string, the path of the application to be tested. It
        can be .ipa or .app.
    test_bundle_path: string, the path of the test bundle to be tested. It can
        be .ipa or .xctest.
    launch_options: dict, the launch test options.
    sdk: ios_constants.SDK. The sdk of the target device.
    test_type: ios_constants.TestType. The type of test bundle.
    work_dir: string, the working directory contains runfiles.
    output_dir: string, The directory where derived data will go, including:
        1) the detailed test session log which includes test output and the
        communication log between host machine and device;
        2) the screenshots of every test stages (XCUITest). If directory is
        specified, the directory will not be deleted after test ends.'

  Raises:
    ios_errors.IllegalArgumentError:
        1) the app under test/test bundle does not exist;
        2) the app under test/test bundle's extension is invaild.
  """
  if launch_options is None:
    launch_options = {}
  if work_dir:
    if not os.path.exists(work_dir):
      os.mkdir(work_dir)
    delete_work_dir = False
  else:
    work_dir = tempfile.mkdtemp()
    delete_work_dir = True

  if output_dir:
    if not os.path.exists(output_dir):
      os.mkdir(output_dir)
    delete_output_dir = False
  else:
    output_dir = tempfile.mkdtemp()
    delete_output_dir = True

  if not sdk:
    # if the device id is actual iphonesimulator's id.
    if '-' in device_id:
      sdk = ios_constants.SDK.IPHONESIMULATOR
    else:
      sdk = ios_constants.SDK.IPHONEOS

  try:
    app_under_test_dir, test_bundle_dir = _PrepareBundles(
        work_dir, app_under_test_path, test_bundle_path)
    if not test_type:
      test_type = _DetectTestType(test_bundle_dir)
      logging.info('Will consider the test as test type %s to run.', test_type)

    # xctestrun can only support in Xcode 8+.
    # xctestrun approach is more flexiable to local debug and is easy to support
    # tests_to_run feature. So in Xcode 8+, use xctestrun approach to run
    # XCTest; in Xcode < 8, still use dummy project approach to run XCTest.
    if (test_type == ios_constants.TestType.XCUITEST or
        (test_type == ios_constants.TestType.XCTEST and
         xcode_info_util.GetXcodeVersionNumber() >= 800)):
      runner = xctestrun.XctestRun(app_under_test_dir, test_bundle_dir, sdk,
                                   test_type, work_dir)
      runner.SetEnvVarDict(launch_options.get('env_vars'))
      runner.SetArgs(launch_options.get('args'))
      runner.SetTestsToRun(launch_options.get('tests_to_run'))
      runner.Run(device_id, output_dir)
    elif test_type == ios_constants.TestType.XCTEST:
      # TODO(albertdai): Add tests_to_run support.
      dummy_project_instance = dummy_project.DummyProject(
          app_under_test_dir, test_bundle_dir, sdk,
          ios_constants.TestType.XCTEST, work_dir)
      dummy_project_instance.SetEnvVars(launch_options.get('env_vars'))
      dummy_project_instance.SetArgs(launch_options.get('args'))
      dummy_project_instance.RunXcTest(device_id, work_dir, output_dir)
    else:
      raise ios_errors.IllegalArgumentError(
          'The test type %s is not supported. Supported test types are %s'
          % (test_type, ios_constants.SUPPORTED_TEST_TYPES))
  finally:
    if delete_work_dir:
      shutil.rmtree(work_dir)
    if delete_output_dir:
      shutil.rmtree(output_dir)


def main(argv):
  args = _BuildParser().parse_args(argv[1:])
  if args.verbose:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')
  else:
    logging.basicConfig(format='%(asctime)s %(message)s')
  args.func(args)
  logging.info('Done.')


if __name__ == '__main__':
  sys.exit(main(sys.argv))
