"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/transitions/effects.py                                  ║
║ Version:     1.0.0                                                           ║
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
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            split = int(w * t)
            frame = src.copy()
            if split > 0:
                frame[:, w - split:, :] = dst[:, w - split:, :]
            yield frame


class WipeRightTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            split = int(w * t)
            frame = src.copy()
            if split > 0:
                frame[:, :split, :] = dst[:, :split, :]
            yield frame


class WipeUpTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            split = int(h * t)
            frame = src.copy()
            if split > 0:
                frame[h - split:, :, :] = dst[h - split:, :, :]
            yield frame


class WipeDownTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            split = int(h * t)
            frame = src.copy()
            if split > 0:
                frame[:split, :, :] = dst[:split, :, :]
            yield frame


class SlideLeftTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        for i in range(self.STEPS):
            t      = self._ease(i / (self.STEPS - 1))
            offset = int(w * t)
            frame  = np.zeros_like(src)
            if offset < w:
                frame[:, :w - offset, :] = src[:, offset:, :]
            if offset > 0:
                frame[:, w - offset:, :] = dst[:, :offset, :]
            yield frame


class SlideRightTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        for i in range(self.STEPS):
            t      = self._ease(i / (self.STEPS - 1))
            offset = int(w * t)
            frame  = np.zeros_like(src)
            if offset < w:
                frame[:, offset:, :] = src[:, :w - offset, :]
            if offset > 0:
                frame[:, :offset, :] = dst[:, w - offset:, :]
            yield frame


class SlideUpTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        for i in range(self.STEPS):
            t      = self._ease(i / (self.STEPS - 1))
            offset = int(h * t)
            frame  = np.zeros_like(src)
            if offset < h:
                frame[:h - offset, :, :] = src[offset:, :, :]
            if offset > 0:
                frame[h - offset:, :, :] = dst[:offset, :, :]
            yield frame


class SlideDownTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        for i in range(self.STEPS):
            t      = self._ease(i / (self.STEPS - 1))
            offset = int(h * t)
            frame  = np.zeros_like(src)
            if offset < h:
                frame[offset:, :, :] = src[:h - offset, :, :]
            if offset > 0:
                frame[:offset, :, :] = dst[h - offset:, :, :]
            yield frame


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
        done    = np.zeros(w, dtype=bool)
        for _ in range(self.STEPS * 2):
            frame = dst.copy()
            for x in range(w):
                off = int(offsets[x])
                if off < h:
                    frame[:h - off, x, :] = src[off:, x, :]
                else:
                    done[x] = True
            yield frame
            offsets = np.minimum(offsets + speeds, h)
            if done.all():
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
    def frames(self, src, dst, w, h):
        cx, cy  = w // 2, h // 2
        coords  = []
        visited = set()
        x, y    = cx, cy
        dx, dy  = 1, 0
        steps   = 1
        count   = 0
        turn    = 0
        while len(coords) < w * h:
            if 0 <= x < w and 0 <= y < h and (x, y) not in visited:
                coords.append((y, x))
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
        total = len(coords)
        chunk = max(1, total // self.STEPS)
        frame = src.copy()
        for i in range(self.STEPS):
            start = i * chunk
            end   = min(start + chunk, total)
            for j in range(start, end):
                r, c = coords[j]
                frame[r, c, :] = dst[r, c, :]
            yield frame.copy()
        yield dst.copy()


class DropTransition(BaseTransition):
    def frames(self, src, dst, w, h):
        delays      = np.random.randint(0, self.STEPS // 2, size=w)
        total_steps = self.STEPS + self.STEPS // 2
        for step in range(total_steps):
            frame = src.copy()
            for x in range(w):
                if step < delays[x]:
                    continue
                progress = step - delays[x]
                t        = min(progress / self.STEPS, 1.0)
                t_ease   = t * t
                drop_h   = int(h * t_ease)
                if drop_h >= h:
                    frame[:, x, :] = dst[:, x, :]
                else:
                    frame[:drop_h, x, :] = dst[h - drop_h:, x, :]
            yield frame
        yield dst.copy()


class BlindsHTransition(BaseTransition):
    STRIPS = 8
    def frames(self, src, dst, w, h):
        strip_h = max(1, h // self.STRIPS)
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            open_ = int(strip_h * t)
            frame = src.copy()
            for s in range(self.STRIPS):
                y0 = s * strip_h
                y1 = min(y0 + open_, y0 + strip_h, h)
                if y1 > y0:
                    frame[y0:y1, :, :] = dst[y0:y1, :, :]
            yield frame


class BlindsVTransition(BaseTransition):
    STRIPS = 8
    def frames(self, src, dst, w, h):
        strip_w = max(1, w // self.STRIPS)
        for i in range(self.STEPS):
            t     = self._ease(i / (self.STEPS - 1))
            open_ = int(strip_w * t)
            frame = src.copy()
            for s in range(self.STRIPS):
                x0 = s * strip_w
                x1 = min(x0 + open_, x0 + strip_w, w)
                if x1 > x0:
                    frame[:, x0:x1, :] = dst[:, x0:x1, :]
            yield frame


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
