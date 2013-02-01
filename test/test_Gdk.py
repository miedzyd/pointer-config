#!/usr/bin/python
#
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

from pointerconfig import Gdk
from pointerconfig.Gdk import GdkX11
from gi.repository import Gtk

class App(object):

    def __init__(self):
        display = Gdk.Display.get_default()
        manager = display.get_device_manager()
        screen = Gdk.Screen.get_default()
        for device in manager.list_devices(Gdk.DeviceType.SLAVE):
            self.print_device(manager, device)

        print 'handler:', manager.connect('device-added', self.print_device)
        print 'handler:', manager.connect('device-changed', self.print_device)
        print 'handler:', screen.connect('size-changed', self.print_screen)

    def print_device(self, manager, device):
        xid = GdkX11.gdk_x11_device_get_id(device)
        print xid, device.get_source().value_nick + ':', device.get_name()

    def print_screen(self, screen):
        print screen.get_width(), screen.get_height()

app = App()
Gtk.main()
