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
║ File:        signage/renderer/base.py                                        ║
║ Version:     1.1.0                                                           ║
║ Author:      Bas                                                             ║
║ Description: Abstract base renderer class - defines the renderer contract    ║
║              that all content renderers must implement. Provides first_frame,║
║              frames generator, and close methods.                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import numpy as np
from abc import ABC, abstractmethod


class BaseRenderer(ABC):
    """
    All renderers inherit from this.

    Usage pattern:
        renderer = SomeRenderer(item, width, height)
        first = renderer.first_frame()          # for transition
        for frame in renderer.frames():         # main loop
            engine.show_frame(frame)
        renderer.close()
    """

    def __init__(self, item: dict, width: int, height: int):
        self.item   = item
        self.width  = width
        self.height = height

    def first_frame(self) -> np.ndarray:
        """
        Return the first frame this renderer would show.
        Used by the transition engine as the 'incoming' frame.
        Default: return a black frame (override for efficiency).
        """
        # Peek at first frame from the generator without consuming it
        gen = self.frames()
        try:
            return next(gen)
        except StopIteration:
            return self._black()

    @abstractmethod
    def frames(self):
        """
        Generator yielding numpy (H, W, 3) uint8 RGB frames.
        Should yield continuously until the caller breaks.
        """
        ...

    def close(self):
        """Release any resources (file handles, decoders etc)."""
        pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _black(self) -> np.ndarray:
        return np.zeros((self.height, self.width, 3), dtype=np.uint8)

    def _resize(self, img, mode='fit') -> np.ndarray:
        """
        Resize a PIL Image to display dimensions.
        mode: 'fit' (letterbox), 'fill' (crop), 'stretch'
        Returns numpy (H, W, 3) uint8.
        """
        from PIL import Image as PILImage
        import numpy as np

        if mode == 'stretch':
            img = img.resize((self.width, self.height), PILImage.LANCZOS)
        elif mode == 'fill':
            # Scale to fill, then centre-crop
            ratio = max(self.width / img.width, self.height / img.height)
            new_w = int(img.width  * ratio)
            new_h = int(img.height * ratio)
            img   = img.resize((new_w, new_h), PILImage.LANCZOS)
            left  = (new_w - self.width)  // 2
            top   = (new_h - self.height) // 2
            img   = img.crop((left, top,
                              left + self.width,
                              top  + self.height))
        else:  # fit
            img.thumbnail((self.width, self.height), PILImage.LANCZOS)
            canvas = PILImage.new('RGB', (self.width, self.height), (0, 0, 0))
            x = (self.width  - img.width)  // 2
            y = (self.height - img.height) // 2
            canvas.paste(img, (x, y))
            img = canvas

        if img.mode != 'RGB':
            img = img.convert('RGB')
        return np.array(img, dtype=np.uint8)


class BlackRenderer(BaseRenderer):
    """Fallback renderer — just shows black."""

    def frames(self):
        while True:
            yield self._black()
