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
║ File:        signage/transcoder.py                                           ║
║ Version:     1.3.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Video transcoding service - resizes uploaded videos to display  ║
║              resolution using ffmpeg. Reduces CPU load from 40-60% to 1-2%   ║
║              and eliminates flickering on LED matrices.                      ║
║                                                                              ║
║ Important:   Creates .matrix.mp4 files alongside originals. VideoRenderer    ║
║              automatically uses transcoded version if available.             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import queue
import subprocess
import logging
import threading

log = logging.getLogger('transcoder')


def matrix_path(original_path: str) -> str:
    """Return the path for the transcoded version of a video file."""
    base, ext = os.path.splitext(original_path)
    return base + '.matrix' + (ext or '.mp4')


def is_transcoded(path: str) -> bool:
    """Return True if a transcoded version exists and is newer than original."""
    if not os.path.exists(path):
        return False
    mp = matrix_path(path)
    if not os.path.exists(mp):
        return False
    return os.path.getmtime(mp) >= os.path.getmtime(path)


def needs_transcode(path: str, display_width: int, display_height: int) -> bool:
    """
    Return True if the video should be transcoded.
    Skips transcoding if the video is already at or near display resolution.
    """
    if is_transcoded(path):
        return False
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error',
             '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height',
             '-of', 'csv=p=0', path],
            capture_output=True, text=True, timeout=10
        )
        parts = result.stdout.strip().split(',')
        if len(parts) == 2:
            w, h = int(parts[0]), int(parts[1])
            # Don't transcode if already small
            if w <= display_width * 2 and h <= display_height * 2:
                log.debug(f"Video {path} is {w}x{h} — small enough, skipping transcode")
                return False
    except Exception as e:
        log.warning(f"Could not probe {path}: {e}")
    return True


def transcode(path: str, display_width: int, display_height: int,
              on_progress=None, on_complete=None, crf: int = 18):
    """
    Transcode a video to display resolution using ffmpeg.
    Runs synchronously — call from a thread if you don't want to block.

    Args:
        path:           path to source video
        display_width:  target width
        display_height: target height
        on_progress:    optional callback(percent: int)
        on_complete:    optional callback(success: bool, out_path: str)
        crf:            libx264 CRF quality (18=high, 23=medium, 28=small file)
    """
    out = matrix_path(path)
    tmp = out + '.tmp.mp4'

    # Get source duration and fps for progress calculation and output rate selection
    duration_s = 0.0
    source_fps = 0.0
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            capture_output=True, text=True, timeout=10
        )
        duration_s = float(r.stdout.strip() or 0)
    except Exception:
        pass
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=r_frame_rate',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            capture_output=True, text=True, timeout=10
        )
        num, _, den = r.stdout.strip().partition('/')
        if num and den:
            source_fps = float(num) / float(den)
    except Exception:
        pass

    # Probe field order — only deinterlace if source is actually interlaced
    interlaced = False
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=field_order',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            capture_output=True, text=True, timeout=10
        )
        field_order = r.stdout.strip().lower()
        interlaced  = field_order not in ('progressive', 'unknown', '')
        log.info(f"Source field_order: '{field_order}' → interlaced={interlaced}")
    except Exception:
        pass

    # Choose output fps to avoid cadence judder from non-integer fps ratios:
    #   ~60fps source → 30fps (exact 2:1 drop, no blending needed)
    #   ~50fps source → 25fps (exact 2:1 drop)
    #   anything else → 25fps
    if source_fps >= 48:
        output_fps = 30
    else:
        output_fps = 25
    log.info(f"Source fps: {source_fps:.3f} → output fps: {output_fps}")

    # Build ffmpeg filter chain:
    # - yadif=0: only added for interlaced sources (skipped for progressive —
    #   running yadif on progressive content wastes significant CPU for nothing)
    # - fps filter: uniform cadence conversion to output_fps
    # - scale to fit display, pad with black to exact display size
    deinterlace = "yadif=0," if interlaced else ""
    vf = (
        f"{deinterlace}"
        f"fps=fps={output_fps},"
        f"scale={display_width}:{display_height}"
        f":force_original_aspect_ratio=decrease,"
        f"pad={display_width}:{display_height}"
        f":(ow-iw)/2:(oh-ih)/2:black"
    )
    cmd = [
        'ffmpeg', '-y',
        '-threads', '2',     # cap cores; signage daemon keeps the rest
        '-i', path,
        '-vf', vf,
        '-c:v', 'libx264',
        '-crf', str(crf),
        '-preset', 'fast',
        '-an',               # no audio
        '-movflags', '+faststart',
        '-progress', 'pipe:1',
        tmp
    ]

    log.info(f"Transcoding: {path} → {out}")
    log.info(f"Command: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=lambda: os.nice(5)
        )

        # Parse ffmpeg progress output
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if line.startswith('out_time_ms=') and duration_s > 0:
                try:
                    ms      = int(line.split('=')[1])
                    pct     = min(99, int(ms / 1000 / duration_s * 100))
                    if on_progress:
                        on_progress(pct)
                except Exception:
                    pass

        try:
            proc.wait(timeout=300)
        except subprocess.TimeoutExpired:
            log.error(f"ffmpeg timed out transcoding {path}")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            if proc.stderr:
                stderr = proc.stderr.read()
                log.error(f"ffmpeg stderr: {stderr[-500:]}")
            if os.path.exists(tmp):
                os.remove(tmp)
            if on_progress:
                on_progress(0)
            if on_complete:
                on_complete(False, '')
            return

        if proc.returncode == 0 and os.path.exists(tmp):
            os.rename(tmp, out)
            log.info(f"Transcode complete: {out} "
                     f"({os.path.getsize(out) // 1024}KB)")
            if on_progress:
                on_progress(100)
            if on_complete:
                on_complete(True, out)
        else:
            stderr = proc.stderr.read() if proc.stderr else ''
            log.error(f"ffmpeg failed (code {proc.returncode}): {stderr[-500:]}")
            if os.path.exists(tmp):
                os.remove(tmp)
            if on_complete:
                on_complete(False, '')

    except Exception as e:
        log.error(f"Transcode error: {e}")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        if on_complete:
            on_complete(False, '')


