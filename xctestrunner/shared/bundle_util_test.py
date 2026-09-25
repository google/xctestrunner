# Copyright 2026 Google Inc.
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

"""Tests for bundle signing identity selection and error reporting."""

import os
import subprocess
import unittest
from unittest import mock

from xctestrunner.shared import bundle_util
from xctestrunner.shared import ios_errors


class BundleUtilTest(unittest.TestCase):

  @mock.patch.object(bundle_util.subprocess, 'check_output')
  def test_get_codesign_identity_uses_leaf_certificate(self, check_output):
    certificate_dirs = []

    def extract_certificates(command, **kwargs):
      self.assertEqual(command[:2], ['codesign', '-d'])
      self.assertEqual(command[3:], ['/tmp/Test.app'])
      self.assertEqual(kwargs, {'stderr': subprocess.STDOUT})
      self.assertTrue(command[2].startswith('--extract-certificates='))
      prefix = command[2].split('=', 1)[1]
      certificate_dirs.append(os.path.dirname(prefix))
      # Use a known SHA-1 test vector for the leaf, and different issuer bytes.
      with open(prefix + '0', 'wb') as certificate:
        certificate.write(b'abc')
      with open(prefix + '1', 'wb') as certificate:
        certificate.write(b'issuer')
      return 'Authority=Apple Development: Example Šigner\n'.encode('utf-8')

    check_output.side_effect = extract_certificates
    self.assertEqual(bundle_util.GetCodesignIdentity('/tmp/Test.app'),
                     'a9993e364706816aba3e25717850c26c9cd0d89d')
    check_output.assert_called_once()
    self.assertFalse(os.path.exists(certificate_dirs[0]))

  @mock.patch.object(bundle_util.subprocess, 'check_output')
  def test_get_codesign_identity_reports_extraction_failure(self, check_output):
    check_output.side_effect = subprocess.CalledProcessError(
        1, ['codesign'], output=b'code object is not signed at all\xff')
    with self.assertRaisesRegex(ios_errors.BundleError,
                                'code object is not signed at all'):
      bundle_util.GetCodesignIdentity('/tmp/Test.app')
    prefix = check_output.call_args.args[0][2].split('=', 1)[1]
    self.assertFalse(os.path.exists(os.path.dirname(prefix)))

  @mock.patch.object(bundle_util.subprocess, 'check_output', return_value=b'')
  def test_get_codesign_identity_reports_missing_certificate(self, check_output):
    with self.assertRaisesRegex(ios_errors.BundleError,
                                'Failed to read signing certificate'):
      bundle_util.GetCodesignIdentity('/tmp/Test.app')

  @mock.patch.object(bundle_util.subprocess, 'check_output', return_value=b'')
  @mock.patch.object(bundle_util, 'GetCodesignIdentity', return_value='fingerprint')
  def test_codesign_bundle_uses_extracted_identity(self, get_identity,
                                                check_output):
    bundle_util.CodesignBundle('/tmp/Test.app')
    get_identity.assert_called_once_with('/tmp/Test.app')
    check_output.assert_called_once_with(
        ['codesign', '-f', '--preserve-metadata=identifier,entitlements',
         '--timestamp=none', '-s', 'fingerprint', '/tmp/Test.app'],
        stderr=subprocess.STDOUT)

  @mock.patch.object(bundle_util.subprocess, 'check_output', return_value=b'')
  @mock.patch.object(bundle_util, 'GetCodesignIdentity')
  def test_codesign_bundle_preserves_explicit_identity_and_entitlements(
      self, get_identity, check_output):
    bundle_util.CodesignBundle('/tmp/Test.app', '/tmp/entitlements.plist',
                               identity='explicit identity')
    get_identity.assert_not_called()
    check_output.assert_called_once_with(
        ['codesign', '-f', '--entitlements', '/tmp/entitlements.plist',
         '--timestamp=none', '-s', 'explicit identity', '/tmp/Test.app'],
        stderr=subprocess.STDOUT)

  @mock.patch.object(bundle_util.subprocess, 'check_output')
  def test_codesign_bundle_reports_failure_output(self, check_output):
    check_output.side_effect = subprocess.CalledProcessError(
        1, ['codesign'], output=b'no identity found\xff')
    for entitlements in (None, '/tmp/entitlements.plist'):
      with self.subTest(entitlements=entitlements):
        with self.assertRaisesRegex(ios_errors.BundleError, 'no identity found'):
          bundle_util.CodesignBundle('/tmp/Test.app', entitlements,
                                     identity='fingerprint')


if __name__ == '__main__':
  unittest.main()
