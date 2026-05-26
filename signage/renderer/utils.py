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
║ File:        signage/renderer/utils.py                                       ║
║ Version:     1.1.0                                                           ║
║ Author:      Bas                                                             ║
║ Description: Shared rendering utilities - background loading with caching,   ║
║              image positioning, scaling, color parsing, and Ken Burns effect.║
║              Used by image, video, clock, and text renderers.                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import numpy as np
from PIL import Image
import logging

log = logging.getLogger('renderer.utils')


def parse_color(value, default=(255, 255, 255)) -> tuple:
    """
    Accept any color format and return an (R, G, B) tuple of ints.
    Handles:
      - [R, G, B] list  (from JSON)
      - (R, G, B) tuple
      - "#rrggbb" hex string  (from <input type=color>)
      - int (greyscale)
    """
    try:
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return tuple(int(v) for v in value[:3])
        if isinstance(value, str):
            hx = value.lstrip('#')
            if len(hx) == 6:
                return (int(hx[0:2], 16),
                        int(hx[2:4], 16),
                        int(hx[4:6], 16))
        if isinstance(value, int):
            return (value, value, value)
    except Exception:
        pass
    return tuple(default)


# ---------------------------------------------------------------------------
# Background canvas
# ---------------------------------------------------------------------------

def _bg_cache_path(image_path: str, width: int, height: int,
                   scale: str, factor: float, ox: int, oy: int,
                   dim: int) -> str:
    """Unique cache filename for a given set of bg parameters."""
    import hashlib, os
    key  = f"{width}x{height}_{scale}_{factor:.2f}_{ox}_{oy}_{dim}"
    h    = hashlib.md5(key.encode()).hexdigest()[:8]
    base = os.path.splitext(image_path)[0]
    return f"{base}.bgcache_{h}.jpg"


def load_background(width: int, height: int, item: dict,
                    src_img: Image.Image = None) -> Image.Image:
    """
    Build a background PIL Image (RGB, display size) from item config.

    bg_mode:
      'color'  → solid color from bg_color [R,G,B]
      'corner' → sample a corner of src_img (requires src_img)
      'image'  → load bg_image file scaled to display

    Background image scaling (bg_mode='image'):
      bg_scale  : 'cover'  (fill, crop edges — default)
                  'contain' (fit, black bars)
                  'stretch' (distort to fill)
                  'custom'  (use bg_scale_factor)
      bg_scale_factor : 0.1–2.0, only for 'custom'
      bg_offset_x : -100..100 % horizontal offset from centre
      bg_offset_y : -100..100 % vertical offset from centre
      bg_dim      : 0–100, dims toward black

    Results are cached to a sidecar .bgcache_*.jpg so the
    expensive LANCZOS scale only runs once per unique config.
    """
    import os
    mode = item.get('bg_mode', 'color')

    if mode == 'corner' and src_img is not None:
        color = _sample_corner(src_img, item.get('bg_corner', 'top-left'))
        return Image.new('RGB', (width, height), color)

    elif mode == 'image':
        path = item.get('bg_image', '')
        if path and os.path.exists(path):
            try:
                bg_scale  = item.get('bg_scale', 'cover')
                bg_factor = float(item.get('bg_scale_factor', 1.0))
                bg_ox     = int(item.get('bg_offset_x', 0))
                bg_oy     = int(item.get('bg_offset_y', 0))
                dim       = int(item.get('bg_dim', 0))

                # Check pre-scaled cache
                cache_path = _bg_cache_path(
                    path, width, height, bg_scale, bg_factor, bg_ox, bg_oy, dim)

                if os.path.exists(cache_path) and                    os.path.getmtime(cache_path) >= os.path.getmtime(path):
                    return Image.open(cache_path).convert('RGB')

                # Build from source
                bg = Image.open(path).convert('RGB')
                bg = _scale_background(bg, width, height,
                                       bg_scale, bg_factor, bg_ox, bg_oy)

                if dim > 0:
                    overlay = Image.new('RGB', (width, height), (0, 0, 0))
                    bg = Image.blend(bg, overlay, dim / 100)

                # Save cache (best-effort)
                try:
                    bg.save(cache_path, 'JPEG', quality=85, optimize=True)
                    log.debug(f"bg cache saved: {os.path.basename(cache_path)}")
                except Exception:
                    pass

                return bg

            except Exception as e:
                log.warning(f"bg_image load failed: {e}")

    # Default: solid color
    color = parse_color(item.get('bg_color', [0, 0, 0]))
    return Image.new('RGB', (width, height), color)


