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
║ PixelCast - Professional LED Matrix Signage System                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/renderer/countdown.py                                   ║
║ Version:     1.1.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Countdown/countup timer renderer - flexible format with weeks,  ║
║              days, hours, minutes, seconds. Supports countdown to target or  ║
║              elapsed time from target with custom styling and labels.        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import time, logging
import numpy as np
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont
from .base import BaseRenderer
from .utils import load_background

log = logging.getLogger('renderer.countdown')

FONT_SEARCH = [
    '/opt/PixelCast/led-signage/fonts/',
    '/usr/share/fonts/truetype/freefont/',
    '/usr/share/fonts/truetype/dejavu/',
]

UNIT_SECONDS = {
    'weeks':   7 * 86400,
    'days':    86400,
    'hours':   3600,
    'minutes': 60,
    'seconds': 1,
}
SHORT_LABELS = {
    'weeks':'w', 'days':'d', 'hours':'h', 'minutes':'m', 'seconds':'s'
}
FULL_LABELS = {
    'weeks':'weeks', 'days':'days', 'hours':'hrs', 'minutes':'min', 'seconds':'sec'
}


def _find_font(name, size):
    import os
    for d in FONT_SEARCH:
        for p in [os.path.join(d, name), os.path.join(d, name + '.ttf')]:
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _decompose(total_s: int, parts: list) -> dict:
    """Break total seconds into the requested units."""
    remaining = abs(total_s)
    result    = {}
    for unit in ['weeks', 'days', 'hours', 'minutes', 'seconds']:
        if unit in parts:
            result[unit] = remaining // UNIT_SECONDS[unit]
            remaining    %= UNIT_SECONDS[unit]
    return result


