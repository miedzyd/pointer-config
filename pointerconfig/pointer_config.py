# Copyright (C) 2012, 2013 Daniel Miedzyblocki
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

import shlex
import subprocess
import sys
import math
import array
import gettext

from pointerconfig import Gdk
from pointerconfig.Gdk import GdkX11
import cairo
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import GLib


class OutlineWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self)
        self.set_gravity(Gdk.Gravity.STATIC)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)


class Outline(object):
    def __init__(self):
        self._top, self._bottom = (OutlineWindow(), OutlineWindow())
        self._left, self._right = (OutlineWindow(), OutlineWindow())

    def transform(self, matrix, width, height):
        scale = cairo.Matrix(xx=width, yy=height)
        matrix = matrix.multiply(scale)
        x, y = map(round, matrix.transform_point(0, 0))
        x2, y2 = map(round, matrix.transform_point(1, 1))
        self.x, self.width = (min(x, x2), max(abs(x - x2), 1))
        self.y, self.height = (min(y, y2), max(abs(y - y2), 1))

    def move(self, size):
        self._top.move(self.x, self.y - size)
        self._bottom.move(self.x, self.y + self.height)
        self._left.move(self.x - size, self.y)
        self._right.move(self.x + self.width, self.y)

    def resize(self, size):
        self._top.resize(self.width, size)
        self._bottom.resize(self.width, size)
        self._left.resize(size, self.height)
        self._right.resize(size, self.height)

    def __getattr__(self, name):
        def callback(*arg):
            for window in (self._top, self._bottom, self._left, self._right):
                getattr(window, name)(*arg)
        return callback


def get_params(schema):
    matrix = list(schema.get_value('matrix'))
    matrix = matrix[0::2] + matrix[1::2] + [0, 0, 1]
    matrix = ['Coordinate Transformation Matrix'] + map(str, matrix)
    prop = [shlex.split(p) for a, p in schema.get_value('property') if a]
    mode = [('ABSOLUTE', 'RELATIVE')[schema.get_enum('mode')]]
    return (matrix, mode, prop)


def call_xinput(device, setup):
    set_mode = ['xinput', 'set-mode']
    set_prop = ['xinput', 'set-prop']
    try:
        for obj in device:
            if not obj.get_name().startswith('Virtual core XTEST'):
                nick = obj.get_source().value_nick
                matrix, mode, prop = setup.get(nick, (False, False, tuple()))
                xid = [str(GdkX11.gdk_x11_device_get_id(obj))]
                if matrix:
                    subprocess.call(set_prop + xid + matrix)
                    subprocess.call(set_mode + xid + mode)
                for param in prop:
                    subprocess.call(set_prop + xid + param)
    except OSError:
        sys.exit('cannot find xinput program')