def _scale_background(bg: Image.Image, width: int, height: int,
                      scale: str, factor: float,
                      offset_x: int, offset_y: int) -> Image.Image:
    """
    Scale and crop/pad a background image to exactly (width, height).

    offset_x/y: -100 to +100 percent of the overflow in each axis.
    0 = centred (default), -100 = top/left edge, +100 = bottom/right edge.
    """
    bw, bh = bg.size

    if scale == 'contain':
        # Fit inside display — letterbox with black
        ratio = min(width / bw, height / bh)
        nw    = int(bw * ratio)
        nh    = int(bh * ratio)
        bg    = bg.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new('RGB', (width, height), (0, 0, 0))
        x = (width  - nw) // 2
        y = (height - nh) // 2
        canvas.paste(bg, (x, y))
        return canvas

    elif scale == 'stretch':
        return bg.resize((width, height), Image.LANCZOS)

    elif scale == 'custom':
        factor = max(0.1, min(4.0, factor))
        nw = int(width  * factor)
        nh = int(height * factor)
        bg = bg.resize((nw, nh), Image.LANCZOS)
        # Fall through to offset crop below

    else:  # cover (default)
        ratio = max(width / bw, height / bh)
        nw    = int(bw * ratio)
        nh    = int(bh * ratio)
        bg    = bg.resize((nw, nh), Image.LANCZOS)

    # Crop to display size, using offset to choose which part
    bw, bh   = bg.size
    overflow_x = bw - width
    overflow_y = bh - height
    left = int(overflow_x * (offset_x + 100) / 200) if overflow_x > 0 else 0
    top  = int(overflow_y * (offset_y + 100) / 200) if overflow_y > 0 else 0
    left = max(0, min(left, overflow_x))
    top  = max(0, min(top,  overflow_y))

    canvas = Image.new('RGB', (width, height), (0, 0, 0))
    canvas.paste(bg, (-left, -top))
    return canvas


