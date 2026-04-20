"""
renderer/gif.py - Animated GIF renderer
"""

import time
import logging
import numpy as np
from PIL import Image
from .base import BaseRenderer

log = logging.getLogger('renderer.gif')


class GifRenderer(BaseRenderer):

    def __init__(self, item: dict, width: int, height: int):
        super().__init__(item, width, height)
        self._frames  = []   # list of (np.ndarray, delay_seconds)
        self._load()

    def _load(self):
        path = self.item.get('file', '')
        mode = self.item.get('scale', 'fit')
        try:
            gif = Image.open(path)
            frame_idx = 0
            while True:
                try:
                    gif.seek(frame_idx)
                except EOFError:
                    break
                # Duration in ms, default 100ms
                delay = gif.info.get('duration', 100) / 1000.0
                frame_rgb = gif.convert('RGB')
                arr = self._resize(frame_rgb, mode)
                self._frames.append((arr, delay))
                frame_idx += 1

            log.info(f"GIF loaded: {path} ({len(self._frames)} frames)")

        except Exception as e:
            log.error(f"Failed to load GIF '{path}': {e}")
            self._frames = [(self._black(), 0.1)]

    def first_frame(self) -> np.ndarray:
        if self._frames:
            return self._frames[0][0].copy()
        return self._black()

    def frames(self):
        """Yield GIF frames in a loop, respecting per-frame timing."""
        if not self._frames:
            while True:
                yield self._black()
            return

        while True:
            for arr, delay in self._frames:
                yield arr.copy()
                time.sleep(delay)
