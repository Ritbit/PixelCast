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
║ File:        signage/timecode.py                                             ║
║ Version:     1.3.1                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Timecode parsing utility - converts various timecode formats    ║
║              to seconds. Supports: frames, ss.ff, mm:ss, hh:mm:ss, etc.      ║
║                                                                              ║
║ Important:   Returns float seconds. FPS parameter needed for frame-based     ║
║              formats (default 25fps).                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import re


def parse_timecode(s: str, fps: float = 25.0) -> float:
    """
    Parse a timecode string and return total seconds as float.
    Raises ValueError on invalid input.
    """
    s = str(s).strip()
    if not s or s == '0':
        return 0.0

    # Pure number — treat as seconds
    if re.fullmatch(r'\d+', s):
        return float(s)

    # Pure float with no colon — could be seconds.frames or just seconds
    if re.fullmatch(r'\d+\.\d+', s):
        parts     = s.split('.')
        secs      = int(parts[0])
        frames    = int(parts[1])
        return secs + frames / fps

    # Has colons
    if ':' in s:
        # Split off optional .frames suffix
        frames_part = 0
        if '.' in s:
            s, dot_part = s.rsplit('.', 1)
            frames_part = int(dot_part)

        parts = s.split(':')
        parts = [int(p) for p in parts]

        if len(parts) == 2:
            minutes, seconds = parts
            hours = 0
        elif len(parts) == 3:
            hours, minutes, seconds = parts
        else:
            raise ValueError(f"Too many colon-separated parts: {s!r}")

        total = hours * 3600 + minutes * 60 + seconds + frames_part / fps
        return total

    raise ValueError(f"Cannot parse timecode: {s!r}")


def seconds_to_timecode(seconds: float, fps: float = 25.0) -> str:
    """
    Convert a float seconds value back to hh:mm:ss.ff display string.
    Only includes hours if >= 1 hour.
    """
    fps_rounded  = round(fps)
    total_frames = round(seconds * fps)
    frames       = total_frames % fps_rounded
    total_secs   = total_frames // fps_rounded
    secs         = total_secs % 60
    total_mins   = total_secs // 60
    mins         = total_mins % 60
    hours        = total_mins // 60

    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}.{frames:02d}"
    elif mins > 0:
        return f"{mins}:{secs:02d}.{frames:02d}"
    else:
        return f"{secs}.{frames:02d}"


if __name__ == '__main__':
    # Quick self-test
    tests = [
        ('0',        0.0),
        ('42',       42.0),
        ('3.20',     3 + 20/25),
        ('1:45',     105.0),
        ('1:45.12',  105 + 12/25),
        ('1:02:30',  3750.0),
        ('1:02:30.05', 3750 + 5/25),
    ]
    for inp, expected in tests:
        result = parse_timecode(inp)
        ok     = abs(result - expected) < 0.001
        print(f"{'OK' if ok else 'FAIL'} parse_timecode({inp!r}) = {result:.4f} (expected {expected:.4f})")

    print()
    for secs in [0, 3.8, 105, 105.48, 3750.2]:
        print(f"seconds_to_timecode({secs}) = {seconds_to_timecode(secs)}")