def _sample_corner(img: Image.Image, corner: str, radius: int = 4) -> tuple:
    w, h = img.size
    r    = min(radius, w // 4, h // 4, 4)
    regions = {
        'top-left':     (0,     0,     r,     r),
        'top-right':    (w - r, 0,     w,     r),
        'bottom-left':  (0,     h - r, r,     h),
        'bottom-right': (w - r, h - r, w,     h),
    }
    box    = regions.get(corner, (0, 0, r, r))
    region = img.convert('RGB').crop(box)
    arr    = np.array(region)
    return tuple(arr.mean(axis=(0, 1)).astype(int).tolist())


# ---------------------------------------------------------------------------
# Image positioning onto background canvas
# ---------------------------------------------------------------------------

POSITIONS = [
    'top-left', 'top-center', 'top-right',
    'middle-left', 'center', 'middle-right',
    'bottom-left', 'bottom-center', 'bottom-right',
]


def paste_at(canvas: Image.Image, img: Image.Image,
             position: str = 'center') -> Image.Image:
    """
    Paste img onto canvas at the given named position.
    Returns canvas (modified in-place).
    """
    cw, ch = canvas.size
    iw, ih = img.size
    margin = 0   # px padding from edges

    if 'left' in position:
        x = margin
    elif 'right' in position:
        x = cw - iw - margin
    else:   # center
        x = (cw - iw) // 2

    if 'top' in position:
        y = margin
    elif 'bottom' in position:
        y = ch - ih - margin
    else:   # middle / center
        y = (ch - ih) // 2

    canvas.paste(img, (x, y))
    return canvas


def fit_image(img: Image.Image, width: int, height: int,
              scale_mode: str = 'fit',
              scale_factor: float = 1.0,
              fast: bool = False) -> Image.Image:
    """Resize image. fast=True uses BILINEAR (for video frames)."""
    resample     = Image.BILINEAR if fast else Image.LANCZOS
    scale_factor = max(0.05, min(1.0, scale_factor))

    if scale_mode == 'stretch':
        return img.resize((width, height), resample)
    elif scale_mode == 'fill':
        ratio = max(width / img.width, height / img.height)
        nw    = int(img.width  * ratio)
        nh    = int(img.height * ratio)
        img   = img.resize((nw, nh), resample)
        l     = (nw - width)  // 2
        t     = (nh - height) // 2
        return img.crop((l, t, l + width, t + height))
    else:
        target_w = int(width  * scale_factor)
        target_h = int(height * scale_factor)
        img = img.copy()
        img.thumbnail((target_w, target_h), resample)
        return img


# ---------------------------------------------------------------------------
# Ken Burns effect
# ---------------------------------------------------------------------------

class KenBurns:
    """
    Produces a sequence of cropped numpy frames from a PIL source image,
    slowly panning and zooming for a cinematic effect.

    Usage:
        kb = KenBurns(pil_image, display_width, display_height, item)
        for frame in kb.frames(fps=25):
            engine.show_frame(frame)
    """

    def __init__(self, img: Image.Image, width: int, height: int, item: dict):
        self.width  = width
        self.height = height

        zoom_start = float(item.get('kb_zoom_start', 1.0))
        zoom_end   = float(item.get('kb_zoom_end',   1.25))
        direction  = item.get('kb_direction', 'random')

        # Clamp
        zoom_start = max(1.0, zoom_start)
        zoom_end   = max(zoom_start, zoom_end)

        import random
        if direction == 'random':
            direction = random.choice(['in', 'out', 'pan_left',
                                       'pan_right', 'pan_up', 'pan_down'])

        # Upscale source so we have headroom for the zoom
        # We need the image to fill the display even at zoom_end
        needed_scale = zoom_end * 1.05
        src_w = int(width  * needed_scale)
        src_h = int(height * needed_scale)

        # Maintain aspect ratio, covering src_w x src_h
        ratio = max(src_w / img.width, src_h / img.height)
        nw    = int(img.width  * ratio)
        nh    = int(img.height * ratio)
        self._src = img.resize((nw, nh), Image.LANCZOS)

        # Compute start and end crop boxes (in source coords)
        self._start_box = self._zoom_box(zoom_start, direction, start=True)
        self._end_box   = self._zoom_box(zoom_end,   direction, start=False)

    def _zoom_box(self, zoom: float, direction: str, start: bool) -> tuple:
        """Return (left, top, right, bottom) crop box in source pixel coords."""
        sw, sh  = self._src.size
        cw      = int(self.width  / zoom)
        ch      = int(self.height / zoom)

        # Anchor position based on direction
        if direction in ('pan_right', 'pan_up'):
            cx = sw // 2 - (sw // 6 if start else -sw // 6)
            cy = sh // 2 - (sh // 6 if direction == 'pan_up' and start
                             else sh // 6 if direction == 'pan_up' else 0)
        elif direction in ('pan_left', 'pan_down'):
            cx = sw // 2 + (sw // 6 if start else -sw // 6)
            cy = sh // 2 + (sh // 6 if direction == 'pan_down' and start
                             else -sh // 6 if direction == 'pan_down' else 0)
        else:   # in / out — stay centred
            cx = sw // 2
            cy = sh // 2

        left   = max(0, cx - cw // 2)
        top    = max(0, cy - ch // 2)
        left   = min(left, sw - cw)
        top    = min(top,  sh - ch)
        return (left, top, left + cw, top + ch)

    def frames(self, fps: float = 25.0):
        """
        Generator — yields numpy (H, W, 3) uint8 frames indefinitely,
        looping the Ken Burns animation.
        """
        import time
        CYCLE = 8.0   # seconds per zoom cycle before reversing
        frame_period = 1.0 / fps
        t0    = time.perf_counter()

        while True:
            now   = time.perf_counter()
            cycle_t = (now - t0) % (CYCLE * 2)
            # Ping-pong: 0→CYCLE forward, CYCLE→2*CYCLE reverse
            if cycle_t <= CYCLE:
                t = cycle_t / CYCLE
            else:
                t = 1.0 - (cycle_t - CYCLE) / CYCLE
            t = _ease(t)

            # Interpolate crop box
            sb, eb = self._start_box, self._end_box
            box = (
                int(sb[0] + (eb[0] - sb[0]) * t),
                int(sb[1] + (eb[1] - sb[1]) * t),
                int(sb[2] + (eb[2] - sb[2]) * t),
                int(sb[3] + (eb[3] - sb[3]) * t),
            )

            crop    = self._src.crop(box)
            resized = crop.resize((self.width, self.height), Image.LANCZOS)
            yield np.array(resized, dtype=np.uint8)

            deadline = now + frame_period
            sleep    = deadline - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)


def _ease(t: float) -> float:
    """Smooth-step easing."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)
