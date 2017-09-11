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

"""Utility class for managing Plist files."""

import logging
import plistlib
import subprocess
import xml.parsers.expat

try:
  # pylint: disable=g-import-not-at-top
  import biplist
except ImportError:
  biplist = None

from xctestrunner.Shared import ios_errors


PLIST_BUDDY = '/usr/libexec/PlistBuddy'


class Plist(object):
  """Handles the .plist file operations."""

  def __init__(self, plist_file_path):
    """Initializes the Plist object.

    Args:
      plist_file_path: string, the path of the .plist file.
    """
    self._plist_file_path = plist_file_path
    # Module to read the .plist file.
    self._plistlib_module = _GetPlistLibModule(plist_file_path)

  def GetPlistField(self, field):
    """View specific field in the .plist file.

    Args:
      field: string, the field consist of property key names delimited by
        colons. List(array) items are specified by a zero-based integer index.
        Examples
          :CFBundleShortVersionString
          :CFBundleDocumentTypes:2:CFBundleTypeExtensions

    Returns:
      the object of the plist's field.

    Raises:
      PlistError: the field does not exist in the plist dict.
    """
    if self._plistlib_module is None:
      return _GetPlistFieldByPlistBuddy(self._plist_file_path, field)
    plist_root_object = self._plistlib_module.readPlist(self._plist_file_path)
    return _GetObjectWithField(plist_root_object, field)

  def SetPlistField(self, field, value):
    """Set field with provided value in .plist file.

    Args:
      field: string, the field consist of property key names delimited by
        colons. List(array) items are specified by a zero-based integer index.
        Examples
          :CFBundleShortVersionString
          :CFBundleDocumentTypes:2:CFBundleTypeExtensions
      value: a object, the value of the field to be added. It can be integer,
          bool, string, array, dict.

    Raises:
      PlistError: the field does not exist in the .plist file's dict.
    """
    if self._plistlib_module is None:
      _SetPlistFieldByPlistBuddy(self._plist_file_path, field, value)
      return

    plist_root_object = self._plistlib_module.readPlist(self._plist_file_path)
    keys_in_field = field.rsplit(':', 1)
    if len(keys_in_field) == 1:
      key = field
      target_object = plist_root_object
    else:
      key = keys_in_field[1]
      target_object = _GetObjectWithField(plist_root_object, keys_in_field[0])
    try:
      target_object[_ParseKey(target_object, key)] = value
    except ios_errors.PlistError as e:
      raise e
    except (KeyError, IndexError):
      raise ios_errors.PlistError('Failed to set key %s from object %s.'
                                  % (key, target_object))
    self._plistlib_module.writePlist(plist_root_object, self._plist_file_path)

  def DeletePlistField(self, field):
    """Delete field in .plist file.

    Args:
      field: string, the field consist of property key names delimited by
        colons. List(array) items are specified by a zero-based integer index.
        Examples
          :CFBundleShortVersionString
          :CFBundleDocumentTypes:2:CFBundleTypeExtensions

    Raises:
      PlistError: the field does not exist in the .plist file's dict.
    """
    if self._plistlib_module is None:
      _DeletePlistFieldByPlistBuddy(self._plist_file_path, field)
      return

    plist_root_object = self._plistlib_module.readPlist(self._plist_file_path)
    keys_in_field = field.rsplit(':', 1)
    if len(keys_in_field) == 1:
      key = field
      target_object = plist_root_object
    else:
      key = keys_in_field[1]
      target_object = _GetObjectWithField(plist_root_object, keys_in_field[0])

    try:
      del target_object[_ParseKey(target_object, key)]
    except ios_errors.PlistError as e:
      raise e
    except (KeyError, IndexError):
      raise ios_errors.PlistError('Failed to delete key %s from object %s.'
                                  % (key, target_object))

    self._plistlib_module.writePlist(plist_root_object, self._plist_file_path)