class PointerConfig(Gtk.Application):

    def __init__(self):
        name = 'config.Pointer'
        flag = Gio.ApplicationFlags.FLAGS_NONE
        Gtk.Application.__init__(self, application_id=name, flags=flag)
        self.connect('activate', self.activate)
        self.connect('startup', self.startup)

    def activate(self, application):
        if '-t' not in sys.argv:
            self.window_main.show_all()
        sys.argv = list()

    def device_changed(self, manager, device):
        self.manager = manager
        key = device.set_source().value_nick
        if reduce(lambda x, y: x or y[0] == key, self.store_type, False):
            child = self.settings.get_child(key)
            if child.get_boolean('auto'):
                param = get_params(child)
                call_xinput((device,), {key:param})

    def reset_outline(self, screen):
        self.screen = screen
        matrix = cairo.Matrix(*self.child.get_value('matrix'))
        self.outline.transform(matrix, screen.get_width(), screen.get_height())
        self.outline.hide()
        self.outline.resize(self.spin_size.get_value_as_int())
        if self.child.get_boolean('outline'):
            self.outline.show_all()
        self.outline.move(self.spin_size.get_value_as_int())

    def monitors_changed(self, screen):
        self.outline.move(self.spin_size.get_value_as_int())

    def window_delete(self, widget, event):
        return widget.hide_on_delete()

    def type_changed(self, selection):
        model, i = selection.get_selected()
        self.type = model.get_value(i, 0)
        self.child = self.settings.get_child(self.type)

        self.combo_rotation.set_active(self.child.get_enum('rotation'))
        left, top, width, height = self.child.get_value('bounds')
        self.spin_left.set_value(left)
        self.spin_top.set_value(top)
        self.spin_width.set_value(width)
        self.spin_height.set_value(height)

        mode = bool(self.child.get_enum('mode'))
        self.radio_absolute.set_active(not mode)
        self.radio_relative.set_active(mode)
        self.store_properties.clear()
        for row in self.child.get_value('property'):
            self.store_properties.append(row)

        self.check_auto.set_active(self.child.get_boolean('auto'))
        self.reset_outline(self.screen)
        self.check_outline.set_active(self.child.get_boolean('outline'))
        rgba = Gdk.RGBA(*self.child.get_value('colour'))
        self.outline.override_background_color(Gtk.StateFlags.NORMAL, rgba)
        self.button_colour.set_rgba(rgba)
        self.spin_size.set_value(self.child.get_uint('size'))

    def notebook_switch(self, notebook, page, page_num):
        self.button_apply.set_sensitive(page != self.grid_options)

    def cursor_released(self, widget, event):
        self.device = event.device

    def cursor_clicked(self, widget):
        device = vars(self).get('device', None)
        if device:
            _, x, y = device.get_position()
            if self.check_left.get_active():
                self.spin_left.set_value(x)
            if self.check_top.get_active():
                self.spin_top.set_value(y)
            if self.check_width.get_active():
                self.spin_width.set_value(x - self.spin_left.get_value())
            if self.check_height.get_active():
                self.spin_height.set_value(y - self.spin_top.get_value())

    def property_toggled(self, renderer, path):
        self.store_properties[path][0] = not self.store_properties[path][0]

    def property_edited(self, renderer, path, text):
        if text:
            self.store_properties[path][1] = text
        else:
            i = self.store_properties.get_iter(path)
            self.store_properties.remove(i)

    def add_clicked(self, widget):
        i = self.store_properties.append((True, ''))
        path = self.store_properties.get_path(i)
        arg = (path, self.column_properties, self.text_properties, True)
        self.tree_properties.set_cursor_on_cell(*arg)

    def remove_row(self, model, path, iterator, data):
        model.remove(iterator)

    def remove_clicked(self, widget):
        self.selection_properties.selected_foreach(self.remove_row, None)

    def edit_clicked(self, widget):
        model, i = self.selection_properties.get_selected()
        if i:
            path = model.get_path(i)
            arg = (path, self.column_properties, self.text_properties, True)
            self.tree_properties.set_cursor_on_cell(*arg)

    def auto_toggled(self, button):
        self.child.set_boolean('auto', button.get_active())

    def outline_toggled(self, button):
        if button.get_active():
            self.outline.present_with_time(Gtk.get_current_event_time())
            self.outline.move(self.spin_size.get_value_as_int())
        else:
            self.outline.hide()
        self.child.set_boolean('outline', button.get_active())

    def colour_set(self, widget):
        rgba = widget.get_rgba()
        self.outline.override_background_color(Gtk.StateFlags.NORMAL, rgba)
        rgba = GLib.Variant('(ddd)', (rgba.red, rgba.green, rgba.blue))
        self.child.set_value('colour', rgba)

    def size_changed(self, spinbutton):
        self.outline.resize(spinbutton.get_value_as_int())
        self.outline.move(spinbutton.get_value_as_int())
        self.child.set_uint('size', spinbutton.get_value_as_int())

    def about_clicked(self, widget):
        self.dialog_about.run()
        self.dialog_about.hide()

    def show_activate(self, gobject):
        if not self.window_main.get_visible():
            self.window_main.present_with_time(Gtk.get_current_event_time())
        elif isinstance(gobject, Gtk.StatusIcon):
            self.window_main.hide()

    def quit_activate(self, widget):
        # self.remove_window(self.window_main)
        self.quit()

    def status_popup(self, icon, button, time):
        arg = (None, None, icon.position_menu, icon, button, time)
        self.menu_status.popup(*arg)

    def apply_clicked(self, widget):
        x, y = (self.spin_left.get_value(), self.spin_top.get_value())
        width = self.spin_width.get_value()
        height = self.spin_height.get_value()
        horizontal = float(self.screen.get_width())
        vertical = float(self.screen.get_height())
        # Create matrix scaled and translated.
        matrix = cairo.Matrix(
            xx=width / horizontal, yy=height / vertical,
            x0=x / horizontal, y0=y / vertical)
        matrix.translate(0.5, 0.5)

        i = self.combo_rotation.get_active_iter()
        radians = math.radians(self.store_rotation.get_value(i, 0))
        cos, sin = (round(math.cos(radians)), round(math.sin(radians)))
        matrix = cairo.Matrix(cos, -sin, sin, cos, 0, 0).multiply(matrix)
        matrix.translate(-0.5, -0.5)
        matrix = array.array('f', matrix).tolist()

        self.child.delay()
        self.child.set_enum('rotation', self.combo_rotation.get_active())
        arg = GLib.Variant('(iiuu)', (x, y, width, height))
        self.child.set_value('bounds', arg)
        self.child.set_enum('mode', int(self.radio_relative.get_active()))
        arg = map(tuple, self.store_properties)
        self.child.set_value('property', GLib.Variant('a(bs)', arg))
        self.child.set_value('matrix', GLib.Variant('(dddddd)', tuple(matrix)))
        self.child.apply()

        params = get_params(self.child)
        device = self.manager.list_devices(Gdk.DeviceType.SLAVE)
        call_xinput(device, {self.type:params})
        self.reset_outline(self.screen)

    def startup(self, application):
        self.display = Gdk.Display.get_default()
        self.manager = self.display.get_device_manager()
        self.screen = Gdk.Screen.get_default()
        # device-added works in Gdk_test.py but not here
        # self.manager.connect('device-added', self.device_changed)
        # self.manager.connect('device-changed', self.device_changed)
        self.screen.connect('monitors-changed', self.monitors_changed)
        self.screen.connect('size-changed', self.reset_outline)

        name = 'pointer-config'
        alt = [GLib.get_user_data_dir()] + list(GLib.get_system_data_dirs())
        alt = filter(GLib.path_is_absolute, alt)
        path = [GLib.build_filenamev((p, 'locale')) for p in alt]
        path = [p for p in path if gettext.find(name, p)] + [None]
        gettext.bindtextdomain(name, path[0])
        gettext.textdomain(name)
        gettext.install(name, path[0])
        _ = gettext.lgettext
        GLib.set_application_name(_('Pointer Config'))

        for sub in alt:
            builder = Gtk.Builder()
            builder.set_translation_domain(name)
            path = GLib.build_filenamev((sub, name, name + '.glade'))
            try:
                builder.add_from_file(path)
                break
            except GLib.GError:
                pass
        else:
            sys.exit('failed to load ' + name + '.glade')
        builder.connect_signals(self)

        self.outline = Outline()
        obj = ('window_main', 'store_type', 'combo_rotation', 'store_rotation',
               'check_left', 'spin_left', 'check_top', 'spin_top',
               'check_width', 'spin_width', 'check_height', 'spin_height',
               'button_cursor', 'radio_absolute', 'radio_relative',
               'tree_properties', 'store_properties', 'column_properties',
               'text_properties', 'selection_properties', 'grid_options',
               'check_auto', 'check_outline', 'button_colour', 'spin_size',
               'button_apply', 'dialog_about', 'menu_status')
        for name in obj:
            setattr(self, name, builder.get_object(name))

        path = '/pointer-config/'
        self.settings = Gio.Settings(application.get_application_id(), path)
        param = dict()
        for key, _ in self.store_type:
            child = self.settings.get_child(key)
            if child.get_boolean('auto'):
                param[key] = get_params(child)
        call_xinput(self.manager.list_devices(Gdk.DeviceType.SLAVE), param)

        self.add_window(self.window_main)
