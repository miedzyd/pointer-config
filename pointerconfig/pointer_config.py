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

import shlex
import subprocess
import math
import array
import sys
import gettext

from pointerconfig import Gdk
from pointerconfig.Gdk import GdkX11
import cairo
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import GLib


class Rectangle(object):

    def __init__(self, x=0, y=0, x2=0, y2=0):
        self.x, self.y, self.x2, self.y2 = (x, y, x2, y2)

    def sort(self, x, y, x2, y2, minimum=0):
        self.x, _, self.x2, _ = sorted((x, x + minimum, x2, x2 + minimum))
        self.y, _, self.y2, _ = sorted((y, y + minimum, y2, y2 + minimum))

    def transform(self, matrix, callback=lambda v: v, minimum=0):
        x, y = matrix.transform_point(self.x, self.y)
        x2, y2 = matrix.transform_point(self.x2, self.y2)
        self.sort(*map(callback, (x, y, x2, y2, minimum)))

    def __getitem__(self, key):
        return getattr(self, key)

    width = property(lambda s: s.x2 - s.x)
    height = property(lambda s: s.y2 - s.y)


class GrabDialog(Gtk.MessageDialog):

    def __init__(self, parent, name, device):
        N_ = lambda m: m
        text = dict(many=N_('Click twice in separate monitor areas to select'),
                    one=N_('Click in monitor area to select'),
                    move=N_('Click once to move mapped area'),
                    position=N_('Click twice to position mapping'))
        Gtk.MessageDialog.__init__(self, parent, 0, Gtk.MessageType.INFO, 
                                   Gtk.ButtonsType.CANCEL, _(text[name]))
        self.set_destroy_with_parent(True)
        self.set_icon_name('preferences-desktop-peripherals')
        self._last = dict(one=True, move=True).get(name)
        self.connect('map-event', self._map_event, device)
        self.handler = self.connect('button-press-event', self._button_press)
        self.connect('grab-broken-event', self._grab_broken)

    def _map_event(self, widget, event, device):
        status = device.grab(
            self.get_window(), Gdk.GrabOwnership.NONE, False,
            Gdk.EventMask.BUTTON_PRESS_MASK, 
            Gdk.Cursor(Gdk.CursorType.CROSSHAIR), Gdk.CURRENT_TIME)
            # Gtk.get_current_event_time()
        if status != Gdk.GrabStatus.SUCCESS:
            self.response(Gtk.ResponseType.NONE)
        return False

    def _button_press(self, widget, event):
        x, y = (event.x_root, event.y_root)
        self.pick = getattr(self, 'pick', Rectangle(x, y, x, y))
        if self._last:
            self.pick.sort(self.pick.x, self.pick.y, x, y)
            self.disconnect(self.handler)
            self.response(Gtk.ResponseType.OK)
        self._last = True
        return False

    def _grab_broken(self, widget, event):
        self.disconnect(self.handler)
        self.response(Gtk.ResponseType.NONE)
        return False


class OutlineWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self)
        self.set_gravity(Gdk.Gravity.STATIC)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)


class Outline(Rectangle):
    def __init__(self):
        Rectangle.__init__(self)
        self._top, self._bottom = (OutlineWindow(), OutlineWindow())
        self._left, self._right = (OutlineWindow(), OutlineWindow())

    def move(self, size):
        self._top.move(self.x, self.y - size)
        self._bottom.move(self.x, self.y2)
        self._left.move(self.x - size, self.y)
        self._right.move(self.x2, self.y)

    def resize(self, size):
        self._top.resize(self.width, size)
        self._bottom.resize(self.width, size)
        self._left.resize(size, self.height)
        self._right.resize(size, self.height)
        self.move(size)

    def __getattr__(self, name):
        def callback(*arg):
            for window in (self._top, self._bottom, self._left, self._right):
                getattr(window, name)(*arg)
        return callback

def get_params(matrix, mode, properties, everything=True, schema=None):
    if schema:
        matrix = list(schema.get_value('matrix'))
        mode = schema.get_enum('mode')
        properties = schema.get_value('property')

    matrix = matrix[0::2] + matrix[1::2] + [0, 0, 1]
    matrix = ['Coordinate Transformation Matrix'] + map(str, matrix)
    prop = list()
    if everything:
        for active, param in properties:
            if active:
                prop.append(shlex.split(param))
        return (matrix, [('ABSOLUTE', 'RELATIVE')[mode]], prop)
    return (matrix, False, tuple())


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
                if mode:
                    subprocess.call(set_mode + xid + mode)
                for param in prop:
                    subprocess.call(set_prop + xid + param)
    except OSError:
        sys.exit('cannot find xinput program')


