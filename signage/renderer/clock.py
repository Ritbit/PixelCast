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
║ File:        signage/renderer/clock.py                                       ║
║ Version:     1.1.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Digital clock renderer - displays time and date with custom     ║
║              fonts, colors, and backgrounds. Supports pixel-perfect rendering║
║              for LED displays and optional blinking separator.               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import time
import logging
import numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from .base import BaseRenderer
from .utils import load_background, parse_color

log = logging.getLogger('renderer.clock')

FONT_SEARCH = [
    '/opt/PixelCast/led-signage/fonts/',
    '/usr/share/fonts/truetype/freefont/',
    '/usr/share/fonts/truetype/dejavu/',
    '/usr/share/fonts/truetype/',
    '/usr/share/fonts/',
]


def find_font(name: str, size: int):
    import os
    if not name:
        name = 'FreeSans.ttf'
    if os.path.isabs(name) and os.path.exists(name):
        return ImageFont.truetype(name, size)
    for d in FONT_SEARCH:
        for candidate in [
            os.path.join(d, name),
            os.path.join(d, name + '.ttf'),
        ]:
            if os.path.exists(candidate):
                return ImageFont.truetype(candidate, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


class ClockRenderer(BaseRenderer):

    def __init__(self, item: dict, width: int, height: int):
        super().__init__(item, width, height)
        self._time_fmt   = item.get('format',      '%H:%M:%S')
        self._date_fmt   = item.get('date_format', '%A %d %B %Y')
        self._show_date  = bool(self._date_fmt)
        self._time_color = parse_color(item.get('color',      [255, 220, 0]))
        self._date_color = parse_color(item.get('date_color', [180, 180, 180]))
        self._blink      = item.get('blink_separator', True)
        time_size        = item.get('time_size', max(20, height // 2))
        date_size        = item.get('date_size', max(10, time_size // 3))
        self._time_font  = find_font(item.get('time_font', 'FreeSansBold.ttf'), time_size)
        self._date_font  = find_font(item.get('date_font', 'FreeSans.ttf'),     date_size)
        # Pre-build background once — expensive for bg_image, cheap to copy
        self._bg_cache = load_background(self.width, self.height, item)

    def _get_bg(self) -> Image.Image:
        return self._bg_cache.copy()   # fast pixel copy, no I/O

    def _render(self, show_colon: bool = True) -> np.ndarray:
        now      = datetime.now()
        canvas   = self._get_bg()
        draw     = ImageDraw.Draw(canvas)

        time_str = now.strftime(self._time_fmt)
        if self._blink and not show_colon:
            time_str = time_str.replace(':', ' ')

        date_str = now.strftime(self._date_fmt) if self._date_fmt else ''

        def text_size(text, font):
            try:
                bb = font.getbbox(text)
                return bb[2] - bb[0], bb[3] - bb[1]
            except AttributeError:
                return font.getsize(text)

        tw, th = text_size(time_str, self._time_font)

        if date_str:
            dw, dh  = text_size(date_str, self._date_font)
            total_h = th + 6 + dh
            time_y  = (self.height - total_h) // 2
            date_y  = time_y + th + 6
        else:
            time_y = (self.height - th) // 2
            date_y = None
            dw     = 0

        time_x = (self.width - tw) // 2
        draw.text((time_x, time_y), time_str,
                  font=self._time_font, fill=self._time_color)

        if date_str and date_y is not None:
            date_x = (self.width - dw) // 2
            draw.text((date_x, date_y), date_str,
                      font=self._date_font, fill=self._date_color)

        return np.array(canvas, dtype=np.uint8)

    def first_frame(self) -> np.ndarray:
        return self._render(show_colon=True)

    def frames(self):
        blink = True
        while True:
            yield self._render(show_colon=blink)
            blink = not blink
            time.sleep(1.0)
