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
║ File:        signage/matrix.py                                               ║
║ Version:     1.3.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Core matrix engine - manages the display loop, renderer         ║
║              lifecycle, transitions, frame caching, and alert overlays.      ║
║              Runs in dedicated daemon thread with exclusive RGBMatrix access.║
║                                                                              ║
║ Important:   Thread-safe operations via locks. Supports test mode, pause,    ║
║              skip, and brightness control. Pre-renders next static items.    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import json
import time
import queue
import logging
import threading
import numpy as np
from datetime import datetime
from PIL import Image
from signage.outputs import create_output

log = logging.getLogger('matrix')


# Types that produce a static first frame — safe to pre-render in background
STATIC_TYPES = {'image', 'gif', 'clock', 'text', 'countdown', 'weather'}

# Hardware presets — applied before per-field overrides in panel.json.
# Each preset defines the safe defaults for that board + Pi generation.
BOARD_PRESETS = {
    'electrodragon-rpi4': {
        'label':       'ElectroDragon MPC1073 (Raspberry Pi 3/4)',
        'gpio_mapping': 'regular',
        'slowdown_gpio': 4,
        'parallel_max': 2,
        'note': 'Uses BCM GPIO direct access. Not recommended on Pi 5.',
    },
    'electrodragon-rpi5': {
        'label':       'ElectroDragon MPC1073 (Raspberry Pi 5 — experimental)',
        'gpio_mapping': 'regular',
        'slowdown_gpio': 2,
        'parallel_max': 2,
        'note': 'Pi 5 RP1 GPIO — marginal support. Prefer Adafruit bonnet for Pi 5.',
    },
    'adafruit-triple-rpi4': {
        'label':       'Adafruit Triple Bonnet #6358 (Raspberry Pi 3/4)',
        'gpio_mapping': 'adafruit-hat-pwm',
        'slowdown_gpio': 4,
        'parallel_max': 3,
        'note': 'PWM-based driving. Supports up to 3 parallel chains.',
    },
    'adafruit-triple-rpi5': {
        'label':       'Adafruit Triple Bonnet #6358 (Raspberry Pi 5)',
        'gpio_mapping': 'adafruit-hat-pwm',
        'slowdown_gpio': 2,
        'parallel_max': 3,
        'note': 'Recommended board for Pi 5. Supports up to 3 parallel chains.',
    },
}


# ---------------------------------------------------------------------------
# Dedicated output thread — decouples render from blocking GPIO/UDP output
# ---------------------------------------------------------------------------

class _OutputThread(threading.Thread):
    """
    Consumes numpy RGB frames from a single-slot queue and pushes them to
    the output backend on its own thread.  For GPIO backends this uses
    FrameCanvas + SwapOnVSync so the display never tears and the render
    thread is never blocked waiting for the hardware swap.
    """

    def __init__(self, output, width: int, height: int):
        super().__init__(daemon=True, name='OutputThread')
        self._output  = output
        self._width   = width
        self._height  = height
        self._queue   = queue.Queue(maxsize=1)
        self._stop    = threading.Event()
        self.dropped  = 0
        self.frame_count = 0
        self._t_last_fps = time.perf_counter()
        self._fps_count  = 0

        # GPIO path: persistent FrameCanvas for double-buffered swap
        self._canvas = None
        self._matrix_hw = None
        if hasattr(output, 'create_canvas'):
            try:
                self._canvas    = output.create_canvas()
                self._matrix_hw = output   # exposes swap_canvas()
                log.info("OutputThread: FrameCanvas double-buffering enabled")
            except Exception as e:
                log.warning(f"OutputThread: FrameCanvas unavailable ({e}) "
                            "— falling back to SetImage")

    # ── public API (called from render thread) ─────────────────────────────

    def submit(self, frame: np.ndarray) -> None:
        """Non-blocking.  Drops the oldest pending frame if queue is full
        so the display always shows the most recent content."""
        if self._queue.full():
            try:
                self._queue.get_nowait()
                self.dropped += 1
            except queue.Empty:
                pass
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            pass   # output thread just grabbed it — that's fine

    def stop(self):
        self._stop.set()

    # ── thread body ───────────────────────────────────────────────────────

    def run(self):
        try:
            os.sched_setaffinity(0, {2})   # pin output thread to core 2
            log.info("OutputThread: started on core 2")
        except (OSError, AttributeError):
            log.info("OutputThread: started (CPU pinning not available)")
        while not self._stop.is_set():
            try:
                frame = self._queue.get(timeout=0.02)
            except queue.Empty:
                continue
            self._send(frame)

    def _send(self, frame: np.ndarray) -> None:
        # Zero-copy PIL view — frombuffer wraps the numpy memory directly.
        # The frame array stays alive (held by local ref) for the duration
        # of SetImage; no allocation, no memcpy.
        pil = Image.frombuffer(
            'RGB', (self._width, self._height),
            frame, 'raw', 'RGB', 0, 1)

        if self._canvas is not None:
            self._canvas.SetImage(pil, unsafe=True)
            self._canvas = self._matrix_hw.swap_canvas(self._canvas)
        else:
            self._output.send_frame(pil)

        self.frame_count += 1
        self._fps_count  += 1
        now = time.perf_counter()
        if now - self._t_last_fps >= 10.0:
            fps = self._fps_count / (now - self._t_last_fps)
            log.debug(f"OutputThread: {fps:.1f} fps "
                      f"(dropped={self.dropped})")
            self._fps_count  = 0
            self._t_last_fps = now


