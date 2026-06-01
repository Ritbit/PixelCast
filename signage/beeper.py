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
║ File:        signage/beeper.py                                               ║
║ Version:     1.3.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Active-buzzer driver for GPIO-based attention beeps.            ║
║              GPIO pin is configurable via panel.json (beeper_gpio).          ║
║              All patterns run in a daemon thread — render loop untouched.    ║
║                                                                              ║
║ Important:   Requires RPi.GPIO (Pi 4) or rpi-lgpio (Pi 5 drop-in shim).     ║
║              Only imported when beeper_gpio is set in panel.json.            ║
║              Use an ACTIVE buzzer; passive buzzers need PWM which conflicts  ║
║              with the LED matrix driver.                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝

Beep patterns
─────────────
  short   — single 0.5 s beep
  long    — single 1.0 s beep
  triple  — three 0.5 s beeps, 0.2 s gap between each
  alert   — continuous 1 s on / 1 s off until stop() is called or
            the optional `until` timestamp expires (use with alert duration)

Wiring (active buzzer, BCM GPIO 26 default)
─────────────────────────────────────────────
  GPIO26 ── 1 kΩ ── BC547/2N2222 base
  collector ── buzzer + ── 3.3 V
  emitter  ── GND

  Or for low-current buzzers (<16 mA): GPIO26 ── buzzer + ── buzzer - ── GND
"""

import time
import threading
import logging

log = logging.getLogger('beeper')

DEFAULT_GPIO = 26

# Pattern definitions: list of (duration_s, pin_high) tuples.
# None is a sentinel for the continuous 'alert' mode.
_PATTERNS: dict = {
    'short':  [(0.5, True)],
    'long':   [(1.0, True)],
    'triple': [(0.5, True), (0.2, False),
               (0.5, True), (0.2, False),
               (0.5, True)],
    'alert':  None,   # continuous: 1 s on / 1 s off
}


class Beeper:
    """
    Active-buzzer driver.  HIGH = on, LOW = off.

    All beep patterns execute in a short daemon thread so the render loop
    and the web thread are never blocked.  A new beep() call silences any
    in-progress pattern before starting the new one.
    """

    def __init__(self, gpio_pin: int = DEFAULT_GPIO):
        """
        Initialise GPIO for the buzzer pin.

        Raises ImportError if neither RPi.GPIO nor rpi-lgpio is installed.
        On Raspberry Pi 5 install the shim:  pip install rpi-lgpio
        """
        try:
            import RPi.GPIO as GPIO          # Pi 4, or Pi 5 with rpi-lgpio
        except ImportError as exc:
            raise ImportError(
                "RPi.GPIO not found. "
                "Pi 4: pip install RPi.GPIO  |  Pi 5: pip install rpi-lgpio"
            ) from exc

        self._GPIO   = GPIO
        self._pin    = gpio_pin
        self._lock   = threading.Lock()
        self._stop   = threading.Event()
        self._thread: threading.Thread | None = None

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(gpio_pin, GPIO.OUT, initial=GPIO.LOW)
        log.info(f"Beeper: active buzzer initialised on BCM GPIO {gpio_pin}")

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def gpio_pin(self) -> int:
        return self._pin

    def beep(self, pattern: str = 'short', until: float = 0.0) -> None:
        """
        Fire a beep pattern in a background thread.  Non-blocking.

        Args:
            pattern: 'short' | 'long' | 'triple' | 'alert'
            until:   Unix timestamp at which to stop the 'alert' pattern
                     (typically alert_manager._expires).  Ignored for
                     one-shot patterns.
        """
        if pattern not in _PATTERNS:
            log.warning(f"Beeper: unknown pattern '{pattern}', falling back to 'short'")
            pattern = 'short'

        self.stop()                     # silence any in-progress beep first
        self._stop.clear()

        t = threading.Thread(
            target=self._run,
            args=(pattern, until),
            daemon=True,
            name='BeeperThread',
        )
        with self._lock:
            self._thread = t
        t.start()
        log.debug(f"Beeper: pattern '{pattern}' started")

    def stop(self) -> None:
        """Immediately silence any active beep or continuous pattern."""
        self._stop.set()
        with self._lock:
            t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=0.15)        # fast: thread checks _stop every 50 ms
        self._pin_set(False)

    def close(self) -> None:
        """Release the GPIO pin on daemon shutdown."""
        self.stop()
        try:
            self._GPIO.cleanup(self._pin)
        except Exception:
            pass
        log.info(f"Beeper: GPIO {self._pin} released")

    # ── internals ─────────────────────────────────────────────────────────────

    def _pin_set(self, high: bool) -> None:
        try:
            self._GPIO.output(self._pin,
                              self._GPIO.HIGH if high else self._GPIO.LOW)
        except Exception as exc:
            log.debug(f"Beeper _pin_set({high}): {exc}")

    def _sleep(self, seconds: float) -> None:
        """Interruptible sleep — wakes within 50 ms of stop() being called."""
        deadline = time.monotonic() + seconds
        while not self._stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.05, remaining))

    def _run(self, pattern: str, until: float) -> None:
        steps = _PATTERNS[pattern]
        try:
            if steps is None:
                # Continuous alert: 1 s on / 1 s off
                while not self._stop.is_set():
                    if until and time.time() >= until:
                        break
                    self._pin_set(True)
                    self._sleep(1.0)
                    if self._stop.is_set():
                        break
                    if until and time.time() >= until:
                        break
                    self._pin_set(False)
                    self._sleep(1.0)
            else:
                for duration, on in steps:
                    if self._stop.is_set():
                        break
                    self._pin_set(on)
                    self._sleep(duration)
        finally:
            self._pin_set(False)
            log.debug(f"Beeper: pattern '{pattern}' finished")