def _GetObjectWithField(target_object, field):
  """Gets sub object of the object with field.

  Args:
    target_object: the target object.
    field: string, the field consist of property key names delimited by
        colons. List(array) items are specified by a zero-based integer index.
        Examples
          :CFBundleShortVersionString
          :CFBundleDocumentTypes:2:CFBundleTypeExtensions

  Returns:
    a object of the target object's field. If field is empty, returns the
      target object itself.

  Raises:
    PlistError: the field does not exist in the object or the field is invaild.
  """
  if not field:
    return target_object
  current_object = target_object
  for key in field.split(':'):
    try:
      current_object = current_object[_ParseKey(current_object, key)]
    except ios_errors.PlistError as e:
      raise e
    except (KeyError, IndexError):
      raise ios_errors.PlistError(
          'The field %s can not be found in the target object. '
          'The object content is %s' % (field, current_object))
  return current_object


def _ParseKey(target_object, key):
  """Parses the key value according target object type.

  Args:
    target_object: the target object.
    key: string, the key of object.

  Returns:
    If object is dict, returns key itself. If object is list, returns int(key).

  Raises:
    PlistError: when object is list and key is not int, or object is not list/
      dict.
  """
  if isinstance(target_object, dict):
    return key
  if isinstance(target_object, list):
    try:
      return int(key)
    except ValueError:
      raise ios_errors.PlistError(
          'The key %s is invaild index of list(array) object %s.'
          % (key, target_object))
  raise ios_errors.PlistError('The object %s is not dict or list.'
                              % target_object)


def _GetPlistLibModule(plist_file_path):
  """Gets the module to read the target .plist file.

  .plist file has two kinds of format: XML format and binary format. If the
  .plist file is XML format, it should be read by plistlib and don't use
  biplist which will change XML format plist to binary plist.

  Args:
    plist_file_path: string, full path of the .plist file.

  Returns:
    a module to read the target .plist file or None if the model can not be
      imported.
  """
  try:
    plistlib.readPlist(plist_file_path)
    return plistlib
  except xml.parsers.expat.ExpatError:
    if biplist is None:
      logging.info(
        'Failed to import biplist module. Will use tool %s to handle the '
        'binary format plist.',
        PLIST_BUDDY)
    return biplist


def _GetPlistFieldByPlistBuddy(plist_path, field):
  """View specific field in the .plist file by PlistBuddy tool.

  Args:
    plist_path: string, the path of plist file.
    field: string, the field consist of property key names delimited by
      colons. List(array) items are specified by a zero-based integer index.
      Examples
        :CFBundleShortVersionString
        :CFBundleDocumentTypes:2:CFBundleTypeExtensions

  Returns:
    the object of the plist's field.
  """
  command = [PLIST_BUDDY, '-c', 'Print :"%s"' % field, plist_path]
  try:
    return subprocess.check_output(command).strip()
  except subprocess.CalledProcessError:
    return ''


def _SetPlistFieldByPlistBuddy(plist_path, field, value):
  """Set field with provided value in .plist file.

  Args:
    plist_path: string, the path of plist file.
    field: string, the field consist of property key names delimited by
      colons. List(array) items are specified by a zero-based integer index.
      Examples
        :CFBundleShortVersionString
        :CFBundleDocumentTypes:2:CFBundleTypeExtensions
    value: a object, the value of the field to be added. It can be integer,
        bool, string, array, dict.

  Raises:
    PlistError: the field does not exist in the .plist file's dict.
  """
  command = [PLIST_BUDDY, '-c', 'Set :"%s" "%s"' % (field, value), plist_path]
  try:
    subprocess.check_output(command)
  except subprocess.CalledProcessError as e:
    raise ios_errors.PlistError('PlistBuddy error: %s' % e.output)


def _DeletePlistFieldByPlistBuddy(plist_path, field):
  """Delete field in .plist file.

  Args:
    plist_path: string, the path of plist file.
    field: string, the field consist of property key names delimited by
      colons. List(array) items are specified by a zero-based integer index.
      Examples
        :CFBundleShortVersionString
        :CFBundleDocumentTypes:2:CFBundleTypeExtensions

  Raises:
    PlistError: the field does not exist in the .plist file's dict.
  """
  command = [PLIST_BUDDY, '-c', 'Delete :"%s"' % field, plist_path]
  try:
    subprocess.check_output(command)
  except subprocess.CalledProcessError as e:
    raise ios_errors.PlistError('PlistBuddy error: %s' % e.output)
