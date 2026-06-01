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
║ File:        signage/screentest.py                                           ║
║ Version:     1.3.1                                                           ║
║ Author:      Bas                                                             ║
║ Description: Screen test pattern generator - provides various test patterns  ║
║              for display calibration and troubleshooting.                    ║
║                                                                              ║
║ Important:   Pauses playlist and runs patterns directly on matrix engine.    ║
║              Patterns include: solid colors, gradients, grid, scrolling.     ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import time
import math
import threading
import numpy as np
import logging

log = logging.getLogger('screentest')


class ScreenTester:
    def __init__(self, engine):
        self._engine = engine
        self._stop   = threading.Event()
        self._thread = None

    def _running(self):
        return self._thread and self._thread.is_alive()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._stop.clear()
        self._engine.resume_playlist()

    def run(self, test_type: str, param: str, duration: int = 10):
        if self._running():
            self.stop()
        self._engine.pause_for_test()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_test,
            args=(test_type, param, duration),
            daemon=True, name='ScreenTest')
        self._thread.start()

    def _run_test(self, test_type, param, duration):
        w, h   = self._engine.width, self._engine.height
        end_t  = time.time() + duration if duration > 0 else float('inf')
        try:
            if test_type == 'solid':
                hx = param.lstrip('#')
                if len(hx) == 3:
                    hx = ''.join(c * 2 for c in hx)
                if len(hx) != 6 or not all(c in '0123456789abcdefABCDEF' for c in hx):
                    log.warning(f"Invalid hex color '{param}', using white")
                    hx = 'ffffff'
                try:
                    color = np.array([int(hx[i:i+2], 16) for i in (0, 2, 4)],
                                     dtype=np.uint8)
                except ValueError:
                    log.warning(f"Failed to parse hex color '{param}', using white")
                    color = np.array([255, 255, 255], dtype=np.uint8)
                frame = np.full((h, w, 3), color, dtype=np.uint8)
                while not self._stop.is_set() and time.time() < end_t:
                    self._engine.show_frame(frame, _from_test=True)
                    time.sleep(0.1)

            elif test_type == 'pattern':
                frame = self._make_pattern(param, w, h)
                while not self._stop.is_set() and time.time() < end_t:
                    self._engine.show_frame(frame, _from_test=True)
                    time.sleep(0.1)

            elif test_type == 'anim':
                self._run_anim(param, w, h, end_t)

        except Exception as e:
            log.error(f"Screen test error: {e}")
        finally:
            if not self._stop.is_set():
                self._engine.resume_playlist()

    def _make_pattern(self, name, w, h):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        if name == 'gradient_h':
            for x in range(w):
                v = int(x / w * 255)
                frame[:, x] = v
        elif name == 'gradient_v':
            for y in range(h):
                v = int(y / h * 255)
                frame[y, :] = v
        elif name == 'rainbow_h':
            for x in range(w):
                t   = x / w
                r   = int(max(0, min(255, 255 * abs(t * 6 - 3) - 1)))
                g   = int(max(0, min(255, 255 * (2 - abs(t * 6 - 2)))))
                b   = int(max(0, min(255, 255 * (2 - abs(t * 6 - 4)))))
                frame[:, x] = [r, g, b]
        elif name == 'checkerboard':
            sz = 8
            for y in range(h):
                for x in range(w):
                    frame[y, x] = 200 if (x // sz + y // sz) % 2 == 0 else 30
        elif name == 'grid':
            frame[:] = 20
            frame[::8, :]  = 80
            frame[:, ::8]  = 80
        elif name == 'crosshair':
            frame[:] = 10
            frame[h // 2, :]   = [0, 255, 0]
            frame[:, w // 2]   = [0, 255, 0]
            frame[0, :]        = [255, 0, 0]
            frame[h-1, :]      = [255, 0, 0]
            frame[:, 0]        = [255, 0, 0]
            frame[:, w-1]      = [255, 0, 0]
        elif name == 'border':
            frame[:] = 10
            frame[0, :]    = [0, 255, 0]
            frame[h-1, :]  = [0, 255, 0]
            frame[:, 0]    = [0, 255, 0]
            frame[:, w-1]  = [0, 255, 0]
        elif name == 'pixels':
            for y in range(h):
                for x in range(w):
                    ch = (x + y) % 3
                    frame[y, x, ch] = 255
        return frame

    def _run_anim(self, name, w, h, end_t):
        fps    = 25
        period = 1.0 / fps
        t      = 0.0
        while not self._stop.is_set() and time.time() < end_t:
            frame = np.zeros((h, w, 3), dtype=np.uint8)

            if name == 'color_fade':
                # Cycle hue over 6 seconds
                hue = (t / 6.0) % 1.0
                rgb = _hsv_to_rgb(hue, 1.0, 1.0)
                frame[:] = rgb

            elif name == 'brightness_ramp':
                v   = int(abs(math.sin(t * math.pi / 4)) * 255)
                frame[:] = v

            elif name == 'flash_rgb':
                ch = int(t * 3) % 3
                frame[:, :, ch] = 255

            elif name == 'scan_h':
                y = int((t * 30) % h)
                frame[y, :] = [255, 255, 255]
                for i in range(1, 4):
                    yi = (y - i) % h
                    frame[yi, :] = [255 // (i * 2), 255 // (i * 2), 255 // (i * 2)]

            elif name == 'scan_v':
                x = int((t * 60) % w)
                frame[:, x] = [255, 255, 255]
                for i in range(1, 6):
                    xi = (x - i) % w
                    frame[:, xi] = [255 // (i * 2), 255 // (i * 2), 255 // (i * 2)]

            self._engine.show_frame(frame, _from_test=True)
            time.sleep(period)
            t += period


def _hsv_to_rgb(h, s, v):
    if s == 0:
        c = int(v * 255)
        return [c, c, c]
    i   = int(h * 6)
    f   = h * 6 - i
    p   = v * (1 - s)
    q   = v * (1 - f * s)
    t_  = v * (1 - (1 - f) * s)
    i  %= 6
    rgb = [(v, t_, p), (q, v, p), (p, v, t_),
           (p, q, v), (t_, p, v), (v, p, q)][i]
    return [int(x * 255) for x in rgb]
