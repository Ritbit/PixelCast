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
║ File:        signage/alert.py                                                ║
║ Version:     1.1.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: High-priority alert overlay system - composites alerts on top   ║
║              of regular playlist content using TextRenderer. Supports all    ║
║              text features: multi-line, scrolling, backgrounds, styling.     ║
║                                                                              ║
║ Important:   Called by engine show_frame() every frame. Auto-expires after   ║
║              configured duration.                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import time
import threading
import logging
import numpy as np

log = logging.getLogger('alert')


class AlertManager:
    """
    Manages high-priority alert overlays composited on top of playlist content.
    Uses TextRenderer for rendering with full text feature support.
    """
    
    def __init__(self, engine):
        """
        Initialize alert manager.
        
        Args:
            engine (MatrixEngine): Reference to matrix engine for display dimensions
        """
        self._engine   = engine
        self._lock     = threading.Lock()
        self._active   = False
        self._cfg      = {}
        self._expires  = 0.0
        self._renderer = None   # TextRenderer instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self, cfg: dict):
        """
        Display a multi-line alert overlay.
        
        Args:
            cfg (dict): Alert configuration matching TextRenderer format:
                - lines (list): Line dicts with text, color, font, font_size, align, scroll, etc.
                - bg_color (list): RGB background color [R,G,B]
                - bg_image (str): Path to background image
                - bg_dim (int): Background dim percentage 0-100
                - bg_mode (str): 'color' or 'image'
                - v_center (bool): Vertically center text
                - duration (int): Display duration in seconds (default 10)
        """
        duration = int(cfg.get('duration', 10))
        with self._lock:
            self._cfg      = dict(cfg)
            self._expires  = time.time() + duration
            self._active   = True
            self._renderer = None   # force rebuild on next get_frame
        log.info(f"Alert shown ({duration}s): "
                 f"{[l.get('text','') for l in cfg.get('lines',[])[:2]]}")

    def clear(self):
        """Clear the active alert immediately."""
        with self._lock:
            self._active   = False
            self._renderer = None
        log.info("Alert cleared")

    def is_active(self) -> bool:
        """
        Check if alert is currently active and not expired.
        
        Returns:
            bool: True if alert is active and not expired
        """
        with self._lock:
            if not self._active:
                return False
            if time.time() >= self._expires:
                self._active   = False
                self._renderer = None
                return False
            return True

    def remaining_seconds(self) -> float:
        """
        Get remaining display time for active alert.
        
        Returns:
            float: Remaining seconds (0.0 if no active alert)
        """
        with self._lock:
            return max(0.0, self._expires - time.time())

    # ------------------------------------------------------------------
    # Frame compositor
    # ------------------------------------------------------------------

    def get_frame(self, base_frame: np.ndarray,
                  width: int, height: int):
        """
        Composite alert overlay on top of base frame.
        Called by engine's show_frame() every frame.
        
        Args:
            base_frame (np.ndarray): Base frame from playlist renderer
            width (int): Display width in pixels
            height (int): Display height in pixels
        
        Returns:
            np.ndarray: Composited frame with alert overlay
        Returns a numpy (H,W,3) frame if alert is active, else None.
        """
        if not self.is_active():
            return None

        with self._lock:
            cfg      = self._cfg.copy()
            renderer = self._renderer

        # Build renderer lazily (first call after show())
        if renderer is None:
            try:
                from signage.renderer.text import TextRenderer
                renderer = TextRenderer(cfg, width, height)
                with self._lock:
                    self._renderer = renderer
            except Exception as e:
                log.error(f"Alert renderer build failed: {e}")
                return None

        try:
            # Use frames() generator for animated alerts
            if not hasattr(renderer, '_alert_gen'):
                renderer._alert_gen = renderer.frames()
            return next(renderer._alert_gen)
        except StopIteration:
            return renderer.first_frame()
        except Exception as e:
            log.error(f"Alert render failed: {e}")
            return None