class MatrixEngine:
    def __init__(self, config_path: str, playlist):
        self.playlist       = playlist
        self._stop_event    = threading.Event()
        self._lock          = threading.Lock()
        self._current_frame = None
        self._skip_event    = threading.Event()
        self._pause_event   = threading.Event()
        self._reload_event  = threading.Event()

        self.cfg    = self._load_config(config_path)
        self.width  = self.cfg['display_width']
        self.height = self.cfg['display_height']
        self.output = create_output(self.cfg)
        self._current_frame   = np.zeros(
            (self.height, self.width, 3), dtype=np.uint8)
        self._last_frame_time = time.time()   # for watchdog
        self._test_mode       = threading.Event()  # set = screen test active
        self._alert_mgr       = None   # AlertManager instance
        self._frame_cache     = {}   # item_id → pre-rendered first frame

        # Dedicated output thread (P1.1) — decouples render from GPIO blocking
        self._out_thread = _OutputThread(self.output, self.width, self.height)
        self._out_thread.start()

        log.info(f"MatrixEngine ready: {self.width}x{self.height}")

    def _load_config(self, path):
        defaults = {
            "board_type": "electrodragon-rpi4",
            "gpio_mapping": "regular", "rows": 64, "cols": 128,
            "chain": 2, "parallel": 2, "slowdown_gpio": 4,
            "pwm_bits": 7, "pwm_lsb_nanoseconds": 50,
            "pwm_dither_bits": 1, "display_width": 256,
            "display_height": 128, "brightness": 80
        }
        if os.path.exists(path):
            with open(path) as f:
                file_cfg = json.load(f)
            # Apply board preset defaults first, then let file values override
            board_type = file_cfg.get('board_type', defaults['board_type'])
            preset = BOARD_PRESETS.get(board_type, {})
            if preset:
                defaults['gpio_mapping']  = preset['gpio_mapping']
                defaults['slowdown_gpio'] = preset['slowdown_gpio']
                log.info(f"Board preset '{board_type}': {preset['label']}")
            defaults.update(file_cfg)
            log.info(f"Panel config loaded from {path}")
        defaults['_path'] = os.path.abspath(path)
        return defaults

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------
    def stop(self):
        self._stop_event.set()
        self._skip_event.set()
        self._out_thread.stop()

    def skip(self):
        self._skip_event.set()

    def pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            log.info("Display resumed")
        else:
            self._pause_event.set()
            log.info("Display paused")

    def reload_playlist(self):
        self._reload_event.set()

    def pause_for_test(self):
        """Signal the engine to stop driving the display — screentest takes over."""
        self._test_mode.set()
        self._skip_event.set()   # interrupt any running renderer immediately

    def resume_playlist(self):
        """Resume normal playlist playback after a screen test."""
        self._test_mode.clear()
        self._skip_event.set()   # wake engine to pick next item

    def set_brightness(self, pct: int):
        pct = max(1, min(100, pct))
        self.cfg['brightness'] = pct
        self.output.set_brightness(pct)

    def get_status(self) -> dict:
        item = self.playlist.current_item()
        return {
            'paused':     self._pause_event.is_set(),
            'current':    item,
            'brightness': self.cfg['brightness'],
            'resolution': f"{self.width}x{self.height}"
        }

    def get_perf_stats(self) -> dict:
        """Return live output-thread performance counters."""
        t = self._out_thread
        return {
            'frames_output': t.frame_count,
            'frames_dropped': t.dropped,
            'canvas_mode': 'FrameCanvas+SwapOnVSync' if t._canvas is not None
                           else 'SetImage (no FrameCanvas)',
        }

    # ------------------------------------------------------------------
    # Frame output
    # ------------------------------------------------------------------
    def set_alert_manager(self, mgr):
        self._alert_mgr = mgr

    def show_frame(self, frame: np.ndarray, _from_test: bool = False):
        # While a screen test is running, only the test thread may write frames
        if self._test_mode.is_set() and not _from_test:
            return
        # Normalise to display size only when the shape is wrong (rare path)
        if frame.shape != (self.height, self.width, 3):
            img   = Image.fromarray(frame.astype(np.uint8))
            img   = img.resize((self.width, self.height), Image.LANCZOS)
            frame = np.array(img, dtype=np.uint8)
        # Keep a reference (not a copy) for wipe-out source reads.
        # All renderers produce fresh arrays per frame so this is safe.
        with self._lock:
            self._current_frame   = frame
            self._last_frame_time = time.time()
        # Apply alert overlay if active
        if self._alert_mgr is not None:
            alert_frame = self._alert_mgr.get_frame(frame, self.width, self.height)
            if alert_frame is not None:
                frame = alert_frame
        # Submit to output thread — non-blocking, render continues immediately
        self._out_thread.submit(frame)

    def black(self):
        self.show_frame(np.zeros((self.height, self.width, 3), dtype=np.uint8))

    def get_current_frame(self) -> np.ndarray:
        with self._lock:
            if self._current_frame is None:
                return np.zeros((self.height, self.width, 3), dtype=np.uint8)
            # .copy() here because callers pass this to transition src which
            # reads it while we may store a new ref; cheap 98 KB once per item.
            return self._current_frame.copy()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _item_is_active(self, item: dict) -> bool:
        now = datetime.now()
        try:
            df = item.get('date_from', '')
            if df and now < datetime.fromisoformat(df):
                return False
        except ValueError:
            pass
        try:
            dt = item.get('date_to', '')
            if dt and now > datetime.fromisoformat(dt):
                return False
        except ValueError:
            pass
        return True

    def _run_transition(self, name: str, speed: float,
                        src: np.ndarray, dst: np.ndarray) -> bool:
        """
        Run a transition from src to dst.
        Returns True if it completed normally, False if skipped/stopped.
        The LAST frame yielded by the transition is always dst — callers
        must NOT re-show dst afterwards or it flashes.
        """
        from signage.transitions import get_transition
        if not name or name == 'none':
            self.show_frame(dst)
            return True
        try:
            transition = get_transition(name, speed)
            # P1.4: stream frames directly — never materialise the full list.
            # First frame is shown within one render iteration instead of
            # waiting for the entire transition to be pre-computed.
            last_frame = None
            for frame in transition.frames(src, dst, self.width, self.height):
                if self._stop_event.is_set() or self._skip_event.is_set():
                    return False
                last_frame = frame
                self.show_frame(frame)
            # Ensure final frame is exactly dst to prevent colour drift
            if last_frame is None or not np.array_equal(last_frame, dst):
                self.show_frame(dst)
            return True
        except Exception as e:
            log.error(f"Transition '{name}' failed: {e}")
            self.show_frame(dst)
            return True

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self):
        from signage.renderer import get_renderer

        # P3.2: Pin render thread to core 1; output thread is on core 2,
        # C++ GPIO refresh thread is on core 3 (pinned in GPIOOutput.__init__)
        try:
            os.sched_setaffinity(0, {1})
            log.info("Render thread pinned to CPU core 1")
        except (OSError, AttributeError):
            pass

        log.info("Display loop starting")

        # Tracks whether the previous wipe-out already landed on the
        # first frame of the upcoming item — if so, skip the wipe-in.
        prev_wipeout_target: np.ndarray = None

        while not self._stop_event.is_set():

            # Pause handling (manual pause)
            while (self._pause_event.is_set() and not self._stop_event.is_set()
                   and not self._test_mode.is_set()):
                time.sleep(0.1)

            # Screen test mode — engine idles while test thread drives the display
            while self._test_mode.is_set() and not self._stop_event.is_set():
                time.sleep(0.1)

            item = self.playlist.advance()
            if item is None:
                log.warning("Playlist empty, showing black")
                self.black()
                time.sleep(2)
                continue

            if not self._item_is_active(item):
                log.debug(f"Skipping '{item.get('name')}' — outside date range")
                continue

            log.info(f"Playing: {item.get('type')} — {item.get('name','')}")

            # Build renderer
            try:
                renderer = get_renderer(item, self.width, self.height)
            except Exception as e:
                log.error(f"Renderer creation failed: {e}")
                time.sleep(2)
                continue

            # Get first frame
            try:
                first_frame = renderer.first_frame()
            except Exception as e:
                log.error(f"first_frame failed: {e}")
                first_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

            # ---- Wipe IN ----
            # Skip if the previous wipe-out already transitioned into
            # this content (frames match) — avoids the double-show bug.
            wipe_in       = item.get('wipe_in', 'fade')
            wipe_in_speed = float(item.get('wipe_in_speed', 1.0))

            already_shown = (
                prev_wipeout_target is not None and
                wipe_in not in ('none', None) and
                np.array_equal(prev_wipeout_target, first_frame)
            )

            if already_shown:
                log.debug("Wipe-in skipped — prev wipe-out already landed here")
                # Display is already showing first_frame, nothing to do
            else:
                outgoing = self.get_current_frame()
                self._run_transition(wipe_in, wipe_in_speed,
                                     outgoing, first_frame)

            prev_wipeout_target = None
            self._skip_event.clear()

            # ---- Render loop ----
            raw_dur    = item.get('duration', 10)
            auto_dur   = (str(raw_dur).strip().lower() == 'auto')
            duration   = None if auto_dur else float(raw_dur)
            started_at = time.time()

            try:
                for frame in renderer.frames():
                    if self._stop_event.is_set() or self._skip_event.is_set():
                        break
                    # Auto duration: advance when renderer signals done
                    # Small grace period (0.3s) ensures last content fully exits
                    if auto_dur:
                        if getattr(renderer, '_done', False):
                            if not hasattr(renderer, '_done_at'):
                                renderer._done_at = time.time()
                            elif time.time() - renderer._done_at >= 0.15:
                                break
                    else:
                        if time.time() - started_at >= duration:
                            break
                    self.show_frame(frame)
            except Exception as e:
                log.error(f"Render loop error: {e}")

            self._skip_event.clear()
            if self._stop_event.is_set():
                break

            last_frame = self.get_current_frame()

            # Pre-render next item's first frame in background (if static type)
            next_item = self.playlist.peek_next()
            if next_item and next_item.get('type') in STATIC_TYPES:
                nid = next_item.get('id')
                if nid and nid not in self._frame_cache:
                    def _prerender(ni=next_item):
                        try:
                            r = get_renderer(ni, self.width, self.height,
                                             lightweight=True)
                            f = r.first_frame()
                            r.close()
                            self._frame_cache[ni['id']] = f
                        except Exception as e:
                            log.debug(f"Pre-render failed: {e}")
                    threading.Thread(target=_prerender, daemon=True,
                                     name='PreRender').start()

            # Peek at next item — lightweight=True skips pre-buffering
            # since we only need the first frame for the wipe-out transition
            next_item = self.playlist.peek_next()
            if next_item and self._item_is_active(next_item):
                try:
                    next_renderer = get_renderer(
                        next_item, self.width, self.height,
                        lightweight=True)
                    next_first = next_renderer.first_frame()
                    next_renderer.close()
                except Exception as _peek_err:
                    log.warning(f"Peek renderer error: {_peek_err}")
                    next_first = np.zeros(
                        (self.height, self.width, 3), dtype=np.uint8)
            else:
                next_first = np.zeros(
                    (self.height, self.width, 3), dtype=np.uint8)

            # ---- Wipe OUT ----
            wipe_out       = item.get('wipe_out', 'fade')
            wipe_out_speed = float(item.get('wipe_out_speed', 1.0))

            if wipe_out and wipe_out != 'none':
                completed = self._run_transition(wipe_out, wipe_out_speed,
                                                 last_frame, next_first)
                if completed:
                    # Remember that we already landed on next_first so the
                    # next iteration can skip its wipe-in
                    prev_wipeout_target = next_first.copy()
            else:
                prev_wipeout_target = None

            renderer.close()

        log.info("Display loop stopped")
        self.black()


class _StubMatrix:
    def __init__(self, w, h):
        self.width      = w
        self.height     = h
        self.brightness = 100
    def SetImage(self, img):
        pass
