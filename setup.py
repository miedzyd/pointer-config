#!/usr/bin/env python
#
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

from distutils.core import setup
import glob
import os.path
import subprocess
import sys

from gi.repository import GLib

NAME = 'pointer-config'

try:
    for source in glob.iglob(os.path.join('i18n', '*.po')):
        code, _, _ = os.path.basename(source).rpartition('.')
        output = os.path.join('locale', code, 'LC_MESSAGES')
        if not os.path.exists(output):
            os.makedirs(output)
        output = os.path.join(output, NAME + '.mo')
        subprocess.call(('msgfmt', '-o', output, source))
    path = os.path.join('autostart', 'pointer-config.desktop')
    subprocess.call(('intltool-merge', '-d', 'i18n', path + '.in', path))
    path = os.path.join('applications', 'pointer-config.desktop')
    subprocess.call(('intltool-merge', '-d', 'i18n', path + '.in', path))
except OSError:
    sys.exit('msgfmt or intltool-merge missing')

conf = filter(GLib.path_is_absolute, GLib.get_system_config_dirs())[0]
data = filter(GLib.path_is_absolute, GLib.get_system_data_dirs())[0]
data_file = list()
append = lambda d, f: data_file.append(('/'.join(d), ('/'.join(f),)))

for path in glob.iglob(os.path.join('locale', '*', 'LC_MESSAGES')):
    append((data, path), (path, NAME + '.mo'))
append((conf, 'autostart'), ('autostart', NAME + '.desktop'))
append((data, 'applications'), ('applications', NAME + '.desktop'))
append((data, 'doc', NAME), ('COPYING',))
append((data, 'doc', NAME), ('README',))
append((data, 'glib-2.0/schemas'), ('Pointer.Config.gschema.xml',))
append((data, NAME), (NAME, NAME + '.glade'))

setup(
    name=NAME,
    version='0.0.2',
    description='Basic configurion for pointer devices using GTK+ and XInput',
    author='Daniel Miedzyblocki',
    packages=('pointerconfig',),
    scripts=('/'.join(('script', NAME)),),
    data_files=data_file)
