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
overlay.py - Overlay system for compositing on top of content

Overlays are rendered on top of playlist content and can show:
- Date/time
- Static text
- Temperature/weather (future)
- RSS feeds (future)
"""

import logging
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from pathlib import Path

log = logging.getLogger('overlay')

# Font cache
_FONT_CACHE = {}


def get_font(name: str, size: int):
    """Get cached font or load it."""
    key = (name, size)
    if key not in _FONT_CACHE:
        try:
            font_path = Path('/usr/share/fonts/truetype') / name
            if not font_path.exists():
                font_path = Path(__file__).parent.parent / 'fonts' / name
            _FONT_CACHE[key] = ImageFont.truetype(str(font_path), size)
        except Exception as e:
            log.warning(f"Font load failed ({name} {size}): {e}, using default")
            _FONT_CACHE[key] = ImageFont.load_default()
    return _FONT_CACHE[key]


class Overlay:
    """Base overlay class."""
    
    def __init__(self, config: dict):
        self.enabled = config.get('enabled', False)
        self.position = config.get('position', 'top-right')  # top-left, top-right, bottom-left, bottom-right
        self.offset_x = config.get('offset_x', 2)
        self.offset_y = config.get('offset_y', 2)
        self.bg_color = tuple(config.get('bg_color', [0, 0, 0])[:3])
        self.bg_alpha = config.get('bg_alpha', 128)  # 0-255
        self.padding = config.get('padding', 2)
    
    def render(self, width: int, height: int) -> np.ndarray:
        """
        Render overlay content.
        Returns RGBA numpy array (H, W, 4) or None if nothing to render.
        """
        raise NotImplementedError
    
    def composite(self, base_frame: np.ndarray, width: int, height: int) -> np.ndarray:
        """Composite overlay onto base frame."""
        if not self.enabled:
            return base_frame
        
        overlay_rgba = self.render(width, height)
        if overlay_rgba is None:
            return base_frame
        
        # Convert base to RGBA if needed
        if base_frame.shape[2] == 3:
            base_rgba = np.dstack([base_frame, np.full((height, width), 255, dtype=np.uint8)])
        else:
            base_rgba = base_frame.copy()
        
        # Calculate position
        ov_h, ov_w = overlay_rgba.shape[:2]
        
        if 'top' in self.position:
            y = self.offset_y
        else:  # bottom
            y = height - ov_h - self.offset_y
        
        if 'left' in self.position:
            x = self.offset_x
        else:  # right
            x = width - ov_w - self.offset_x
        
        # Clamp to bounds
        y = max(0, min(y, height - ov_h))
        x = max(0, min(x, width - ov_w))
        
        # Alpha blend
        alpha = overlay_rgba[:, :, 3:4] / 255.0
        base_rgba[y:y+ov_h, x:x+ov_w, :3] = (
            overlay_rgba[:, :, :3] * alpha +
            base_rgba[y:y+ov_h, x:x+ov_w, :3] * (1 - alpha)
        ).astype(np.uint8)
        
        # Return RGB only
        return base_rgba[:, :, :3]


class DateTimeOverlay(Overlay):
    """Date/time overlay."""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.format = config.get('format', '%H:%M')  # strftime format
        self.font = config.get('font', 'FreeSans.ttf')
        self.font_size = config.get('font_size', 12)
        self.color = tuple(config.get('color', [255, 255, 255])[:3])
    
    def render(self, width: int, height: int) -> np.ndarray:
        """Render current date/time."""
        try:
            text = datetime.now().strftime(self.format)
            font = get_font(self.font, self.font_size)
            
            # Measure text
            dummy = Image.new('RGB', (1, 1))
            draw = ImageDraw.Draw(dummy)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            
            # Create overlay with padding
            ov_w = text_w + self.padding * 2
            ov_h = text_h + self.padding * 2
            
            img = Image.new('RGBA', (ov_w, ov_h), (*self.bg_color, self.bg_alpha))
            draw = ImageDraw.Draw(img)
            draw.text((self.padding, self.padding), text, font=font, fill=(*self.color, 255))
            
            return np.array(img)
        except Exception as e:
            log.error(f"DateTimeOverlay render failed: {e}")
            return None


class TextOverlay(Overlay):
    """Static text overlay."""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.text = config.get('text', '')
        self.font = config.get('font', 'FreeSans.ttf')
        self.font_size = config.get('font_size', 10)
        self.color = tuple(config.get('color', [255, 255, 255])[:3])
    
    def render(self, width: int, height: int) -> np.ndarray:
        """Render static text."""
        if not self.text:
            return None
        
        try:
            font = get_font(self.font, self.font_size)
            
            # Measure text
            dummy = Image.new('RGB', (1, 1))
            draw = ImageDraw.Draw(dummy)
            bbox = draw.textbbox((0, 0), self.text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            
            # Create overlay with padding
            ov_w = text_w + self.padding * 2
            ov_h = text_h + self.padding * 2
            
            img = Image.new('RGBA', (ov_w, ov_h), (*self.bg_color, self.bg_alpha))
            draw = ImageDraw.Draw(img)
            draw.text((self.padding, self.padding), self.text, font=font, fill=(*self.color, 255))
            
            return np.array(img)
        except Exception as e:
            log.error(f"TextOverlay render failed: {e}")
            return None


class OverlayManager:
    """Manages multiple overlays."""
    
    def __init__(self, config: dict):
        self.overlays = []
        self._load_overlays(config)
    
    def _load_overlays(self, config: dict):
        """Load overlays from config."""
        self.overlays = []
        
        # DateTime overlay
        if 'datetime' in config:
            self.overlays.append(DateTimeOverlay(config['datetime']))
        
        # Text overlay
        if 'text' in config:
            self.overlays.append(TextOverlay(config['text']))
        
        enabled_count = sum(1 for o in self.overlays if o.enabled)
        log.info(f"OverlayManager: {enabled_count}/{len(self.overlays)} overlays enabled")
    
    def reload(self, config: dict):
        """Reload overlays from new config."""
        self._load_overlays(config)
    
    def composite(self, frame: np.ndarray, width: int, height: int) -> np.ndarray:
        """Apply all enabled overlays to frame."""
        result = frame
        for overlay in self.overlays:
            if overlay.enabled:
                result = overlay.composite(result, width, height)
        return result
