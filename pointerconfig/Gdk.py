# Copyright (C) 2012 Daniel Miedzyblocki
#
# This file is part of Pointer Config.
#
# Pointer Config is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Pointer Config is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Pointer Config.  If not, see <http://www.gnu.org/licenses/>.

import ctypes
import ctypes.util

from gi.repository import Gdk
from gi.repository.Gdk import GrabOwnership
from gi.repository.Gdk import EventMask
from gi.repository.Gdk import Cursor
from gi.repository.Gdk import CursorType
from gi.repository.Gdk import CURRENT_TIME
from gi.repository.Gdk import GrabStatus
from gi.repository.Gdk import WindowTypeHint
from gi.repository.Gdk import Gravity
from gi.repository.Gdk import RGBA
from gi.repository.Gdk import DeviceType
from gi.repository.Gdk import Screen

_gdk = ctypes.CDLL(ctypes.util.find_library('gdk-3'))
_glib = ctypes.CDLL(ctypes.util.find_library('glib-2'))
_gobject = ctypes.CDLL(ctypes.util.find_library('gobject-2'))


class GdkX11(object):

    def gdk_x11_device_get_id(device):
        return _gdk.gdk_x11_device_get_id(device)

    gdk_x11_device_get_id = staticmethod(gdk_x11_device_get_id)


class Device(ctypes.c_void_p):

    def get_name(self):
        _gdk.gdk_device_get_name.restype = ctypes.c_char_p
        return _gdk.gdk_device_get_name(self)

    def get_source(self):
        _gdk.gdk_device_get_source.restype = Gdk.InputSource
        return _gdk.gdk_device_get_source(self)


class Manager(ctypes.c_void_p):

    _callback = dict()

    def append_device(self, data):
        self.device.append(data)

    def list_devices(self, device_type):
        self.device = list()
        _gdk.gdk_device_manager_list_devices.restype = ctypes.c_void_p
        glist = _gdk.gdk_device_manager_list_devices(self, device_type.real)
        prototype = ctypes.CFUNCTYPE(None, Device)
        _glib.g_list_foreach(glist, prototype(self.append_device))
        _glib.g_list_free(glist)
        device = self.device
        del self.device
        return device

    def iter_devices(self, device_type):
        ''' iterate over devices, causes seg fault in some cases '''
        _gdk.gdk_device_manager_list_devices.restype = ctypes.c_void_p
        head = _gdk.gdk_device_manager_list_devices(self, device_type.real)
        _glib.g_list_nth_data.restype = Device
        device = _glib.g_list_nth_data(head, 0)
        _glib.g_list_delete_link.restype = ctypes.c_void_p
        while device:
            yield device
            head = _glib.g_list_delete_link(head, head)
            device = _glib.g_list_nth_data(head, 0)

    def device_added(manager, device, data):
        Manager._callback['device-added'](manager, device)

    def device_changed(manager, device, data):
        Manager._callback['device-changed'](manager, device)

    device_added = staticmethod(device_added)
    device_changed = staticmethod(device_changed)

    def connect(self, signal, handler):
        call = _prototype(getattr(Manager, signal.replace('-', '_')))
        Manager._callback[signal] = handler
        _gobject.g_signal_connect_object.restype = ctypes.c_ulong
        return _gobject.g_signal_connect_object(self, signal, call, None, 0)


_prototype = ctypes.CFUNCTYPE(None, Manager, Device, ctypes.c_void_p)


class Display(ctypes.c_void_p):

    def get_default(cls):
        _gdk.gdk_display_get_default.restype = cls
        return _gdk.gdk_display_get_default()

    get_default = classmethod(get_default)

    def get_device_manager(self):
        _gdk.gdk_display_get_device_manager.restype = Manager
        return _gdk.gdk_display_get_device_manager(self)