# ---------------------------------------------------------------------------
# Serialised transcode queue — one job at a time, no parallel ffmpeg
# ---------------------------------------------------------------------------
_queue:        queue.Queue       = queue.Queue()
_queued_paths: set               = set()          # paths waiting in queue
_active_path:  str | None        = None           # path currently encoding
_queue_lock:   threading.Lock    = threading.Lock()
_worker:       threading.Thread | None = None


def _worker_loop():
    global _active_path
    while True:
        job = _queue.get()
        path, w, h, on_progress, on_complete, crf = job
        with _queue_lock:
            _queued_paths.discard(path)
            _active_path = path
        try:
            transcode(path, w, h, on_progress, on_complete, crf)
        except Exception as e:
            log.error(f"Worker transcode error: {e}")
        finally:
            with _queue_lock:
                _active_path = None
        _queue.task_done()


def _ensure_worker():
    global _worker
    with _queue_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(
                target=_worker_loop,
                name='TranscodeWorker',
                daemon=True
            )
            _worker.start()


def transcode_async(path: str, display_width: int, display_height: int,
                    on_complete=None, crf: int = 18):
    """Queue a transcode job.  At most one ffmpeg runs at a time.
    Returns queue position (1 = next up, 0 = currently active).
    """
    _ensure_worker()
    with _queue_lock:
        if path == _active_path or path in _queued_paths:
            log.info(f"Transcode already queued/active: {os.path.basename(path)}")
            return 0
        _queued_paths.add(path)
        pos = len(_queued_paths)   # approximate position
    _queue.put((path, display_width, display_height, None, on_complete, crf))
    log.info(f"Queued transcode #{pos} crf={crf}: {os.path.basename(path)}")
    return pos


def transcode_queue_status(path: str) -> dict:
    """Return queue info for a given path.
    Keys: active (bool), queued (bool), position (int, 0 if not queued).
    """
    with _queue_lock:
        active = path == _active_path
        queued = path in _queued_paths
        pos    = (list(_queued_paths).index(path) + 1) if queued else 0
    return {'active': active, 'queued': queued, 'position': pos}


def resolve_video_path(path: str, item: dict = None) -> str:
    """
    Return the best version of a video to play.
    
    If a custom background is configured (non-black color, image, or corner sample),
    use the original video to allow runtime compositing with the background.
    Otherwise, use the transcoded .matrix.mp4 for optimal performance.
    
    Args:
        path: Original video file path
        item: Playlist item dict (optional, to check background settings)
    
    Returns:
        Path to the video file to use (original or transcoded)
    """
    # Check if custom background is configured
    if item:
        bg_mode = item.get('bg_mode', 'color')
        bg_color = item.get('bg_color', [0, 0, 0])
        
        # Use original if:
        # - Background mode is 'image' or 'corner' (requires runtime compositing)
        # - Background color is not black (requires custom padding color)
        if bg_mode in ('image', 'corner'):
            log.debug(f"Using original video for bg_mode={bg_mode}")
            return path
        if bg_color != [0, 0, 0]:
            log.debug(f"Using original video for custom bg_color={bg_color}")
            return path
    
    # Use transcoded version if available (black background, optimized)
    mp = matrix_path(path)
    if os.path.exists(mp):
        return mp
    return path
