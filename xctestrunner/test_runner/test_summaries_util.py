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

"""Helper class for parsing TestSummaries.plist file.
"""

import glob
import os
import shutil
import tempfile

from xctestrunner.shared import plist_util


def GetTestSummariesPaths(derived_data_dir):
  """Get the TestSummaries.plist files under the DerivedData directory."""
  return glob.glob('%s/Logs/Test/*_TestSummaries.plist' % derived_data_dir)


def ParseTestSummaries(
    test_summaries_path, attachments_dir_path,
    delete_uitest_auto_screenshots=True):
  """Parse the TestSummaries.plist and structure the attachments' files.

  Only the screenshots file from failure test methods and .crash files will be
  stored. Other files will be removed.

  Args:
    test_summaries_path: string, the path of TestSummaries.plist file.
    attachments_dir_path: string, the path of Attachments directory.
    delete_uitest_auto_screenshots: bool, whether deletes the auto screenshots.
  """
  test_summaries_plist = plist_util.Plist(test_summaries_path)
  tests_obj = test_summaries_plist.GetPlistField('TestableSummaries:0:Tests:0')
  # Store the required screenshots and crash files under temp directory first.
  # Then use the temp directory to replace the original Attachments directory.
  # If delete_uitest_auto_screenshots is true, only move crash files to
  # temp directory and the left screenshots will be deleted.
  temp_dir = tempfile.mkdtemp(dir=os.path.dirname(attachments_dir_path))
  if not delete_uitest_auto_screenshots:
    _ParseTestObject(tests_obj, attachments_dir_path, temp_dir)
  for crash_file in glob.glob('%s/*.crash' % attachments_dir_path):
    shutil.move(crash_file, temp_dir)
  shutil.rmtree(attachments_dir_path)
  shutil.move(temp_dir, attachments_dir_path)


def _ParseTestObject(test_obj, attachments_dir_path, parent_test_obj_dir_path):
  """Parse the test method object and structure its attachment files."""
  test_obj_dir_path = os.path.join(
      parent_test_obj_dir_path,
      test_obj['TestIdentifier'].replace('.', '_').replace('/', '_'))
  if 'Subtests' in test_obj:
    # If the test suite only has one sub test, don't create extra folder which
    # causes extra directory hierarchy.
    if len(test_obj['Subtests']) > 1:
      if not os.path.exists(test_obj_dir_path):
        os.mkdir(test_obj_dir_path)
    else:
      test_obj_dir_path = parent_test_obj_dir_path
    for sub_test_obj in test_obj['Subtests']:
      _ParseTestObject(sub_test_obj, attachments_dir_path, test_obj_dir_path)
    return
  # Only parse the failure test methods. The succeed test method's attachment
  # files will be removed later.
  if test_obj['TestStatus'] == 'Success':
    return
  if not os.path.exists(test_obj_dir_path):
    os.mkdir(test_obj_dir_path)
  test_result_plist_path = os.path.join(test_obj_dir_path,
                                        'TestMethodResult.plist')
  plist_util.Plist(test_result_plist_path).SetPlistField('', test_obj)
  if 'ActivitySummaries' in test_obj:
    for test_activity_obj in test_obj['ActivitySummaries']:
      _ExploreTestActivity(
          test_activity_obj, attachments_dir_path, test_obj_dir_path)


def _ExploreTestActivity(test_activity_obj, attachments_dir_path,
                         test_obj_dir_path):
  """Move the screenshot files of this method to test object directory."""
  if 'HasScreenshotData' in test_activity_obj:
    screenshot_file_paths = glob.glob(
        os.path.join(
            attachments_dir_path,
            'Screenshot_%s.*' % test_activity_obj['UUID']))
    for path in screenshot_file_paths:
      shutil.move(path, test_obj_dir_path)
  if 'SubActivities' in test_activity_obj:
    for sub_test_activity_obj in test_activity_obj['SubActivities']:
      _ExploreTestActivity(
          sub_test_activity_obj, attachments_dir_path, test_obj_dir_path)
