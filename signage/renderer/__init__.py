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
║ File:        signage/renderer/__init__.py                                    ║
║ Version:     1.1.0                                                           ║
║ Author:      Bas                                                             ║
║ Description: Renderer factory - creates appropriate renderer instances based ║
║              on playlist item type. Supports: image, gif, video, clock,      ║
║              text, weather, countdown.                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import logging
from .base import BaseRenderer

log = logging.getLogger('renderer')


def get_renderer(item: dict, width: int, height: int,
                 lightweight: bool = False) -> BaseRenderer:
    """
    Factory: return the correct renderer for a playlist item.
    """
    t = item.get('type', '').lower()

    if t == 'image':
        from .image import ImageRenderer
        return ImageRenderer(item, width, height)

    elif t == 'gif':
        from .image import GifRenderer
        return GifRenderer(item, width, height)

    elif t == 'video':
        from .video import VideoRenderer
        return VideoRenderer(item, width, height, lightweight=lightweight)

    elif t == 'clock':
        from .clock import ClockRenderer
        return ClockRenderer(item, width, height)

    elif t == 'text':
        from .text import TextRenderer
        return TextRenderer(item, width, height)
    elif t == 'weather':
        from .weather import WeatherRenderer
        return WeatherRenderer(item, width, height, lightweight=lightweight)
    elif t == 'countdown':
        from .countdown import CountdownRenderer
        return CountdownRenderer(item, width, height, lightweight=lightweight)

    else:
        log.error(f"Unknown renderer type: '{t}'")
        from .base import BlackRenderer
        return BlackRenderer(item, width, height)


__all__ = ['get_renderer', 'BaseRenderer']
