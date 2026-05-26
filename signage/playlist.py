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
║ File:        signage/playlist.py                                             ║
║ Version:     1.1.0                                                           ║
║ Author:      Bas                                                             ║
║ Description: Thread-safe playlist manager - loads, saves, and manages        ║
║              playlist items. Handles CRUD operations, navigation, reordering,║
║              and date range filtering. Auto-saves on every change.           ║
║                                                                              ║
║ Important:   All operations are thread-safe via RLock. Provides default      ║
║              playlist on first boot.                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import json
import uuid
import copy
import logging
import threading
import random

log = logging.getLogger('playlist')

# ---------------------------------------------------------------------------
# Default playlist shown on first boot
# ---------------------------------------------------------------------------
DEFAULT_PLAYLIST = [
    {
        "id":           "default-splash",
        "type":         "image",
        "name":         "PixelCast",
        "duration":     10,
        "wipe_in":      "zoom_in",
        "wipe_out":     "fade_black",
        "wipe_in_speed":  5.0,
        "wipe_out_speed": 4.0,
        # Bundled image lives on the read-only SD card — always available
        "file":         "/opt/PixelCast/led-signage/media/pixelcast_final-dark-background.png",
        "scale_mode":   "fit",
        "scale_factor": 0.9,
        "position":     "center",
        "bg_mode":      "color",
        "bg_color":     [0, 0, 0],
    },
    {
        "id":       "default-clock",
        "type":     "clock",
        "name":     "Clock",
        "duration": 15,
        "wipe_in":  "fade",
        "wipe_out": "fade",
        "format":   "%H:%M:%S",
        "date_format": "%A %d %B %Y",
        "color":    [255, 220, 0],
        "bg_color": [0, 0, 0],
    },
    {
        "id":            "default-weather",
        "type":          "weather",
        "name":          "Weather",
        "duration":      15,
        "wipe_in":       "fade",
        "wipe_out":      "fade",
        "latitude":      52.37,
        "longitude":     4.89,
        "location_name": "Amsterdam",
        "units":         "celsius",
        "forecast_days": 3,
        "show_humidity": True,
        "show_wind":     True,
        "bg_mode":       "color",
        "bg_color":      [0, 0, 0],
    },
]

# ---------------------------------------------------------------------------
# Valid transition names (used for validation)
# ---------------------------------------------------------------------------
VALID_TRANSITIONS = {
    'none', 'random',
    'fade', 'fade_black',
    'wipe_left', 'wipe_right', 'wipe_up', 'wipe_down',
    'slide_left', 'slide_right', 'slide_up', 'slide_down',
    'zoom_in', 'zoom_out',
    'dissolve', 'melt', 'snow', 'spiral',
    'drop', 'blinds_h', 'blinds_v', 'checkerboard', 'pixelate'
}

VALID_TYPES = {'image', 'video', 'clock', 'text', 'gif', 'weather', 'countdown'}


