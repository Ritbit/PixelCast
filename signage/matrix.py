"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/matrix.py                                               ║
║ Version:     1.0.0                                                           ║
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
import logging
import threading
import numpy as np
from datetime import datetime
from PIL import Image

log = logging.getLogger('matrix')

# Types that produce a static first frame — safe to pre-render in background
STATIC_TYPES = {'image', 'gif', 'clock', 'text', 'countdown', 'weather'}

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    REAL_MATRIX = True
except ImportError:
    log.warning("rgbmatrix not found - running in STUB mode")
    REAL_MATRIX = False


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
        self.matrix = self._init_matrix()
        self._current_frame = np.zeros(
            (self.height, self.width, 3), dtype=np.uint8)
        self._last_frame_time = time.time()   # for watchdog
        self._test_mode       = threading.Event()  # set = screen test active
        self._alert_mgr      = None   # AlertManager instance
        self._frame_cache     = {}   # item_id → pre-rendered first frame
        log.info(f"MatrixEngine ready: {self.width}x{self.height}")

    def _load_config(self, path):
        defaults = {
            "gpio_mapping": "regular", "rows": 64, "cols": 128,
            "chain": 2, "parallel": 2, "slowdown_gpio": 4,
            "pwm_bits": 7, "pwm_lsb_nanoseconds": 50,
            "pwm_dither_bits": 1, "display_width": 256,
            "display_height": 128, "brightness": 80
        }
        if os.path.exists(path):
            with open(path) as f:
                defaults.update(json.load(f))
            log.info(f"Panel config loaded from {path}")
        return defaults

    def _init_matrix(self):
        if not REAL_MATRIX:
            return _StubMatrix(self.width, self.height)
        options = RGBMatrixOptions()
        options.hardware_mapping         = self.cfg['gpio_mapping']
        options.rows                     = self.cfg['rows']
        options.cols                     = self.cfg['cols']
        options.chain_length             = self.cfg['chain']
        options.parallel                 = self.cfg['parallel']
        options.gpio_slowdown            = self.cfg['slowdown_gpio']
        options.pwm_bits                 = self.cfg['pwm_bits']
        options.pwm_lsb_nanoseconds      = self.cfg['pwm_lsb_nanoseconds']
        options.pwm_dither_bits          = self.cfg['pwm_dither_bits']
        options.brightness               = self.cfg['brightness']
        options.disable_hardware_pulsing = self.cfg.get('disable_hardware_pulsing', False)
        options.show_refresh_rate        = self.cfg.get('show_refresh_rate', False)
        options.drop_privileges          = False

        limit = self.cfg.get('limit_refresh', 0)
        if limit > 0:
            options.limit_refresh_rate_hz = limit
            log.info(f"Panel refresh rate limited to {limit}Hz")

        scan_mode = self.cfg.get('scan_mode', 0)
        if scan_mode:
            options.scan_mode = scan_mode

        row_addr = self.cfg.get('row_addr_type', 0)
        if row_addr:
            options.row_address_type = row_addr

        mux = self.cfg.get('multiplexing', 0)
        if mux:
            options.multiplexing = mux

        rgb_seq = self.cfg.get('rgb_sequence', 'RGB')
        if rgb_seq and rgb_seq != 'RGB':
            options.led_rgb_sequence = rgb_seq

        panel_type = self.cfg.get('panel_type', '')
        if panel_type:
            options.panel_type = panel_type

        pixel_mapper = self.cfg.get('pixel_mapper', '')
        if pixel_mapper:
            options.pixel_mapper_config = pixel_mapper
        m = RGBMatrix(options=options)
        log.info("RGBMatrix hardware initialised")
        return m

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------
    def stop(self):
        self._stop_event.set()
        self._skip_event.set()

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
        if REAL_MATRIX:
            self.matrix.brightness = pct

    def get_status(self) -> dict:
        item = self.playlist.current_item()
        return {
            'paused':     self._pause_event.is_set(),
            'current':    item,
            'brightness': self.cfg['brightness'],
            'resolution': f"{self.width}x{self.height}"
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
        if frame.shape != (self.height, self.width, 3):
            img   = Image.fromarray(frame.astype(np.uint8))
            img   = img.resize((self.width, self.height), Image.LANCZOS)
            frame = np.array(img)
        with self._lock:
            self._current_frame  = frame.copy()
            self._last_frame_time = time.time()
        # Apply alert overlay if active
        if self._alert_mgr is not None:
            alert_frame = self._alert_mgr.get_frame(frame, self.width, self.height)
            if alert_frame is not None:
                frame = alert_frame
        if REAL_MATRIX:
            self.matrix.SetImage(
                Image.fromarray(frame.astype(np.uint8), 'RGB'))

    def black(self):
        self.show_frame(np.zeros((self.height, self.width, 3), dtype=np.uint8))

    def get_current_frame(self) -> np.ndarray:
        with self._lock:
            if self._current_frame is None:
                return np.zeros((self.height, self.width, 3), dtype=np.uint8)
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
            frames     = list(transition.frames(src, dst, self.width, self.height))
            # Ensure last frame is exactly dst to avoid colour drift
            if len(frames) > 0:
                frames[-1] = dst.copy()
            for frame in frames:
                if self._stop_event.is_set() or self._skip_event.is_set():
                    return False
                self.show_frame(frame)
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
