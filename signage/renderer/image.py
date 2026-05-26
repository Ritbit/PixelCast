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
║ File:        signage/renderer/image.py                                       ║
║ Version:     1.1.0                                                           ║
║ Author:      Bas                                                             ║
║ Description: Static image and animated GIF renderer - supports multiple     ║
║              scaling modes, positioning, Ken Burns effects, and background   ║
║              options. Handles JPG, PNG, BMP, WebP, and animated GIF.        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import time
import logging
import numpy as np
from PIL import Image
from .base import BaseRenderer
from .utils import load_background, fit_image, paste_at, KenBurns

log = logging.getLogger('renderer.image')


class ImageRenderer(BaseRenderer):

    def __init__(self, item: dict, width: int, height: int):
        super().__init__(item, width, height)
        self._ken_burns = item.get('ken_burns', False)
        self._kb        = None
        self._frame     = None
        self._load()

    def _load(self):
        path = self.item.get('file', '')
        try:
            img  = Image.open(path).convert('RGB')
            bg   = load_background(self.width, self.height, self.item, img)

            scale_mode   = self.item.get('scale_mode',
                           self.item.get('scale', 'fit'))
            scale_factor = float(self.item.get('scale_factor', 1.0))
            position     = self.item.get('position', 'center')

            if self._ken_burns:
                # Ken Burns renders its own frames — no static frame needed
                self._kb    = KenBurns(img, self.width, self.height, self.item)
                self._frame = next(self._kb.frames())   # first frame for transition
                log.info(f"Image (Ken Burns) loaded: {path}")
            else:
                sized  = fit_image(img, self.width, self.height,
                                   scale_mode, scale_factor)
                canvas = bg.copy()
                paste_at(canvas, sized, position)
                self._frame = np.array(canvas, dtype=np.uint8)
                log.info(f"Image loaded: {path}")

        except Exception as e:
            log.error(f"Failed to load image '{path}': {e}")
            self._frame = self._black()

    def first_frame(self) -> np.ndarray:
        return self._frame.copy()

    def frames(self):
        if self._ken_burns and self._kb:
            yield from self._kb.frames()
        else:
            while True:
                yield self._frame.copy()


class GifRenderer(BaseRenderer):

    def __init__(self, item: dict, width: int, height: int):
        super().__init__(item, width, height)
        self._frames = []
        self._load()

    def _load(self):
        path         = self.item.get('file', '')
        scale_mode   = self.item.get('scale_mode',
                       self.item.get('scale', 'fit'))
        scale_factor = float(self.item.get('scale_factor', 1.0))
        position     = self.item.get('position', 'center')

        try:
            gif = Image.open(path)
            # Build background once from first frame
            gif.seek(0)
            first_rgb = gif.convert('RGB')
            bg = load_background(self.width, self.height, self.item, first_rgb)

            idx = 0
            while True:
                try:
                    gif.seek(idx)
                except EOFError:
                    break
                delay  = gif.info.get('duration', 100) / 1000.0
                frame  = gif.convert('RGB')
                sized  = fit_image(frame, self.width, self.height,
                                   scale_mode, scale_factor)
                canvas = bg.copy()   # reuse cached bg
                paste_at(canvas, sized, position)
                self._frames.append((np.array(canvas, dtype=np.uint8), delay))
                idx += 1
            log.info(f"GIF loaded: {path} ({len(self._frames)} frames)")
        except Exception as e:
            log.error(f"Failed to load GIF '{path}': {e}")
            self._frames = [(self._black(), 0.1)]

    def first_frame(self) -> np.ndarray:
        return self._frames[0][0].copy() if self._frames else self._black()

    def frames(self):
        if not self._frames:
            while True:
                yield self._black()
            return
        while True:
            for arr, delay in self._frames:
                yield arr.copy()
                time.sleep(delay)


# Keep old name for import compat (renderer factory uses ImageRenderer/GifRenderer)
def sample_corner_color(img, corner='top-left', radius=4):
    from .utils import _sample_corner
    return _sample_corner(img, corner, radius)