class PlaylistManager:
    """
    Thread-safe playlist manager.
    """

    def __init__(self, playlist_path: str, media_dir: str):
        self._path      = playlist_path
        self._media_dir = media_dir
        self._lock      = threading.RLock()
        self._items     = []
        self._index     = -1   # Points to CURRENTLY playing item

        self._load()

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _resolve_file(self, item: dict) -> None:
        """Resolve item's 'file' field to an absolute path in-place."""
        fp = item.get('file', '')
        if fp and not os.path.isabs(fp):
            item['file'] = os.path.join(self._media_dir, os.path.basename(fp))

    def _strip_file(self, item: dict) -> dict:
        """Return a copy of item with 'file' reduced to just the basename."""
        item = item.copy()
        fp = item.get('file', '')
        if fp:
            mdir = self._media_dir.rstrip(os.sep) + os.sep
            if fp.startswith(mdir):
                item['file'] = os.path.basename(fp)
        return item

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        with self._lock:
            if os.path.exists(self._path):
                try:
                    with open(self._path) as f:
                        data = json.load(f)
                    self._items = data if isinstance(data, list) else []
                    # Ensure every item has an id and absolute file paths
                    for item in self._items:
                        if 'id' not in item:
                            item['id'] = str(uuid.uuid4())
                        self._resolve_file(item)
                    log.info(f"Playlist loaded: {len(self._items)} items from {self._path}")
                except Exception as e:
                    log.error(f"Failed to load playlist: {e}")
                    self._items = copy.deepcopy(DEFAULT_PLAYLIST)
            else:
                log.info("No playlist found, using defaults")
                self._items = copy.deepcopy(DEFAULT_PLAYLIST)
                self._save()

    def _save(self):
        """Write playlist to disk with bare filenames. Must be called with lock held."""
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            to_save = [self._strip_file(i) for i in self._items]
            with open(self._path, 'w') as f:
                json.dump(to_save, f, indent=2)
        except Exception as e:
            log.error(f"Failed to save playlist: {e}")

    def reload(self):
        """Reload from disk (e.g. after external edit)."""
        self._load()

    # ------------------------------------------------------------------
    # Playback navigation
    # ------------------------------------------------------------------

    def advance(self) -> dict | None:
        """
        Move to next item and return it.
        Returns None if playlist is empty.
        """
        with self._lock:
            if not self._items:
                return None
            self._index = (self._index + 1) % len(self._items)
            return copy.deepcopy(self._items[self._index])

    def current_item(self) -> dict | None:
        """Return current item without advancing."""
        with self._lock:
            if not self._items or self._index < 0:
                return None
            return copy.deepcopy(self._items[self._index])

    def peek_next(self) -> dict | None:
        """Return the next item without advancing."""
        with self._lock:
            if not self._items:
                return None
            next_idx = (self._index + 1) % len(self._items)
            return copy.deepcopy(self._items[next_idx])

    # ------------------------------------------------------------------
    # CRUD operations (called from web UI)
    # ------------------------------------------------------------------

    def get_all(self) -> list:
        with self._lock:
            return copy.deepcopy(self._items)

    def get_item(self, item_id: str) -> dict | None:
        with self._lock:
            for item in self._items:
                if item['id'] == item_id:
                    return copy.deepcopy(item)
            return None

    def add_item(self, item: dict) -> dict:
        """Add a new item to end of playlist. Returns the item with assigned id."""
        item = copy.deepcopy(item)
        item['id'] = str(uuid.uuid4())
        item = self._apply_defaults(item)
        self._resolve_file(item)   # ensure in-memory path is absolute
        with self._lock:
            self._items.append(item)
            self._save()
        log.info(f"Added item: {item['type']} '{item.get('name','')}'")
        return item

    def update_item(self, item_id: str, updates: dict) -> dict | None:
        """Update an existing item. Returns updated item or None if not found."""
        with self._lock:
            for i, item in enumerate(self._items):
                if item['id'] == item_id:
                    item.update(updates)
                    item['id'] = item_id  # preserve id
                    self._resolve_file(item)   # ensure in-memory path is absolute
                    self._items[i] = item
                    self._save()
                    log.info(f"Updated item: {item_id}")
                    return copy.deepcopy(item)
            return None

    def delete_item(self, item_id: str) -> bool:
        """Remove item from playlist. Returns True if found and removed."""
        with self._lock:
            before = len(self._items)
            self._items = [i for i in self._items if i['id'] != item_id]
            if len(self._items) < before:
                # Adjust index if needed
                if self._index >= len(self._items):
                    self._index = max(0, len(self._items) - 1)
                self._save()
                log.info(f"Deleted item: {item_id}")
                return True
            return False

    def reorder(self, ordered_ids: list) -> bool:
        """Reorder playlist by providing a list of ids in desired order."""
        with self._lock:
            id_to_item = {i['id']: i for i in self._items}
            new_order = []
            for oid in ordered_ids:
                if oid in id_to_item:
                    new_order.append(id_to_item[oid])
            if len(new_order) == len(self._items):
                self._items = new_order
                self._index = -1  # reset to start
                self._save()
                return True
            return False

    def move_item(self, item_id: str, direction: str) -> bool:
        """Move item up or down one position."""
        with self._lock:
            idx = next((i for i, x in enumerate(self._items)
                        if x['id'] == item_id), None)
            if idx is None:
                return False
            if direction == 'up' and idx > 0:
                self._items[idx], self._items[idx-1] = \
                    self._items[idx-1], self._items[idx]
            elif direction == 'down' and idx < len(self._items) - 1:
                self._items[idx], self._items[idx+1] = \
                    self._items[idx+1], self._items[idx]
            else:
                return False
            self._save()
            return True

    def duplicate_item(self, item_id: str) -> dict | None:
        """Duplicate an item and insert after original."""
        with self._lock:
            for i, item in enumerate(self._items):
                if item['id'] == item_id:
                    new_item = copy.deepcopy(item)
                    new_item['id'] = str(uuid.uuid4())
                    new_item['name'] = new_item.get('name', '') + ' (copy)'
                    self._items.insert(i + 1, new_item)
                    self._save()
                    return copy.deepcopy(new_item)
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_defaults(self, item: dict) -> dict:
        """Apply sensible defaults to a new item."""
        item.setdefault('name', item.get('type', 'item').title())
        item.setdefault('duration', 10)
        item.setdefault('wipe_in', 'fade')
        item.setdefault('wipe_out', 'fade')

        t = item.get('type')
        if t == 'clock':
            item.setdefault('format', '%H:%M:%S')
            item.setdefault('date_format', '%A %d %B %Y')
            item.setdefault('color', [255, 220, 0])
            item.setdefault('bg_color', [0, 0, 0])
        elif t == 'text':
            item.setdefault('lines', [
                {"text": "New Message", "color": [255,255,255],
                 "font_size": 20, "align": "center"}
            ])
            item.setdefault('bg_color', [0, 0, 0])
            item.setdefault('scroll', False)
        elif t in ('image', 'gif', 'video'):
            item.setdefault('bg_color', [0, 0, 0])
            item.setdefault('bg_mode', 'color')
        return item

    def resolve_transition(self, name: str) -> str:
        """Resolve 'random' to an actual effect name."""
        if name == 'random':
            choices = list(VALID_TRANSITIONS - {'none', 'random'})
            return random.choice(choices)
        return name

    def __len__(self):
        with self._lock:
            return len(self._items)
