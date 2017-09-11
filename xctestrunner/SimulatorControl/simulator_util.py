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

"""The utility class for simulator."""

import ast
import logging
import os
import pwd
import shutil
import subprocess
import time

from xctestrunner.Shared import ios_constants
from xctestrunner.Shared import ios_errors
from xctestrunner.Shared import plist_util
from xctestrunner.Shared import xcode_info_util


_SIMULATOR_STATES_MAPPING = {0: ios_constants.SimState.CREATING,
                             1: ios_constants.SimState.SHUTDOWN,
                             3: ios_constants.SimState.BOOTED}
_PREFIX_RUNTIME_ID = 'com.apple.CoreSimulator.SimRuntime.'
_SIM_OPERATION_MAX_ATTEMPTS = 3
_SIMULATOR_CREATING_TO_SHUTDOWN_TIMEOUT_SEC = 10
_SIMULATOR_SHUTDOWN_TIMEOUT_SEC = 30
_SIM_ERROR_RETRY_INTERVAL_SEC = 2
_SIM_CHECK_STATE_INTERVAL_SEC = 0.5


class Simulator(object):
  """The object for simulator in MacOS."""

  def __init__(self, simulator_id):
    """Constructor of Simulator object.

    Args:
      simulator_id: string, the identity of the simulator.
    """
    self._simulator_id = simulator_id
    self._simulator_root_dir = None
    self._simulator_log_root_dir = None
    self._device_plist_object = None

  @property
  def simulator_id(self):
    if not self._simulator_id:
      raise ios_errors.SimError(
          'The simulator has not been created or has been deleted.')
    return self._simulator_id

  @property
  def simulator_root_dir(self):
    """Gets the simulator's root directory."""
    if not self._simulator_root_dir:
      home_dir = pwd.getpwuid(os.geteuid()).pw_dir
      self._simulator_root_dir = os.path.join(
          '%s/Library/Developer/CoreSimulator/Devices/%s'
          % (home_dir, self.simulator_id))
    return self._simulator_root_dir

  @property
  def simulator_log_root_dir(self):
    """Gets the root directory of the simulator's logs."""
    if not self._simulator_log_root_dir:
      home_dir = pwd.getpwuid(os.geteuid()).pw_dir
      self._simulator_log_root_dir = os.path.join(
          '%s/Library/Logs/CoreSimulator/%s'
          % (home_dir, self.simulator_id))
    return self._simulator_log_root_dir

  @property
  def device_plist_object(self):
    """Gets the plist_util.Plist object of device.plist of the simulator.

    Returns:
      a plist_util.Plist object of device.plist of the simulator or None when
      the simulator does not exist or is being created.
    """
    if not self._device_plist_object:
      device_plist_path = os.path.join(self.simulator_root_dir, 'device.plist')
      if not os.path.exists(device_plist_path):
        return None
      self._device_plist_object = plist_util.Plist(device_plist_path)
    return self._device_plist_object

  def Shutdown(self):
    """Shuts down the simulator."""
    sim_state = self._GetSimulatorState()
    if sim_state == ios_constants.SimState.SHUTDOWN:
      logging.info('Simulator %s has already shut down.', self.simulator_id)
      return
    if sim_state == ios_constants.SimState.CREATING:
      raise ios_errors.SimError(
          'Can not shut down the simulator in state CREATING.')
    logging.info('Shutting down simulator %s.', self.simulator_id)
    try:
      subprocess.check_output(
          ['xcrun', 'simctl', 'shutdown', self.simulator_id],
          stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
      if 'Unable to shut down device in current state: Shutdown' in e.output:
        logging.info('Simulator %s has already shut down.', self.simulator_id)
        return
      raise ios_errors.SimError(e.output)
    self.WaitUntilStateShutdown()
    logging.info('Shut down simulator %s.', self.simulator_id)

  def Delete(self):
    """Deletes the simulator.

    The simulator state should be SHUTDOWN when deleting it. Otherwise, it will
    raise exception.

    Raises:
      ios_errors.SimError: The simulator's state is not SHUTDOWN.
    """
    sim_state = self._GetSimulatorState()
    if sim_state != ios_constants.SimState.SHUTDOWN:
      raise ios_errors.SimError(
          'Can only delete the simulator with state SHUTDOWN. The current '
          'state of simulator %s is %s.' % (self._simulator_id, sim_state))
    subprocess.check_call(['xcrun', 'simctl', 'delete', self.simulator_id])
    # The delete command won't delete the simulator log directory.
    if os.path.exists(self.simulator_log_root_dir):
      shutil.rmtree(self.simulator_log_root_dir)
    logging.info('Deleted simulator %s.', self.simulator_id)
    self._simulator_id = None

  def WaitUntilStateShutdown(self, timeout_sec=_SIMULATOR_SHUTDOWN_TIMEOUT_SEC):
    """Waits until the simulator state becomes SHUTDOWN.

    Args:
      timeout_sec: int, timeout of waiting simulator state for becoming
          SHUTDOWN in seconds.

    Raises:
      ios_errors.SimError: when it is timeout to wait the simulator state
          becomes SHUTDOWN.
    """
    start_time = time.time()
    while start_time + timeout_sec >= time.time():
      if self._GetSimulatorState() == ios_constants.SimState.SHUTDOWN:
        return
      time.sleep(_SIM_CHECK_STATE_INTERVAL_SEC)
    raise ios_errors.SimError(
        'Timeout to wait for simulator shutdown in %ss.' % timeout_sec)

  def _GetSimulatorState(self):
    """Gets the state of the simulator in real time.

    Returns:
      Shared.ios_constants.SimState, the state of the simulator.

    Raises:
      ios_errors.SimError: The state can not be recognized.
    """
    if self.device_plist_object is None:
      return ios_constants.SimState.CREATING
    state_num = self.device_plist_object.GetPlistField('state')
    if state_num not in _SIMULATOR_STATES_MAPPING.keys():
      logging.warning(
          'The state %s of simulator %s can not be recognized.',
          state_num, self.simulator_id)
      return ios_constants.SimState.UNKNOWN
    return _SIMULATOR_STATES_MAPPING[state_num]


def CreateNewSimulator(simulator_type=None, os_version=None, name=None):
  """Creates a new simulator according to arguments.

  Args:
    simulator_type: string, type of the new simulator, such as iPhone 6,
        iPad Air, etc. By default, will use the latest iPhone.
    os_version: string, OS version of the new simulator. By default, will use
        the latest supported OS version of simulator type.
    name: string, name of the new simulator. By default, it will be the value of
        concatenating simulator_type with os_version.
        E.g., NEW_IPHONE_6_PLUS_10_2.

  Returns:
    string, id of the new simulator.

  Raises:
    ios_errors.SimError: when failed to create new simulator.
    ios_errors.IllegalArgumentError: when the given argument is invalid.
  """
  if not simulator_type:
    simulator_type = GetLastSupportedSimType(ios_constants.OS.IOS)
  else:
    ValidateSimulatorType(simulator_type)
  os_type = GetOsType(simulator_type)
  if not os_version:
    os_version = GetLastSupportedSimOsVersion(os_type)
  else:
    supported_sim_os_versions = GetSupportedSimOsVersions(os_type)
    if os_version not in supported_sim_os_versions:
      raise ios_errors.IllegalArgumentError(
          'The simulator os version %s is not supported. Supported simulator '
          'os versions are %s.' % (os_version, supported_sim_os_versions))
  if not name:
    # Example: NEW_IPHONE6S_PLUS_10_3
    name = 'NEW_%s_%s' % (simulator_type, os_version)
    name = name.replace('.', '_').replace(' ', '_').upper()

  # Example
  # Runtime ID of iOS 10.2: com.apple.CoreSimulator.SimRuntime.iOS-10-2
  runtime_id = _PREFIX_RUNTIME_ID + os_type + '-' + os_version.replace('.', '-')
  logging.info('Creating a new simulator:\nName: %s\nOS: %s %s\nType: %s',
               name, os_type, os_version, simulator_type)
  for i in range(0, _SIM_OPERATION_MAX_ATTEMPTS):
    new_simulator_id = subprocess.check_output(
        ['xcrun', 'simctl', 'create', name, simulator_type, runtime_id]).strip()
    new_simulator_obj = Simulator(new_simulator_id)
    # After creating a new simulator, its state is CREATING. When the
    # simulator's state becomes SHUTDOWN, the simulator is created.
    try:
      new_simulator_obj.WaitUntilStateShutdown(
          _SIMULATOR_CREATING_TO_SHUTDOWN_TIMEOUT_SEC)
      logging.info('Created new simulator %s.', new_simulator_id)
      return new_simulator_id
    except ios_errors.SimError as error:
      logging.debug('Failed to create simulator %s: %s.',
                    new_simulator_id, error)
      logging.debug('Deleted half-created simulator %s.', new_simulator_id)
      new_simulator_obj.Delete()
      if i != _SIM_OPERATION_MAX_ATTEMPTS - 1:
        logging.debug('Will sleep %ss and retry again.',
                      _SIM_ERROR_RETRY_INTERVAL_SEC)
        # If the simulator's state becomes SHUTDOWN, there may be something
        # wrong in CoreSimulatorService. Sleeps a short interval(2s) can help
        # reduce flakiness.
        time.sleep(_SIM_ERROR_RETRY_INTERVAL_SEC)
  raise ios_errors.SimError('Failed to create simulator in %d attempts.'
                            % _SIM_OPERATION_MAX_ATTEMPTS)


def GetSupportedSimTypes(os_type=None):
  """Gets the name list of supported simulator types of given OS type.

  If os_type is not provided, it will return all supported simulator types.
  The names are got from command result of `xcrun simctl list devices`. So some
  simulator types' name may be different in different Xcode. E.g., the name
  of iPad Pro (12.9-inch) in Xcode 7.2.1 is "iPad Pro", but it is
  "iPad Pro (12.9-inch)" in Xcode 8+.

  Args:
    os_type: Shared.ios_constants.OS, os type of simulator, such as iOS,
      watchOS, tvOS.

  Returns:
    a list of string, each item is a simulator type.
    E.g., ["iPhone 5", "iPhone 6 Plus"]
  """
  # Example output:
  # {
  #   "devicetypes" : [
  #    {
  #      "name" : "iPhone 5",
  #      "identifier" : "com.apple.CoreSimulator.SimDeviceType.iPhone-5"
  #    }
  #   ]
  # }
  #
  # See more examples in testdata/simctl_list_devicetypes.json
  sim_types_infos_json = ast.literal_eval(
      subprocess.check_output(
          ('xcrun', 'simctl', 'list', 'devicetypes', '-j')))
  sim_types = []
  for sim_types_info in sim_types_infos_json['devicetypes']:
    sim_type = sim_types_info['name']
    if (os_type is None or
        (os_type == ios_constants.OS.IOS and sim_type.startswith('i')) or
        (os_type == ios_constants.OS.TVOS and 'TV' in sim_type) or
        (os_type == ios_constants.OS.WATCHOS and 'Watch' in sim_type)):
      sim_types.append(sim_type)
  return sim_types


def GetLastSupportedSimType(os_type=ios_constants.OS.IOS):
  """"Gets the last supported simulator type of given OS type.

  Args:
    os_type: Shared.ios_constants.OS, os type of simulator, such as iOS,
      watchOS, tvOS.

  Returns:
    a string, the last supported simulator type of simulator os type.
  """
  supported_sim_types = GetSupportedSimTypes(os_type)
  return supported_sim_types[-1]


def GetSupportedSimOsVersions(os_type=ios_constants.OS.IOS):
  """Gets the supported version of given simulator OS type.

  Args:
    os_type: Shared.ios_constants.OS, os type of simulator, such as iOS,
      watchOS, tvOS.

  Returns:
    a list of string, each item is an OS version number. E.g., ["10.1", "11.0"]
  """
  # Example output:
  # {
  #   "runtimes" : [
  #     {
  #       "buildversion" : "12B411",
  #       "availability" : "(available)",
  #       "name" : "iOS 8.1",
  #       "identifier" : "com.apple.CoreSimulator.SimRuntime.iOS-8-1",
  #       "version" : "8.1"
  #     },
  #   ]
  #  }
  #
  # See more examples in testdata/simctl_list_runtimes.json
  sim_runtime_infos_json = ast.literal_eval(
      subprocess.check_output(
          ('xcrun', 'simctl', 'list', 'runtimes', '-j')))
  sim_versions = []
  for sim_runtime_info in sim_runtime_infos_json['runtimes']:
    # Normally, the json does not contain unavailable runtimes. To be safe,
    # also checks the 'availability' field.
    if sim_runtime_info['availability'].find('unavailable') >= 0:
      continue
    listed_os_type, listed_os_version = sim_runtime_info['name'].split(' ', 1)
    if listed_os_type == os_type:
      sim_versions.append(listed_os_version)
  return sim_versions


def GetLastSupportedSimOsVersion(os_type=ios_constants.OS.IOS):
  """Gets the last supported version of given simulator OS type.

  Args:
    os_type: Shared.ios_constants.OS, os type of simulator, such as iOS,
      watchOS, tvOS.

  Returns:
    a string, the last supported version of simulator os type.
  """
  supported_iossim_os_versions = GetSupportedSimOsVersions(os_type)
  return supported_iossim_os_versions[-1]


def GetOsType(simulator_type):
  """Gets the OS type of the given simulator.

  This method can not work fine if the simulator_type is invalid. Please calls
  simulator_util.ValidateSimulatorType(simulator_type) to validate it first.

  Args:
    simulator_type: string, type of the new simulator, such as iPhone 6,
        iPad Air, etc.

  Returns:
    Shared.ios_constants.OS.

  Raises:
    ios_errors.IllegalArgumentError: when the os type of the given simulator
        type can not be recognized.
  """
  if simulator_type.startswith('i'):
    return ios_constants.OS.IOS
  if 'TV' in simulator_type:
    return ios_constants.OS.TVOS
  if 'Watch' in simulator_type:
    return ios_constants.OS.WATCHOS
  raise ios_errors.IllegalArgumentError(
      'Failed to recognize the os type for simulator type %s.' % simulator_type)


def ValidateSimulatorType(simulator_type):
  """Checks if the simulator type is valid.

  Args:
    simulator_type: string, type of the new simulator, such as iPhone 6,
        iPad Air, etc.

  Raises:
    ios_errors.IllegalArgumentError: when the given simulator type is invalid.
  """
  supported_sim_types = GetSupportedSimTypes()
  if simulator_type not in supported_sim_types:
    raise ios_errors.IllegalArgumentError(
        'The simulator type %s is not supported. Supported simulator types '
        'are %s.' % (simulator_type, supported_sim_types))


def QuitSimulatorApp():
  """Quits the Simulator.app."""
  if xcode_info_util.GetXcodeVersionNumber() >= 700:
    simulator_name = 'Simulator'
  else:
    simulator_name = 'iOS Simulator'
  subprocess.Popen(['killall', simulator_name],
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
