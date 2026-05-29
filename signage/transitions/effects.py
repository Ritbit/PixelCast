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
║ File:        signage/transitions/effects.py                                  ║
║ Version:     1.3.0                                                           ║
║ Author:      Bas                                                             ║
║ Description: 22 transition effects - fade, wipe, slide, zoom, dissolve,      ║
║              melt, snow, spiral, drop, blinds, checkerboard, pixelate, etc.  ║
║              Each yields numpy frames for smooth visual transitions.         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import numpy as np
import random
from PIL import Image


class BaseTransition:
    def __init__(self, steps: int = 30):
        self.STEPS = max(3, steps)

    def frames(self, src, dst, w, h):
        raise NotImplementedError

    def _blend(self, a, b, t):
        t = np.clip(t, 0.0, 1.0)
        return (a * (1 - t) + b * t).astype(np.uint8)

    def _ease(self, t):
        return t * t * (3 - 2 * t)


class FadeTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        for i in range(self.STEPS):
            t = self._ease(i / (self.STEPS - 1))
            yield self._blend(src, dst, t)


class FadeBlackTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        black = np.zeros_like(src)
        half  = self.STEPS // 2
        for i in range(half):
            t = self._ease(i / max(half - 1, 1))
            yield self._blend(src, black, t)
        for i in range(half):
            t = self._ease(i / max(half - 1, 1))
            yield self._blend(black, dst, t)


class WipeLeftTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        frame = src.copy()
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            split = int(w * t)
            np.copyto(frame, src)
            if split > 0:
                frame[:, w - split:, :] = dst[:, w - split:, :]
            yield frame.copy()


class WipeRightTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        frame = src.copy()
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            split = int(w * t)
            np.copyto(frame, src)
            if split > 0:
                frame[:, :split, :] = dst[:, :split, :]
            yield frame.copy()


class WipeUpTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        frame = src.copy()
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            split = int(h * t)
            np.copyto(frame, src)
            if split > 0:
                frame[h - split:, :, :] = dst[h - split:, :, :]
            yield frame.copy()


class WipeDownTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        frame = src.copy()
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            split = int(h * t)
            np.copyto(frame, src)
            if split > 0:
                frame[:split, :, :] = dst[:split, :, :]
            yield frame.copy()


class SlideLeftTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        frame = np.empty_like(src)
        for i in range(self.STEPS):
            t      = self._ease(i / (self.STEPS - 1))
            offset = int(w * t)
            frame[:] = 0
            if offset < w:
                frame[:, :w - offset, :] = src[:, offset:, :]
            if offset > 0:
                frame[:, w - offset:, :] = dst[:, :offset, :]
            yield frame.copy()


class SlideRightTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        frame = np.empty_like(src)
        for i in range(self.STEPS):
            t      = self._ease(i / (self.STEPS - 1))
            offset = int(w * t)
            frame[:] = 0
            if offset < w:
                frame[:, offset:, :] = src[:, :w - offset, :]
            if offset > 0:
                frame[:, :offset, :] = dst[:, w - offset:, :]
            yield frame.copy()


class SlideUpTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        frame = np.empty_like(src)
        for i in range(self.STEPS):
            t      = self._ease(i / (self.STEPS - 1))
            offset = int(h * t)
            frame[:] = 0
            if offset < h:
                frame[:h - offset, :, :] = src[offset:, :, :]
            if offset > 0:
                frame[h - offset:, :, :] = dst[:offset, :, :]
            yield frame.copy()


class SlideDownTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        frame = np.empty_like(src)
        for i in range(self.STEPS):
            t      = self._ease(i / (self.STEPS - 1))
            offset = int(h * t)
            frame[:] = 0
            if offset < h:
                frame[offset:, :, :] = src[:h - offset, :, :]
            if offset > 0:
                frame[:offset, :, :] = dst[h - offset:, :, :]
            yield frame.copy()


class ZoomInTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            scale = max(0.05, t)
            nw    = max(1, int(w * scale))
            nh    = max(1, int(h * scale))
            small = Image.fromarray(dst).resize((nw, nh), Image.LANCZOS)
            frame = src.copy()
            x     = (w - nw) // 2
            y     = (h - nh) // 2
            frame[y:y+nh, x:x+nw, :] = np.array(small)
            yield frame


class ZoomOutTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            scale = max(0.05, 1.0 - t)
            nw    = max(1, int(w * scale))
            nh    = max(1, int(h * scale))
            small = Image.fromarray(src).resize((nw, nh), Image.LANCZOS)
            frame = dst.copy()
            x     = (w - nw) // 2
            y     = (h - nh) // 2
            frame[y:y+nh, x:x+nw, :] = np.array(small)
            yield frame


class DissolveTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        total    = w * h
        indices  = np.arange(total)
        np.random.shuffle(indices)
        frame    = src.reshape(-1, 3).copy()
        dst_flat = dst.reshape(-1, 3)
        chunk    = max(1, total // self.STEPS)
        for i in range(self.STEPS):
            start = i * chunk
            end   = min(start + chunk, total)
            frame[indices[start:end]] = dst_flat[indices[start:end]]
            yield frame.reshape(h, w, 3).copy()


class MeltTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        offsets = np.random.randint(0, h // 2, size=w)
        speeds  = np.random.randint(1, max(2, h // self.STEPS), size=w)
        frame   = dst.copy()   # reuse across steps
        for _ in range(self.STEPS * 2):
            np.copyto(frame, dst)
            # Vectorised: for each column x, copy src rows [off:] to frame rows [:h-off]
            # Columns are independent so we loop over unique offset values (much fewer
            # than w iterations when steps are large) — but numpy advanced indexing
            # is faster than a Python per-column loop regardless.
            for off_val in np.unique(offsets):
                if off_val >= h:
                    continue
                cols = np.where(offsets == off_val)[0]
                frame[:h - off_val, cols, :] = src[off_val:, cols, :]
            yield frame.copy()
            offsets = np.minimum(offsets + speeds, h)
            if np.all(offsets >= h):
                break
        yield dst.copy()


class SnowTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        mask  = np.zeros((h, w), dtype=bool)
        total = w * h
        for step in range(self.STEPS):
            n_new = total // self.STEPS
            ys    = np.random.randint(0, h, n_new)
            xs    = np.random.randint(0, w, n_new)
            mask[ys, xs] = True
            frame = src.copy()
            frame[mask] = dst[mask]
            if step < self.STEPS - 2:
                sy = ys[:len(ys)//4]
                sx = xs[:len(xs)//4]
                frame[sy, sx] = [255, 255, 255]
            yield frame
        yield dst.copy()


class SpiralTransition(BaseTransition):
    _walk_cache: dict = {}   # (w, h) → (row_idx, col_idx) — computed once per resolution

    def frames(self, src, dst, w, h):
        key = (w, h)
        if key not in SpiralTransition._walk_cache:
            cx, cy   = w // 2, h // 2
            rows_out = []
            cols_out = []
            visited  = set()
            x, y     = cx, cy
            dx, dy   = 1, 0
            steps    = 1
            count    = 0
            turn     = 0
            while len(rows_out) < w * h:
                if 0 <= x < w and 0 <= y < h and (x, y) not in visited:
                    rows_out.append(y)
                    cols_out.append(x)
                    visited.add((x, y))
                x += dx
                y += dy
                count += 1
                if count == steps:
                    count = 0
                    dx, dy = -dy, dx
                    turn  += 1
                    if turn % 2 == 0:
                        steps += 1
                if len(visited) >= w * h:
                    break
            SpiralTransition._walk_cache[key] = (
                np.array(rows_out, dtype=np.intp),
                np.array(cols_out, dtype=np.intp),
            )
        # Pre-built flat index arrays for vectorised bulk assignment
        row_idx, col_idx = SpiralTransition._walk_cache[key]
        total   = len(row_idx)
        chunk   = max(1, total // self.STEPS)
        frame   = src.copy()
        src_flat = src.reshape(-1, 3)
        dst_flat = dst.reshape(-1, 3)
        for i in range(self.STEPS):
            end = min((i + 1) * chunk, total)
            r   = row_idx[:end]
            c   = col_idx[:end]
            # Vectorised bulk assignment — no Python loop over pixels
            flat = r * w + c
            frame.reshape(-1, 3)[flat] = dst_flat[flat]
            yield frame.copy()
        yield dst.copy()


class DropTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        delays      = np.random.randint(0, self.STEPS // 2, size=w)
        total_steps = self.STEPS + self.STEPS // 2
        frame       = src.copy()   # reused scratch buffer
        for step in range(total_steps):
            np.copyto(frame, src)
            # Vectorised: compute drop_h for every column simultaneously
            progress = np.maximum(0, step - delays).astype(np.float32)
            t_ease   = np.clip(progress / self.STEPS, 0.0, 1.0) ** 2
            drop_h   = (h * t_ease).astype(np.intp)   # shape (w,)

            # Full columns (drop_h >= h) — paste entire dst column
            full = drop_h >= h
            if full.any():
                frame[:, full, :] = dst[:, full, :]

            # Partial columns — group by drop_h value to minimise Python iters
            partial_cols = np.where((drop_h > 0) & ~full)[0]
            if partial_cols.size:
                for dh in np.unique(drop_h[partial_cols]):
                    cols = partial_cols[drop_h[partial_cols] == dh]
                    frame[:dh, cols, :] = dst[h - dh:, cols, :]
            yield frame.copy()
        yield dst.copy()


class BlindsHTransition(BaseTransition):
    STRIPS = 8
    def frames(self, src, dst, w, h):
        strip_h = max(1, h // self.STRIPS)
        frame   = src.copy()
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            open_ = int(strip_h * t)
            np.copyto(frame, src)
            for s in range(self.STRIPS):
                y0 = s * strip_h
                y1 = min(y0 + open_, y0 + strip_h, h)
                if y1 > y0:
                    frame[y0:y1, :, :] = dst[y0:y1, :, :]
            yield frame.copy()


class BlindsVTransition(BaseTransition):
    STRIPS = 8
    def frames(self, src, dst, w, h):
        strip_w = max(1, w // self.STRIPS)
        frame   = src.copy()
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            open_ = int(strip_w * t)
            np.copyto(frame, src)
            for s in range(self.STRIPS):
                x0 = s * strip_w
                x1 = min(x0 + open_, x0 + strip_w, w)
                if x1 > x0:
                    frame[:, x0:x1, :] = dst[:, x0:x1, :]
            yield frame.copy()


class CheckerboardTransition(BaseTransition):
    TILE = 16
    def frames(self, src, dst, w, h):
        tiles_x = (w + self.TILE - 1) // self.TILE
        tiles_y = (h + self.TILE - 1) // self.TILE
        coords  = [(ty, tx) for ty in range(tiles_y)
                             for tx in range(tiles_x)]
        random.shuffle(coords)
        total = len(coords)
        chunk = max(1, total // self.STEPS)
        frame = src.copy()
        for i in range(self.STEPS):
            start = i * chunk
            end   = min(start + chunk, total)
            for j in range(start, end):
                ty, tx = coords[j]
                y0 = ty * self.TILE
                x0 = tx * self.TILE
                y1 = min(y0 + self.TILE, h)
                x1 = min(x0 + self.TILE, w)
                frame[y0:y1, x0:x1, :] = dst[y0:y1, x0:x1, :]
            yield frame.copy()
        yield dst.copy()


class PixelateTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        half      = self.STEPS // 2
        max_block = max(4, min(w, h) // 4)

        def pixelate(arr, block):
            if block <= 1:
                return arr.copy()
            img   = Image.fromarray(arr)
            small = img.resize((max(1, w // block), max(1, h // block)),
                               Image.NEAREST)
            big   = small.resize((w, h), Image.NEAREST)
            return np.array(big, dtype=np.uint8)

        for i in range(half):
            t     = i / max(half - 1, 1)
            block = max(1, int(max_block * t))
            yield pixelate(src, block)

        for i in range(half):
            t     = 1.0 - (i / max(half - 1, 1))
            block = max(1, int(max_block * t))
            yield pixelate(dst, block)

        yield dst.copy()
