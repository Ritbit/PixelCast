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
║ File:        signage/watchdog.py                                             ║
║ Version:     1.3.1                                                           ║
║ Author:      Bas                                                             ║
║ Description: Health monitoring watchdog - monitors MatrixEngine frame age    ║
║              and restarts daemon if display freezes beyond timeout.          ║
║                                                                              ║
║ Important:   Pauses monitoring during intentional pause to avoid false       ║
║              positives. Default timeout: 30 seconds.                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import time
import logging
import threading
import subprocess

log = logging.getLogger('watchdog')


class Watchdog:
    def __init__(self, engine, timeout_s: int = 30):
        self._engine    = engine
        self._timeout   = timeout_s
        self._stop      = threading.Event()
        self._thread    = None
        self._triggered = False

    def start(self):
        self._thread = threading.Thread(
            target=self._run, name='Watchdog', daemon=True)
        self._thread.start()
        log.info(f"Watchdog started (timeout={self._timeout}s)")

    def stop(self):
        self._stop.set()

    def _run(self):
        # Give the engine time to initialise before we start watching
        self._stop.wait(15)

        while not self._stop.is_set():
            try:
                # Don't fire while paused — display is intentionally frozen
                if not self._engine._pause_event.is_set():
                    age = time.time() - self._engine._last_frame_time
                    if age > self._timeout:
                        log.error(
                            f"Watchdog: engine appears frozen "
                            f"({age:.0f}s since last frame). "
                            f"Restarting daemon.")
                        self._triggered = True
                        subprocess.Popen(
                            ['systemctl', 'restart', 'led-signage'])
                        return
            except Exception as e:
                log.warning(f"Watchdog check error: {e}")

            self._stop.wait(10)

    @property
    def triggered(self) -> bool:
        return self._triggered
