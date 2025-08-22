#!/usr/bin/env python3
"""
Unit tests for simulator_util.py functions using mocked dependencies.
"""

import unittest
from unittest import mock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from xctestrunner.simulator_control import simulator_util
from xctestrunner.shared import ios_errors


class MockSimTypeProfile:
    """Mock SimTypeProfile for testing with guaranteed ordering."""
    
    def __init__(self, device_type):
        self.device_type = device_type
        # Use array of tuples for guaranteed ordering (device, min_os, max_os)
        # None for max_os means no upper limit
        self._device_specs = [
            ('iPhone 16 Pro', 18.0, None),
            ('iPhone 16', 18.0, None),
            ('iPhone 15 Pro', 17.0, None),
            ('iPhone 15', 17.0, None),
            ('iPhone 14 Pro', 16.0, None),
            ('iPhone 14', 16.0, None),
            ('iPhone 13 Pro', 15.0, None),
            ('iPhone 13', 15.0, None),
            ('iPhone SE (3rd generation)', 15.4, None),
            ('iPhone 12 Pro', 14.1, None),
            ('iPhone 12', 14.1, None),
            ('iPhone SE (2nd generation)', 13.4, None),
            ('iPhone 11 Pro', 13.0, None),
            ('iPhone 11', 13.0, None),
            ('iPhone Xs', 12.0, 16.99),
            ('iPhone X', 11.0, 16.99),
            ('iPhone 8', 11.0, 16.99),
            ('iPhone 7', 10.0, 15.99),
            ('iPhone SE (1st generation)', 9.3, 15.99),
            ('iPhone 6s', 9.0, 15.99),
            ('iPhone 6s Plus', 9.0, 15.99),
        ]
    
    def _get_device_spec(self):
        for device, min_os, max_os in self._device_specs:
            if device == self.device_type:
                return min_os, max_os
        return 9.0, None
    
    @property
    def min_os_version(self):
        min_os, _ = self._get_device_spec()
        return min_os
    
    @property
    def max_os_version(self):
        _, max_os = self._get_device_spec()
        return max_os


class TestGetLastSupportedIphoneSimType(unittest.TestCase):
    """Test cases for GetLastSupportedIphoneSimType function with mocking."""

    def setUp(self):
        """Set up mock data for consistent testing."""
        self.mock_devices = [
            'iPhone 16 Pro', 'iPhone 16', 'iPhone 15 Pro', 'iPhone 15',
            'iPhone 14 Pro', 'iPhone 14', 'iPhone 13 Pro', 'iPhone 13',
            'iPhone SE (3rd generation)', 'iPhone 12 Pro', 'iPhone 12',
            'iPhone SE (2nd generation)', 'iPhone 11 Pro', 'iPhone 11',
            'iPhone Xs', 'iPhone X', 'iPhone 8', 'iPhone 7',
            'iPhone SE (1st generation)', 'iPhone 6s', 'iPhone 6s Plus',
            # Also include non-iPhone devices to test filtering
            'iPad Pro', 'iPad Air', 'Apple Watch Series 9'
        ]

    @mock.patch('xctestrunner.simulator_control.simtype_profile.SimTypeProfile')
    @mock.patch('xctestrunner.simulator_control.simulator_util.GetSupportedSimDeviceTypes')
    def test_ios_18_5_returns_newest_compatible(self, mock_get_devices, mock_profile):
        """Test iOS 18.5 returns newest iPhone that supports it."""
        mock_get_devices.return_value = self.mock_devices
        mock_profile.side_effect = MockSimTypeProfile
        
        result = simulator_util.GetLastSupportedIphoneSimType("18.5")
        self.assertEqual(result, "iPhone 16 Pro")

    @mock.patch('xctestrunner.simulator_control.simtype_profile.SimTypeProfile')
    @mock.patch('xctestrunner.simulator_control.simulator_util.GetSupportedSimDeviceTypes')
    def test_ios_16_0_respects_max_version(self, mock_get_devices, mock_profile):
        """Test iOS 16.0 correctly handles max_os_version limits."""
        mock_get_devices.return_value = self.mock_devices
        mock_profile.side_effect = MockSimTypeProfile
        
        result = simulator_util.GetLastSupportedIphoneSimType("16.0")
        self.assertEqual(result, "iPhone 14 Pro")

    @mock.patch('xctestrunner.simulator_control.simtype_profile.SimTypeProfile')
    @mock.patch('xctestrunner.simulator_control.simulator_util.GetSupportedSimDeviceTypes')
    def test_critical_bug_regression_iphone_6s_plus(self, mock_get_devices, mock_profile):
        """Regression test: iPhone 6s Plus should NOT be returned for iOS 18.5."""
        mock_get_devices.return_value = self.mock_devices
        mock_profile.side_effect = MockSimTypeProfile
        
        result = simulator_util.GetLastSupportedIphoneSimType("18.5")
        
        # Regression test: iPhone 6s Plus should NOT be returned for iOS 18.5
        self.assertNotEqual(result, "iPhone 6s Plus",
                          "iPhone 6s Plus cannot run iOS 18.5 (max OS 15.99)")
        self.assertEqual(result, "iPhone 16 Pro")

    @mock.patch('xctestrunner.simulator_control.simtype_profile.SimTypeProfile')
    @mock.patch('xctestrunner.simulator_control.simulator_util.GetSupportedSimDeviceTypes')
    def test_no_compatible_devices(self, mock_get_devices, mock_profile):
        """Test when no devices support the requested iOS version."""
        limited_devices = ['iPhone 6s Plus', 'iPhone 7', 'iPhone X']
        mock_get_devices.return_value = limited_devices
        mock_profile.side_effect = MockSimTypeProfile
        
        with self.assertRaises(ios_errors.SimError):
            simulator_util.GetLastSupportedIphoneSimType("25.0")

    @mock.patch('xctestrunner.simulator_control.simtype_profile.SimTypeProfile')
    @mock.patch('xctestrunner.simulator_control.simulator_util.GetSupportedSimDeviceTypes')
    def test_no_iphones_available(self, mock_get_devices, mock_profile):
        """Test when no iPhone simulators are available."""
        mock_get_devices.return_value = ['iPad Pro', 'iPad Air', 'Apple Watch Series 9']
        mock_profile.side_effect = MockSimTypeProfile
        
        with self.assertRaises(ios_errors.SimError):
            simulator_util.GetLastSupportedIphoneSimType("16.0")

    def test_invalid_version_format(self):
        """Test with invalid iOS version format."""
        with self.assertRaises(ValueError):
            simulator_util.GetLastSupportedIphoneSimType("invalid")
        
        with self.assertRaises(ValueError):
            simulator_util.GetLastSupportedIphoneSimType("not.a.number")


if __name__ == '__main__':    
    unittest.main()