class CountdownRenderer(BaseRenderer):

    def __init__(self, item: dict, width: int, height: int,
                 lightweight: bool = False):
        super().__init__(item, width, height)
        self._item      = item
        self._bg_cache  = load_background(width, height, item)

        target_str      = item.get('target_date', '2026-12-31T00:00:00')
        try:
            self._target = datetime.fromisoformat(
                target_str.replace('Z', '+00:00'))
        except Exception:
            self._target = datetime.now(tz=timezone.utc)

        self._direction   = item.get('direction', 'down')
        self._finished    = item.get('finished_text', '🎉 Done!')
        self._parts       = item.get('format_parts',
                             ['days', 'hours', 'minutes', 'seconds'])
        self._show_labels = item.get('show_labels', True)
        self._label_style = item.get('label_style', 'short')
        self._separator   = item.get('separator', ':')
        self._position    = item.get('position', 'center')
        self._prefix      = item.get('prefix_text', '')
        self._suffix      = item.get('suffix_text', '')

        from .utils import parse_color
        self._num_color = parse_color(item.get('number_color'),  (255, 220,   0))
        self._lbl_color = parse_color(item.get('label_color'),   (180, 180, 180))
        self._pre_color = parse_color(item.get('prefix_color'),  (200, 200, 255))
        self._suf_color = parse_color(item.get('suffix_color'),  (200, 200, 200))
        self._fin_color = parse_color(item.get('finished_color'),(255, 180,   0))

        # Fonts — auto-size if not specified
        font_name   = item.get('font', 'FreeSansBold.ttf')
        lbl_font    = item.get('label_font', 'FreeSans.ttf')
        pre_font    = item.get('prefix_font',  'FreeSans.ttf')
        suf_font    = item.get('suffix_font',  'FreeSans.ttf')
        fin_font    = item.get('finished_font', font_name)
        n_units     = len(self._parts)

        if item.get('font_size', 0):
            num_sz = int(item['font_size'])
        else:
            # Auto: fit numbers across width
            num_sz = max(10, min(height // 2,
                                 (width // max(1, n_units * 2 + 1))))

        lbl_sz      = max(6,  num_sz // 3)
        pre_sz      = int(item.get('prefix_size',   max(8, height // 10)))
        suf_sz      = int(item.get('suffix_size',   max(8, height // 12)))
        fin_sz      = int(item.get('finished_size', max(12, height // 5)))

        self._num_font = _find_font(font_name, num_sz)
        self._lbl_font = _find_font(lbl_font,  lbl_sz)
        self._pre_font = _find_font(pre_font,  pre_sz)
        self._suf_font = _find_font(suf_font,  suf_sz)
        self._fin_font = _find_font(fin_font,  fin_sz)

    def _text_w(self, t, f):
        try:
            bb = f.getbbox(t); return bb[2] - bb[0]
        except AttributeError:
            return f.getsize(t)[0]

    def _text_h(self, t, f):
        try:
            bb = f.getbbox(t); return bb[3] - bb[1]
        except AttributeError:
            return f.getsize(t)[1]

    def _remaining(self) -> int:
        if self._target.tzinfo is not None:
            now = datetime.now(tz=self._target.tzinfo)
        else:
            now = datetime.now()
        delta = (self._target - now).total_seconds()
        return int(delta) if self._direction == 'down' else int(-delta)

    def _render(self) -> np.ndarray:
        canvas = self._bg_cache.copy()
        draw   = ImageDraw.Draw(canvas)
        rem    = self._remaining()
        W, H   = self.width, self.height

        # Finished state
        if self._direction == 'down' and rem <= 0:
            msg = self._finished
            mw  = self._text_w(msg, self._fin_font)
            mh  = self._text_h(msg, self._fin_font)
            draw.text(((W - mw)//2, (H - mh)//2), msg,
                      font=self._fin_font, fill=self._fin_color)
            return np.array(canvas, dtype=np.uint8)

        values = _decompose(rem, self._parts)

        # Measure everything first
        num_strs = [f"{values[p]:02d}" for p in self._parts]
        sep      = self._separator
        sep_w    = self._text_w(sep, self._num_font) if sep else 0

        num_ws   = [self._text_w(s, self._num_font) for s in num_strs]
        num_h    = self._text_h('00', self._num_font)
        lbl_h    = self._text_h('d', self._lbl_font) if self._show_labels else 0

        total_w  = sum(num_ws) + sep_w * (len(self._parts) - 1)
        block_h  = num_h + (lbl_h + 2 if self._show_labels else 0)

        pre_h    = (self._text_h(self._prefix, self._pre_font) + 4
                    if self._prefix else 0)
        suf_h    = (self._text_h(self._suffix, self._suf_font) + 4
                    if self._suffix else 0)

        total_block = pre_h + block_h + suf_h

        # Vertical anchor
        if self._position == 'top':
            y0 = 4
        elif self._position == 'bottom':
            y0 = H - total_block - 4
        else:
            y0 = (H - total_block) // 2

        y = y0

        # Prefix
        if self._prefix:
            pw = self._text_w(self._prefix, self._pre_font)
            draw.text(((W - pw)//2, y), self._prefix,
                      font=self._pre_font, fill=self._pre_color)
            y += pre_h

        # Numbers + separators
        x = (W - total_w) // 2
        for idx, (unit, s, nw) in enumerate(
                zip(self._parts, num_strs, num_ws)):
            draw.text((x, y), s, font=self._num_font, fill=self._num_color)

            if self._show_labels:
                lbl = (SHORT_LABELS[unit] if self._label_style == 'short'
                       else FULL_LABELS[unit]  if self._label_style == 'full'
                       else '')
                if lbl:
                    lw = self._text_w(lbl, self._lbl_font)
                    draw.text((x + nw//2 - lw//2, y + num_h + 2),
                              lbl, font=self._lbl_font, fill=self._lbl_color)
            x += nw
            if idx < len(self._parts) - 1 and sep:
                draw.text((x, y), sep, font=self._num_font,
                          fill=self._lbl_color)
                x += sep_w

        y += block_h

        # Suffix
        if self._suffix:
            sw = self._text_w(self._suffix, self._suf_font)
            draw.text(((W - sw)//2, y + 2), self._suffix,
                      font=self._suf_font, fill=self._suf_color)

        return np.array(canvas, dtype=np.uint8)

    def first_frame(self) -> np.ndarray:
        return self._render()

    def frames(self):
        while True:
            yield self._render()
            time.sleep(1.0)