def rotate_point(degrees, x, y):
    matrix = cairo.Matrix(x0=x, y0=y) # translate
    radians = math.radians(degrees)
    cos = round(math.cos(radians))
    sin = round(math.sin(radians))
    rotate = cairo.Matrix(cos, -sin, sin, cos, 0, 0)
    matrix = rotate.multiply(matrix)
    matrix.translate(-x, -y)
    return matrix


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
        if reduce(lambda x, y: x or y[0] == key, self.store_list, False):
            child = self.settings.get_child(key)
            if child.get_boolean('auto'):
                param = get_params(None, None, None, schema=child)
                call_xinput((device,), {key:param})

    def reset_outline(self, screen, reset=True):
        self.screen = screen
        if reset:
            m = cairo.Matrix(xx=screen.get_width(), yy=screen.get_height())
            m = cairo.Matrix(*self.child.get_value('matrix')).multiply(m)
            vars(self.outline).update(dict(x=0, y=0, x2=1, y2=1))
            self.outline.transform(m, round, 1)
            self.outline.hide()
            self.outline.resize(self.spin_size.get_value_as_int())
            if self.child.get_boolean('outline'):
                self.outline.show_all()
        else:
            self.outline.move(self.spin_size.get_value_as_int())

    def window_delete(self, widget, event):
        return widget.hide_on_delete()

    def type_changed(self, selection):
        model, i = selection.get_selected()
        self.type = model.get_value(i, 0)
        self.child = self.settings.get_child(self.type)

        self.combo_rotation.set_active(self.child.get_enum('rotation'))
        active = self.child.get_boolean('horizontal-bounds')
        self.check_horizontal_bounds.set_active(active)
        active = self.child.get_boolean('vertical-bounds')
        self.check_vertical_bounds.set_active(active)
        self.combo_monitors.set_active(self.child.get_enum('monitors'))
        self.combo_action.set_active(self.child.get_enum('action'))

        active = self.child.get_boolean('horizontal-margin')
        self.check_horizontal_margin.set_active(active)
        active = self.child.get_boolean('vertical-margin')
        self.check_vertical_margin.set_active(active)
        margin = Rectangle(*self.child.get_value('margin'))
        self.spin_horizontal.set_value(margin.x2)
        self.spin_vertical.set_value(margin.y2)

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
        self.button_colour.set_rgba(rgba)
        self.outline.override_background_color(Gtk.StateFlags.NORMAL, rgba)
        self.spin_size.set_value(self.child.get_uint('size'))

    def notebook_switch(self, notebook, page, page_num):
        self.button_apply.set_sensitive(page != self.grid_options)

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

    def set_axis(self, name, n, n2, screen, mon, pick, rect):
        if name == 'screen':
            arg = {n:0, n2:screen}
        elif name == 'many' or name == 'one':
            arg = {n:mon[n], n2:mon[n2]}
        elif name == 'margin' or name == 'position':
            arg = {n:pick[n], n2:pick[n2]}
        elif name == 'move':
            return pick[n] - rect[n]
        vars(rect).update(arg)
        return 0.0

    def get_rect(self, name, x, y, rect, pick=None, mon=None):
        rect = Rectangle(**vars(rect))
        if x:
            root = self.screen.get_width()
            x = self.set_axis(name, 'x', 'x2', root, mon, pick, rect)
        if y:
            root = self.screen.get_height()
            y = self.set_axis(name, 'y', 'y2', root, mon, pick, rect)
        rect.transform(cairo.Matrix(x0=float(x), y0=float(y))) # translate
        return rect

    def apply_matrix(self, rotate, bounds, margin, everything=True):
        width = float(self.screen.get_width())
        height = float(self.screen.get_height())
        m = dict(xx=(bounds.width + margin.width) / width,
                 yy=(bounds.height + margin.height) / height) # scale
        m = cairo.Matrix(x0=(bounds.x + margin.x) / width,
                         y0=(bounds.y + margin.y) / height, **m) # translate
        m = array.array('f', rotate.multiply(m)).tolist()
        params = get_params(m, self.radio_relative.get_active(),
                            self.store_properties, everything)
        device = self.manager.list_devices(Gdk.DeviceType.SLAVE)
        call_xinput(device, {self.type:params})
        return m

    def write_settings(self, matrix, bounds, margin):
        self.child.delay()
        self.child.set_enum('rotation', self.combo_rotation.get_active())
        active = self.check_horizontal_bounds.get_active()
        self.child.set_boolean('horizontal-bounds', active)
        active = self.check_vertical_bounds.get_active()
        self.child.set_boolean('vertical-bounds', active)
        self.child.set_enum('monitors', self.combo_monitors.get_active())
        self.child.set_enum('action', self.combo_action.get_active())

        active = self.check_horizontal_margin.get_active()
        self.child.set_boolean('horizontal-margin', active)
        active = self.check_vertical_margin.get_active()
        self.child.set_boolean('vertical-margin', active)

        self.child.set_enum('mode', int(self.radio_relative.get_active()))
        arg = map(tuple, self.store_properties)
        self.child.set_value('property', GLib.Variant('a(bs)', arg))

        self.child.set_value('matrix', GLib.Variant('(dddddd)', tuple(matrix)))
        arg = (bounds.x, bounds.y, bounds.x2, bounds.y2)
        self.child.set_value('bounds', GLib.Variant('(dddd)', arg))
        arg = (margin.x, margin.y, margin.x2, margin.y2)
        self.child.set_value('margin', GLib.Variant('(dddd)', arg))
        self.child.apply()
        self.reset_outline(self.screen)

    def grab(self, name, x, y, rotate, bounds, margin, original):
        device = Gtk.get_current_event_device()
        msg = GrabDialog(self.window_main, name, device)
        status = msg.run()
        msg.destroy()
        if status == Gtk.ResponseType.NONE:
            self.dialog_failed.run()
            self.dialog_failed.hide()
        if status == Gtk.ResponseType.OK:
            i = self.screen.get_monitor_at_point(msg.pick.x, msg.pick.y)
            m = self.screen.get_monitor_geometry(i)
            i = self.screen.get_monitor_at_point(msg.pick.x2, msg.pick.y2)
            m2 = self.screen.get_monitor_geometry(i)
            m = Rectangle(m.x, m.y, m2.x + m2.width, m2.y + m2.height)
            rect = self.get_rect(name, x, y, bounds, msg.pick, m)
            return (self.apply_matrix(rotate, rect, margin, False), rect)
        return (self.apply_matrix(rotate, bounds, original, False), bounds)
    
    def apply_clicked(self, widget):
        bounds = Rectangle(*self.child.get_value('bounds'))
        margin = Rectangle(*self.child.get_value('margin'))
        i = self.combo_rotation.get_active_iter()
        next = self.store_rotation.get_value(i, 0)
        diff = next - self.store_rotation[self.child.get_enum('rotation')][0]
        x = bounds.x + bounds.width / 2.0
        y = bounds.y + bounds.height / 2.0
        bounds.transform(rotate_point(diff, x, y))
        margin.transform(rotate_point(diff, 0.0, 0.0))

        x = self.check_horizontal_margin.get_active()
        y = self.check_vertical_margin.get_active()
        h = self.spin_horizontal.get_value()
        v = self.spin_vertical.get_value()
        margin = self.get_rect('margin', x, y, margin, Rectangle(-h, -v, h, v)) 

        x = self.check_horizontal_bounds.get_active()
        y = self.check_vertical_bounds.get_active()
        rotate = rotate_point(next, 0.5, 0.5)
        if not x and not y:
            matrix = self.apply_matrix(rotate, bounds, margin)
            return self.write_settings(matrix, bounds, margin)

        i = self.combo_monitors.get_active_iter()
        mon = self.store_monitors.get_value(i, 0)
        i = self.combo_action.get_active_iter()
        act = self.store_action.get_value(i, 0)
        mod = self.get_rect('screen', x, y, bounds)
        rect = margin if mon == 'all' and act == 'scale' else Rectangle()
        matrix = self.apply_matrix(rotate, mod, rect)

        if mon != 'all':
            rect = margin if act == 'scale' else Rectangle()
            matrix, mod = self.grab(mon, x, y, rotate, bounds, rect, margin)
        if act != 'scale' and mod != bounds:
            matrix, mod = self.grab(act, x, y, rotate, bounds, margin, margin)
        self.write_settings(matrix, mod, margin)

    def startup(self, application):
        self.display = Gdk.Display.get_default()
        self.manager = self.display.get_device_manager()
        self.screen = Gdk.Screen.get_default()
        # device-added works in Gdk_test.py but not here
        # self.manager.connect('device-added', self.device_changed)
        # self.manager.connect('device-changed', self.device_changed)
        self.screen.connect('monitors-changed', self.reset_outline, False)
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
        obj = ('window_main', 'store_type', 'grid_options', 'radio_absolute',
               'radio_relative', 'combo_rotation', 'store_rotation',
               'check_horizontal_bounds', 'check_vertical_bounds',
               'combo_monitors', 'store_monitors', 'combo_action',
               'store_action', 'check_horizontal_margin', 'spin_horizontal',
               'check_vertical_margin', 'spin_vertical', 'tree_properties',
               'store_properties', 'column_properties', 'text_properties',
               'selection_properties', 'check_auto', 'check_outline',
               'button_colour', 'spin_size', 'button_apply', 'menu_status',
               'dialog_about', 'dialog_failed')
        for name in obj:
            setattr(self, name, builder.get_object(name))

        path = '/pointer-config/'
        self.settings = Gio.Settings(application.get_application_id(), path)
        param = dict()
        for key, _ in self.store_type:
            child = self.settings.get_child(key)
            if child.get_boolean('auto'):
                param[key] = get_params(None, None, None, schema=child)
        call_xinput(self.manager.list_devices(Gdk.DeviceType.SLAVE), param)

        self.add_window(self.window_main)
