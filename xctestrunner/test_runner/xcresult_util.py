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

"""Helper class for parsing xcresult under Xcode 11 or later."""

import json
import subprocess

from xctestrunner.shared import ios_errors


def ExposeDiagnosticsRef(xcresult_path, output_path):
  """Exposes the DiagnosticsRef files from the given xcresult file."""
  output = subprocess.check_output([
      'xcrun', 'xcresulttool', 'get', '--format', 'json', '--path',
      xcresult_path
  ])
  result_bundle_json = json.loads(output)
  actions = result_bundle_json['actions']['_values']
  action_result = None
  for action in actions:
    if action['_type']['_name'] == 'ActionRecord':
      action_result = action['actionResult']
      break
  if action_result is None:
    raise ios_errors.XcresultError(
        'Failed to get "ActionResult" from result bundle %s' % output)

  diagnostics_id = action_result['diagnosticsRef']['id']['_value']
  subprocess.check_call([
      'xcrun', 'xcresulttool', 'export', '--path', xcresult_path,
      '--output-path', output_path, '--type', 'directory', '--id',
      diagnostics_id
  ])
