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
║ PixelCast - Professional LED Matrix Signage System                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/renderer/video.py                                       ║
║ Version:     1.3.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Video renderer using PyAV - supports MP4, AVI, MOV with        ║
║              multiple scaling modes, loop modes (restart/pingpong), start    ║
║              offset, and background options. Auto-uses transcoded versions.  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import time
import threading
import logging
import numpy as np
from PIL import Image
from .base import BaseRenderer
from .utils import load_background, fit_image, paste_at
from signage.timecode import parse_timecode

log = logging.getLogger('renderer.video')


class VideoRenderer(BaseRenderer):

    def __init__(self, item: dict, width: int, height: int,
                 lightweight: bool = False):
        super().__init__(item, width, height)
        from signage.transcoder import resolve_video_path as _rvp
        self._path         = _rvp(item.get('file', ''), item)
        self._scale_mode   = item.get('scale_mode', item.get('scale', 'fit'))
        self._scale_factor = float(item.get('scale_factor', 1.0))
        self._position     = item.get('position', 'center')
        self._loop         = item.get('loop', True)
        self._loop_mode    = item.get('loop_mode', 'restart')
        self._loop_count   = int(item.get('loop_count', 0))   # 0 = infinite
        self._fps_override = float(item.get('fps_override', 0) or 0)
        self._lightweight  = lightweight
        self._want_prebuf  = item.get('prebuffer', False) and not lightweight
        self._item         = item   # keep for bg loading

        raw_offset = item.get('start_offset', 0)
        try:
            self._start_offset = parse_timecode(str(raw_offset))
        except Exception:
            self._start_offset = 0.0

        self._first         = None
        self._container     = None
        self._video_fps     = 25.0
        self._done          = False   # set True when video ends (for auto duration)
        self._prebuffered   = None
        self._prebuf_ready  = threading.Event()
        self._prebuf_thread = None
        self._prebuf_stop   = threading.Event()
        self._bg_cache      = None   # cached background PIL image

        self._open()
        # Pre-build background canvas once; also cache as numpy for fast copy
        self._bg_cache = load_background(width, height, item)
        # Pre-computed numpy bg array — avoids PIL Image.copy() per frame
        self._bg_np    = np.array(self._bg_cache, dtype=np.uint8)
        if self._want_prebuf and self._container is not None:
            self._prebuf_thread = threading.Thread(
                target=self._do_prebuffer, daemon=True,
                name='VideoPreBuffer')
            self._prebuf_thread.start()

    def _open(self):
        try:
            import av
            self._container = av.open(self._path)
            stream = self._container.streams.video[0]
            # Set thread_type BEFORE any decoding/seeking — it cannot be
            # changed after the codec is opened
            stream.thread_type = 'AUTO'
            detected        = float(stream.average_rate or 25.0)
            self._video_fps = self._fps_override or detected
            log.info(f"Video opened: {self._path} @ {self._video_fps:.3f}fps")
        except Exception as e:
            log.error(f"Failed to open video '{self._path}': {e}")
            self._container = None

    def _seek_to_offset(self, container):
        if self._start_offset <= 0:
            return
        try:
            container.seek(int(self._start_offset * 1_000_000))
        except Exception as e:
            log.warning(f"Seek failed: {e}")

    def _pil_to_array(self, pil_img: Image.Image) -> np.ndarray:
        """Convert a decoded video frame PIL image to display-sized numpy array.
        Background is cached — only the video frame is resized per-frame.
        """
        # For corner sampling: resolve bg on first real frame, then cache
        if self._bg_cache is None or \
                (self._item.get('bg_mode') == 'corner' and self._first is None):
            self._bg_cache = load_background(
                self.width, self.height, self._item, pil_img)
            self._bg_np = np.array(self._bg_cache, dtype=np.uint8)

        # Resize the video frame (BILINEAR — adequate quality for LED panels)
        sized = fit_image(pil_img, self.width, self.height,
                          self._scale_mode, self._scale_factor,
                          fast=True)
        sized_np = np.asarray(sized, dtype=np.uint8)  # view, no copy if already uint8

        # P3: Start from numpy bg copy instead of PIL Image allocation
        canvas = self._bg_np.copy()

        # Compute paste position (mirrors paste_at logic, pure numpy)
        iw, ih = sized.size
        cw, ch = self.width, self.height
        x = 0 if 'left' in self._position else \
            cw - iw if 'right' in self._position else (cw - iw) // 2
        y = 0 if 'top'  in self._position else \
            ch - ih if 'bottom' in self._position else (ch - ih) // 2
        # Clamp to canvas bounds
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(cw, x + iw), min(ch, y + ih)
        sx, sy = x0 - x, y0 - y
        if x1 > x0 and y1 > y0:
            canvas[y0:y1, x0:x1] = sized_np[sy:sy+(y1-y0), sx:sx+(x1-x0)]

        return canvas

    def _do_prebuffer(self):
        import av
        frames = []
        try:
            tmp = av.open(self._path)
            self._seek_to_offset(tmp)
            for packet in tmp.demux(video=0):
                if self._prebuf_stop.is_set():
                    break
                for frame in packet.decode():
                    if self._prebuf_stop.is_set():
                        break
                    pil_img = frame.to_image()
                    frames.append(self._pil_to_array(pil_img))
            tmp.close()
        except Exception as e:
            log.error(f"Pre-buffer failed: {e}")
            self._prebuf_ready.set()
            return
        mb = len(frames) * self.width * self.height * 3 / 1_048_576
        log.info(f"Pre-buffered {len(frames)} frames ({mb:.1f}MB)")
        if mb > 200:
            log.warning(f"Pre-buffer uses {mb:.0f}MB")
        self._prebuffered = frames
        if frames and self._first is None:
            self._first = frames[0].copy()
        self._prebuf_ready.set()

    def first_frame(self) -> np.ndarray:
        if self._first is not None:
            return self._first.copy()
        if self._container is None:
            return self._black()
        try:
            import av
            tmp    = av.open(self._path)
            self._seek_to_offset(tmp)
            stream = tmp.streams.video[0]
            stream.thread_type = 'AUTO'
            for packet in tmp.demux(stream):
                for frame in packet.decode():
                    self._first = self._pil_to_array(
                        frame.to_image().convert('RGB'))
                    tmp.close()
                    return self._first.copy()
            tmp.close()
        except Exception as e:
            log.error(f"first_frame failed: {e}")
        return self._black()

    def frames(self):
        if self._container is None and self._prebuffered is None:
            while True:
                yield self._black()
                time.sleep(0.01)
            return
        if self._want_prebuf:
            if self._prebuf_ready.is_set() and self._prebuffered:
                yield from self._play_buffer(self._prebuffered)
            else:
                yield from self._stream_with_handoff()
        else:
            yield from self._stream_from_disk()

    def _stream_with_handoff(self):
        for frame in self._single_pass():
            yield frame
        if not self._loop:
            while True: yield self._first or self._black()
            return
        while True:
            if self._prebuf_ready.is_set() and self._prebuffered:
                yield from self._play_buffer(self._prebuffered)
                if not self._loop: return
            else:
                for frame in self._single_pass():
                    yield frame

    def _single_pass(self):
        try:
            self._container.seek(0)
            self._seek_to_offset(self._container)
            stream = self._container.streams.video[0]
            # thread_type already set in _open() before codec was opened
            period   = 1.0 / self._video_fps
            deadline = time.perf_counter() + period
            collected = []
            for packet in self._container.demux(stream):
                for av_frame in packet.decode():
                    arr = self._pil_to_array(av_frame.to_image().convert('RGB'))
                    sleep_t = deadline - time.perf_counter()
                    if sleep_t > 0: time.sleep(sleep_t)
                    deadline += period
                    yield arr
                    if self._loop_mode == 'pingpong':
                        collected.append(arr)
            if self._loop_mode == 'pingpong' and collected:
                deadline = time.perf_counter() + period
                for arr in reversed(collected):
                    sleep_t = deadline - time.perf_counter()
                    if sleep_t > 0: time.sleep(sleep_t)
                    deadline += period
                    yield arr
        except Exception as e:
            log.error(f"Stream error: {e}")
            yield self._black()

    def _stream_from_disk(self):
        plays = 0
        while True:
            for frame in self._single_pass(): yield frame
            plays += 1
            self._done = True   # signal one complete play for auto-duration
            if not self._loop:
                while True: yield self._first or self._black()
                return
            if self._loop_count > 0 and plays >= self._loop_count:
                # Held on last frame indefinitely after loop limit
                while True: yield self._first or self._black()
                return

    def _play_buffer(self, buf):
        period = 1.0 / self._video_fps
        plays  = 0
        while True:
            indices = list(range(len(buf)))
            if self._loop_mode == 'pingpong':
                indices += list(range(len(buf) - 2, 0, -1))
            deadline = time.perf_counter() + period
            for i in indices:
                sleep_t = deadline - time.perf_counter()
                if sleep_t > 0: time.sleep(sleep_t)
                deadline += period
                yield buf[i]
            plays += 1
            self._done = True   # signal one complete play for auto-duration
            if not self._loop:
                while True: yield buf[-1]
                return
            if self._loop_count > 0 and plays >= self._loop_count:
                while True: yield buf[-1]
                return

    def close(self):
        # Signal prebuffer thread to stop
        if self._prebuf_thread and self._prebuf_thread.is_alive():
            self._prebuf_stop.set()
            self._prebuf_thread.join(timeout=2.0)
            self._prebuf_thread = None
        
        if self._container:
            try: self._container.close()
            except Exception: pass
            self._container = None
        self._prebuffered = None
        self._prebuf_stop.clear()
