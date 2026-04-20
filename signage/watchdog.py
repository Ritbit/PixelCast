"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/watchdog.py                                             ║
║ Version:     1.0.0                                                           ║
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
