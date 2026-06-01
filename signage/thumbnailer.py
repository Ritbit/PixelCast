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
║ File:        signage/thumbnailer.py                                          ║
║ Version:     1.3.1                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Thumbnail generation service - creates 160x90 JPEG thumbnails   ║
║              for all media files. Supports images, GIF, and video.           ║
║                                                                              ║
║ Important:   Stores thumbnails in media/.thumbs/ directory. Uses PyAV for    ║
║              video, falls back to ffmpeg if needed.                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import logging
from PIL import Image

log = logging.getLogger('thumbnailer')

THUMB_DIR  = '.thumbs'
THUMB_W    = 160
THUMB_H    = 90


def thumb_dir(media_dir: str) -> str:
    return os.path.join(media_dir, THUMB_DIR)


def thumb_path(media_dir: str, filename: str) -> str:
    base = os.path.splitext(filename)[0]
    return os.path.join(thumb_dir(media_dir), base + '.jpg')


def thumb_exists(media_dir: str, filename: str) -> bool:
    tp = thumb_path(media_dir, filename)
    if not os.path.exists(tp):
        return False
    src = os.path.join(media_dir, filename)
    if not os.path.exists(src):
        return False
    return os.path.getmtime(tp) >= os.path.getmtime(src)


def _save_thumb(img: Image.Image, dest: str):
    """Resize PIL image to thumbnail dimensions and save as JPEG."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    img = img.convert('RGB')
    # Fit into THUMB_W x THUMB_H with black letterbox
    img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
    canvas = Image.new('RGB', (THUMB_W, THUMB_H), (20, 20, 20))
    x = (THUMB_W - img.width)  // 2
    y = (THUMB_H - img.height) // 2
    canvas.paste(img, (x, y))
    canvas.save(dest, 'JPEG', quality=75, optimize=True)


def generate(media_dir: str, filename: str) -> bool:
    """
    Generate a thumbnail for a media file.
    Returns True on success, False on failure.
    """
    src  = os.path.join(media_dir, filename)
    dest = thumb_path(media_dir, filename)
    ext  = os.path.splitext(filename)[1].lower()

    if not os.path.exists(src):
        return False

    try:
        if ext in ('.jpg', '.jpeg', '.png', '.bmp', '.webp'):
            img = Image.open(src)
            _save_thumb(img, dest)
            return True

        elif ext == '.gif':
            img = Image.open(src)
            img.seek(0)
            _save_thumb(img.convert('RGB'), dest)
            return True

        elif ext in ('.mp4', '.webm', '.avi', '.mkv', '.mov'):
            return _video_thumb(src, dest)

    except Exception as e:
        log.error(f"Thumbnail generation failed for {filename}: {e}")

    return False


THUMB_OFFSET_S = 5.0   # seconds into video to grab thumbnail


def _video_thumb(src: str, dest: str) -> bool:
    """
    Extract a frame from THUMB_OFFSET_S seconds into the video.

    Uses ffmpeg subprocess — NOT PyAV. PyAV holds the Python GIL during
    H264 decode which starves the matrix engine thread and causes display
    freezes. ffmpeg as a subprocess has zero GIL interaction.
    """
    import subprocess
    tmp = dest + '.tmp.jpg'

    # First try with seek offset (-ss before -i = fast keyframe seek)
    for seek_args in (['-ss', str(THUMB_OFFSET_S)], []):
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
            result = subprocess.run(
                ['ffmpeg', '-y'] + seek_args + [
                    '-i', src, '-vframes', '1', '-q:v', '3', tmp
                ],
                capture_output=True, timeout=30,
                preexec_fn=lambda: os.nice(5)
            )
            if result.returncode == 0 and os.path.exists(tmp):
                img = Image.open(tmp).convert('RGB')
                _save_thumb(img, dest)
                os.remove(tmp)
                return True
        except subprocess.TimeoutExpired:
            log.warning(f"ffmpeg thumbnail timed out: {src}")
        except Exception as e:
            log.error(f"ffmpeg thumbnail error: {e}")
        finally:
            if os.path.exists(tmp):
                try: os.remove(tmp)
                except Exception: pass

    return False


def generate_all_missing(media_dir: str):
    """
    Generate thumbnails for all media files that don't have one yet.
    Called on startup to catch files uploaded before thumbnailing existed.
    """
    if not os.path.isdir(media_dir):
        return
    valid_exts = {'.jpg','.jpeg','.png','.bmp','.webp',
                  '.gif','.mp4','.webm','.avi','.mkv','.mov'}
    count = 0
    for fn in sorted(os.listdir(media_dir)):
        if '.matrix.' in fn or fn.startswith('.'):
            continue
        if os.path.splitext(fn)[1].lower() not in valid_exts:
            continue
        if not thumb_exists(media_dir, fn):
            if generate(media_dir, fn):
                count += 1
    if count:
        log.info(f"Generated {count} missing thumbnail(s)")
