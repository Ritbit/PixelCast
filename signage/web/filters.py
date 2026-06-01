# SPDX-License-Identifier: AGPL-3.0-or-later
#
# PixelCast
# Copyright (C) 2026 Bas van Ritbergen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public
# License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/web/filters.py                                          ║
║ Version:     1.3.1                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Custom Jinja2 template filters - timecode, basename, rgb_hex.   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import os


def register_filters(app):

    @app.template_filter('timecode')
    def timecode_filter(value):
        """Convert a stored start_offset value to display timecode string."""
        if not value and value != 0:
            return ''
        s = str(value).strip()
        # If already looks like a timecode string (contains colon), return as-is
        if ':' in s:
            return s
        # Plain float seconds — convert to timecode display
        try:
            from signage.timecode import seconds_to_timecode
            return seconds_to_timecode(float(s))
        except Exception:
            return s


    @app.template_filter('basename')
    def basename_filter(path):
        return os.path.basename(path) if path else ''

    @app.template_filter('rgb_hex')
    def rgb_hex_filter(color):
        """Convert [r, g, b] list to '#rrggbb' hex string for color inputs."""
        try:
            r, g, b = int(color[0]), int(color[1]), int(color[2])
            return f'#{r:02x}{g:02x}{b:02x}'
        except (TypeError, IndexError, ValueError):
            return '#ffffff'
