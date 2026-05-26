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
║ File:        signage/scheduler.py                                            ║
║ Version:     1.1.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Time-based display scheduler - manages on/off/dim rules by day  ║
║              of week and time. Runs as background daemon thread, checks      ║
║              rules every 30 seconds and controls MatrixEngine accordingly.   ║
║                                                                              ║
║ Important:   Supports timezone-aware scheduling. Days: 0=Monday...6=Sunday.  ║
║              Config stored in config/schedule.json.                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import json
import os
import time
import logging
import threading
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

log = logging.getLogger('scheduler')

DEFAULT_SCHEDULE = {
    "enabled": False,
    "timezone": "Europe/Amsterdam",
    "rules": []
}


class Scheduler:
    def __init__(self, config_path: str, engine):
        self._path   = config_path
        self._engine = engine
        self._cfg    = DEFAULT_SCHEDULE.copy()
        self._stop   = threading.Event()
        self._thread = None
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    self._cfg = json.load(f)
                log.info(f"Schedule loaded: {len(self._cfg.get('rules',[]))} rules")
            except Exception as e:
                log.error(f"Failed to load schedule: {e}")
        else:
            self._save()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, 'w') as f:
                json.dump(self._cfg, f, indent=2)
        except Exception as e:
            log.error(f"Failed to save schedule: {e}")

    def get_config(self) -> dict:
        return self._cfg.copy()

    def update_config(self, cfg: dict):
        self._cfg = cfg
        self._save()
        log.info("Schedule updated")

    # ------------------------------------------------------------------
    # Scheduler loop
    # ------------------------------------------------------------------

    def start(self):
        self._thread = threading.Thread(
            target=self._run, name='Scheduler', daemon=True)
        self._thread.start()
        log.info("Scheduler started")

    def stop(self):
        self._stop.set()

    def _run(self):
        """Check schedule every 30 seconds."""
        while not self._stop.is_set():
            try:
                self._apply()
            except Exception as e:
                log.error(f"Scheduler error: {e}")
            self._stop.wait(30)

    def _apply(self):
        if not self._cfg.get('enabled', False):
            return

        rules = self._cfg.get('rules', [])
        if not rules:
            return

        tz_name = self._cfg.get('timezone', 'UTC')
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            log.warning(f"Invalid timezone '{tz_name}', falling back to UTC")
            tz = ZoneInfo('UTC')
        now     = datetime.now(tz=tz)
        weekday = now.weekday()   # 0=Monday, 6=Sunday
        now_min = now.hour * 60 + now.minute

        # Find the most recently passed rule for today
        # Rules are evaluated in time order — last applicable rule wins
        applicable = []
        for rule in rules:
            days = rule.get('days', list(range(7)))
            if weekday not in days:
                continue
            t_str = rule.get('time', '00:00')
            try:
                h, m   = map(int, t_str.split(':'))
                rule_min = h * 60 + m
            except Exception:
                continue
            if rule_min <= now_min:
                applicable.append((rule_min, rule))

        if not applicable:
            return

        # Most recently passed rule
        applicable.sort(key=lambda x: x[0])
        _, active_rule = applicable[-1]

        action = active_rule.get('action', 'on')

        if action == 'off':
            if not self._engine._pause_event.is_set():
                log.info("Scheduler: turning display OFF")
                self._engine.pause()

        elif action == 'on':
            if self._engine._pause_event.is_set():
                log.info("Scheduler: turning display ON")
                self._engine.pause()  # toggle back on
            # Restore full brightness if previously dimmed
            full = self._engine.cfg.get('brightness', 80)
            self._engine.set_brightness(full)

        elif action == 'dim':
            if self._engine._pause_event.is_set():
                self._engine.pause()  # make sure display is on
            brightness = active_rule.get('brightness', 30)
            log.info(f"Scheduler: dimming to {brightness}%")
            self._engine.set_brightness(brightness)

    def next_event(self) -> dict | None:
        """Return info about the next scheduled event (for UI display)."""
        if not self._cfg.get('enabled', False):
            return None

        rules   = self._cfg.get('rules', [])
        now     = datetime.now()
        weekday = now.weekday()
        now_min = now.hour * 60 + now.minute

        upcoming = []
        for day_offset in range(7):
            check_day = (weekday + day_offset) % 7
            for rule in rules:
                days = rule.get('days', list(range(7)))
                if check_day not in days:
                    continue
                t_str = rule.get('time', '00:00')
                try:
                    h, m     = map(int, t_str.split(':'))
                    rule_min = h * 60 + m
                except Exception:
                    continue

                total_min = day_offset * 1440 + rule_min
                if day_offset == 0 and rule_min <= now_min:
                    continue   # already passed today

                upcoming.append({
                    'minutes_from_now': total_min - now_min,
                    'action':    rule.get('action'),
                    'time':      t_str,
                    'day_offset': day_offset,
                    'brightness': rule.get('brightness')
                })

        if not upcoming:
            return None

        upcoming.sort(key=lambda x: x['minutes_from_now'])
        return upcoming[0]
