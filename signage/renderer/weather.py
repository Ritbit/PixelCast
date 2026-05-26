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
║ File:        signage/renderer/weather.py                                     ║
║ Version:     1.1.0                                                           ║
║ Author:      Bas                                                             ║
║ Description: Weather display renderer using Open-Meteo API (free, no key).   ║
║              Shows current conditions and multi-day forecast with WMO icons. ║
║              Supports built-in geometric icons or custom PNG icons.          ║
║                                                                              ║
║ Important:   15-minute refresh interval. Custom icons: place WMO-numbered    ║
║              PNGs (0.png, 61.png, etc.) in media/weather-icons/.             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import time, threading, logging, os, json
import numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from .base import BaseRenderer
from .utils import load_background, parse_color

log = logging.getLogger('renderer.weather')

FONT_SEARCH = [
    '/opt/PixelCast/led-signage/fonts/',
    '/usr/share/fonts/truetype/freefont/',
    '/usr/share/fonts/truetype/dejavu/',
]

# WMO weather interpretation codes → (label, icon_key)
WMO = {
    0:  ('Clear',      'sunny'),
    1:  ('Mostly Clear','sunny'),
    2:  ('Partly Cloudy','partly_cloudy'),
    3:  ('Overcast',   'cloudy'),
    45: ('Fog',        'fog'),
    48: ('Icy Fog',    'fog'),
    51: ('Drizzle',    'drizzle'),
    53: ('Drizzle',    'drizzle'),
    55: ('Drizzle',    'drizzle'),
    61: ('Rain',       'rain'),
    63: ('Rain',       'rain'),
    65: ('Heavy Rain', 'heavy_rain'),
    71: ('Snow',       'snow'),
    73: ('Snow',       'snow'),
    75: ('Heavy Snow', 'snow'),
    80: ('Showers',    'rain'),
    81: ('Showers',    'rain'),
    82: ('Heavy Showers','heavy_rain'),
    85: ('Snow Showers','snow'),
    86: ('Snow Showers','snow'),
    95: ('Thunderstorm','thunder'),
    96: ('Thunderstorm','thunder'),
    99: ('Thunderstorm','thunder'),
}

DAY_NAMES = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']


def _find_font(name, size):
    for d in FONT_SEARCH:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
        p2 = p + '.ttf'
        if os.path.exists(p2):
            return ImageFont.truetype(p2, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Smooth, rounded weather icons drawn with Pillow
# ---------------------------------------------------------------------------

import math as _math

def _draw_icon(key: str, size: int = 40) -> Image.Image:
    """Return a smooth RGBA icon of the given weather type."""
    img  = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s    = size
    m    = max(1, s // 40)   # line/stroke scale factor

    if key == 'sunny':
        _draw_sun(draw, s//2, s//2, s//3, s, m, bright=True)

    elif key == 'partly_cloudy':
        # Smaller sun offset to top-right
        _draw_sun(draw, s*58//100, s*38//100, s//5, s, m, bright=True, rays=True)
        _draw_smooth_cloud(draw, s*42//100, s*66//100, s*54//100, s*36//100,
                           (230, 235, 245, 248))

    elif key == 'cloudy':
        _draw_smooth_cloud(draw, s//2, s//2, s*72//100, s*46//100,
                           (190, 200, 215, 250))

    elif key == 'fog':
        _draw_smooth_cloud(draw, s//2, s*38//100, s*70//100, s*40//100,
                           (190, 200, 215, 220))
        for i in range(3):
            y = s*58//100 + i * s//8
            w = s*65//100 - i * s//10
            x = (s - w) // 2
            alpha = 200 - i * 40
            draw.rounded_rectangle([x, y, x+w, y + max(2, m*2)],
                                   radius=m, fill=(170, 180, 200, alpha))

    elif key == 'drizzle':
        _draw_smooth_cloud(draw, s//2, s*36//100, s*66//100, s*38//100,
                           (160, 175, 195, 240))
        for i in range(3):
            x = s*(22 + i*22)//100
            _draw_raindrop(draw, x, s*62//100, s//14, m, (130, 175, 255, 200))

    elif key == 'rain':
        _draw_smooth_cloud(draw, s//2, s*32//100, s*68//100, s*40//100,
                           (130, 145, 165, 245))
        for i in range(4):
            x = s*(16 + i*20)//100
            _draw_raindrop(draw, x, s*60//100, s//12, m, (90, 150, 255, 230))

    elif key == 'heavy_rain':
        _draw_smooth_cloud(draw, s//2, s*28//100, s*70//100, s*38//100,
                           (100, 110, 130, 250))
        for i in range(5):
            x = s*(12 + i*17)//100
            _draw_raindrop(draw, x, s*57//100, s//10, m+1, (70, 130, 255, 240))

    elif key == 'snow':
        _draw_smooth_cloud(draw, s//2, s*34//100, s*66//100, s*38//100,
                           (200, 210, 225, 240))
        for i in range(4):
            x = s*(18 + i*20)//100
            y = s*62//100 + (i%2) * s//12
            _draw_snowflake(draw, x, y, s//14, m)

    elif key == 'thunder':
        _draw_smooth_cloud(draw, s//2, s*28//100, s*70//100, s*38//100,
                           (85, 90, 110, 250))
        _draw_lightning(draw, s//2, s*56//100, s//4, m)

    return img


def _draw_sun(draw, cx, cy, r, s, m, bright=True, rays=True):
    # Soft outer glow
    glow_r = int(r * 1.5)
    for gr in range(glow_r, r-1, -1):
        alpha = int(80 * (1 - (gr - r) / (glow_r - r + 1)))
        c = (255, 230, 80, alpha)
        draw.ellipse([cx-gr, cy-gr, cx+gr, cy+gr], fill=c)
    # Main disc
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(255, 225, 60, 255))
    # Highlight
    hr = max(2, r//3)
    draw.ellipse([cx-r+hr//2, cy-r+hr//2, cx-r+hr//2+hr, cy-r+hr//2+hr],
                 fill=(255, 248, 180, 120))
    if not rays:
        return
    # Rounded rays
    n_rays = 8
    for i in range(n_rays):
        ang   = _math.radians(i * 360 / n_rays)
        r1    = r + max(2, m+1)
        r2    = r + max(5, m*4)
        x1    = cx + _math.cos(ang) * r1
        y1    = cy + _math.sin(ang) * r1
        x2    = cx + _math.cos(ang) * r2
        y2    = cy + _math.sin(ang) * r2
        draw.line([x1, y1, x2, y2], fill=(255, 215, 40, 220),
                  width=max(2, m*2))


def _draw_smooth_cloud(draw, cx, cy, w, h, color):
    """Draw a smooth multi-bubble cloud shape."""
    r  = h // 2
    # Three overlapping circles + rectangle body
    draw.ellipse([cx - w//2,   cy - r,  cx,         cy + r], fill=color)
    draw.ellipse([cx - w//4,   cy-r-r//2, cx+w//4,  cy+r//2], fill=color)
    draw.ellipse([cx,          cy - r,  cx + w//2,  cy + r], fill=color)
    draw.rectangle([cx - w//2, cy - r//2, cx + w//2, cy + r], fill=color)
    # Soft top highlight
    hi = tuple(min(255, c+40) for c in color[:3]) + (80,)
    draw.ellipse([cx - w//4 + 2, cy-r-r//2 + 2,
                  cx + w//4 - 2, cy - r//4], fill=hi)


def _draw_raindrop(draw, x, y, r, m, color):
    """Draw a teardrop-shaped raindrop."""
    # Oval body
    draw.ellipse([x-r, y, x+r, y + r*2], fill=color)
    # Pointed top (triangle)
    pts = [(x, y - r), (x-r, y+r//2), (x+r, y+r//2)]
    draw.polygon(pts, fill=color)


def _draw_snowflake(draw, x, y, r, m):
    color = (200, 225, 255, 230)
    # Six arms
    for i in range(6):
        ang = _math.radians(i * 60)
        x2  = x + _math.cos(ang) * r
        y2  = y + _math.sin(ang) * r
        draw.line([x, y, x2, y2], fill=color, width=max(1, m))
    # Centre dot
    draw.ellipse([x-m, y-m, x+m, y+m], fill=(220, 240, 255, 255))


def _draw_lightning(draw, x, y, h, m):
    """Draw a sharp lightning bolt."""
    w = h // 2
    pts = [
        (x,      y),
        (x-w//2, y + h//2),
        (x,      y + h//2),
        (x-w//2, y + h),
        (x+w//3, y + h//2 - h//6),
        (x-w//6, y + h//2 - h//6),
    ]
    draw.polygon(pts, fill=(255, 235, 0, 255))
    # White core highlight
    pts2 = [
        (x-1,    y + 2),
        (x-w//3, y + h//2),
        (x,      y + h//2),
        (x-w//3+2, y + h - 4),
    ]
    draw.polygon(pts2, fill=(255, 255, 200, 160))


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

_CACHE_DIR = '/opt/PixelCast/cache'


def _cache_path(lat, lon, units):
    return os.path.join(_CACHE_DIR, f'weather_{lat}_{lon}_{units}.json')


def _load_cache(lat, lon, units):
    try:
        p = _cache_path(lat, lon, units)
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _save_cache(lat, lon, units, data):
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(_cache_path(lat, lon, units), 'w') as f:
            json.dump(data, f)
    except Exception:
        pass


# wttr.in weather codes → WMO codes
_WTTR_TO_WMO = {
    113: 0,  116: 2,  119: 3,  122: 3,
    143: 45, 248: 45, 260: 48,
    176: 80, 179: 85, 182: 80, 185: 51,
    200: 95,
    227: 71, 230: 75,
    263: 51, 266: 51, 281: 51, 284: 51,
    293: 61, 296: 61, 299: 63, 302: 63, 305: 65, 308: 65,
    311: 61, 314: 63, 317: 80, 320: 80,
    323: 71, 326: 71, 329: 73, 332: 73, 335: 75, 338: 75,
    350: 51, 353: 80, 356: 82, 359: 82,
    362: 85, 365: 86, 368: 85, 371: 86, 374: 85, 377: 86,
    386: 95, 389: 95, 392: 95, 395: 99,
}


def _fetch_openmeteo(lat, lon, days, units):
    import urllib.request
    temp_unit = 'celsius' if units == 'celsius' else 'fahrenheit'
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,"
        f"weather_code,wind_speed_10m"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min"
        f"&temperature_unit={temp_unit}"
        f"&wind_speed_unit=kmh"
        f"&forecast_days={days}"
        f"&timezone=auto"
    )
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def _fetch_wttr(lat, lon, days, units):
    """Fallback: wttr.in — normalised to Open-Meteo response format."""
    import urllib.request
    url = f"https://wttr.in/{lat},{lon}?format=j1"
    with urllib.request.urlopen(url, timeout=10) as r:
        raw = json.loads(r.read())

    use_c   = (units == 'celsius')
    cur_raw = raw['current_condition'][0]
    wmo_cur = _WTTR_TO_WMO.get(int(cur_raw['weatherCode']), 3)

    forecasts  = raw.get('weather', [])[:days]
    max_key    = 'maxtempC'  if use_c else 'maxtempF'
    min_key    = 'mintempC'  if use_c else 'mintempF'

    def _day_wmo(day):
        # weatherCode is NOT at the day level — use the midday hourly slot (index 4)
        hourly = day.get('hourly', [])
        slot   = hourly[4] if len(hourly) > 4 else (hourly[0] if hourly else {})
        return _WTTR_TO_WMO.get(int(slot.get('weatherCode', 0)), 3)

    return {
        'current': {
            'temperature_2m':        float(cur_raw['temp_C' if use_c else 'temp_F']),
            'relative_humidity_2m':  float(cur_raw['humidity']),
            'weather_code':          wmo_cur,
            'wind_speed_10m':        float(cur_raw['windspeedKmph']),
        },
        'daily': {
            'weather_code':        [_day_wmo(d) for d in forecasts],
            'temperature_2m_max':  [float(d[max_key]) for d in forecasts],
            'temperature_2m_min':  [float(d[min_key]) for d in forecasts],
            'time':                [d['date']          for d in forecasts],
        },
    }


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class WeatherRenderer(BaseRenderer):

    def __init__(self, item: dict, width: int, height: int,
                 lightweight: bool = False):
        super().__init__(item, width, height)
        self._item     = item
        self._lat      = float(item.get('latitude',  52.37))
        self._lon      = float(item.get('longitude', 4.89))
        self._name     = item.get('location_name', '')
        self._units    = item.get('units', 'celsius')
        self._days     = max(1, min(5, int(item.get('forecast_days', 3))))
        # interval set in __init__
        self._icon_dir = item.get('icon_dir',
                         '/opt/PixelCast/led-signage/media/weather-icons')

        self._data       = _load_cache(self._lat, self._lon, self._units)
        self._stale      = self._data is not None
        self._frame      = None
        self._bg_cache   = load_background(width, height, item)
        self._lock       = threading.Lock()
        self._last_fetch = 0
        self._err_count  = 0
        self._lightweight = lightweight
        # 15 minute refresh interval (override item config)
        self._interval   = 900

        # Fonts — configurable via item, with sensible larger defaults
        font_name = item.get('font', 'FreeSansBold.ttf')
        font_name_reg = item.get('font_regular', 'FreeSans.ttf')
        # Default sizes scale with display height; item can override each
        sz_big = int(item.get('font_size_big', max(18, height // 6)))
        sz_med = int(item.get('font_size_med', max(14, height // 9)))
        sz_sm  = int(item.get('font_size_sm',  max(11, height // 12)))
        self._font_big  = _find_font(font_name,     sz_big)
        self._font_med  = _find_font(font_name_reg, sz_med)
        self._font_sm   = _find_font(font_name_reg, sz_sm)

        # Skip network fetch when only peeking for transition frame
        if not lightweight:
            threading.Thread(target=self._refresh, daemon=True).start()

    def _refresh(self):
        errors = {}
        for fetcher in (_fetch_openmeteo, _fetch_wttr):
            name = fetcher.__name__
            try:
                data = fetcher(self._lat, self._lon, self._days, self._units)
                with self._lock:
                    self._data  = data
                    self._stale = False
                    self._err_count = 0
                    self._last_fetch = time.time()
                    self._frame = None   # invalidate cached frame
                _save_cache(self._lat, self._lon, self._units, data)
                log.info(f"Weather data fetched via {name}")
                return
            except Exception as e:
                errors[name] = e
                log.debug(f"Weather source {name} failed: {e}")
        # Both sources failed
        with self._lock:
            self._err_count += 1
            cnt = self._err_count
        if cnt == 1 or cnt % 10 == 0:
            details = '; '.join(f"{s}: {e}" for s, e in errors.items())
            log.warning(f"All weather sources failed (attempt {cnt}): {details}")

    def _get_icon(self, code: int, size: int) -> Image.Image:
        _, icon_key = WMO.get(code, ('Unknown', 'cloudy'))
        size = max(4, size)

        # Try WMO-numbered PNG in icon_dir (e.g. 0.png, 61.png)
        # Named files use _named_ prefix (e.g. _named_sunny.png)
        for fname in [f"{code}.png", f"_named_{icon_key}.png", f"{icon_key}.png"]:
            path = os.path.join(self._icon_dir, fname)
            if os.path.exists(path):
                try:
                    icon = Image.open(path).convert('RGBA')
                    if icon.width != size or icon.height != size:
                        icon = icon.resize((size, size), Image.LANCZOS)
                    log.debug(f"Icon loaded: {path} @ {size}px")
                    return icon
                except Exception as e:
                    log.warning(f"Icon load failed {path}: {e}")
            else:
                log.debug(f"Icon not found: {path}")

        # Fall back to built-in drawn icon
        log.warning(f"Using drawn fallback for code={code} key={icon_key} "
                    f"icon_dir={self._icon_dir}")
        return _draw_icon(icon_key, size)

    def _text_w(self, text, font):
        try:
            bb = font.getbbox(text)
            return bb[2] - bb[0]
        except AttributeError:
            return font.getsize(text)[0]

    def _render(self) -> np.ndarray:
        canvas = self._bg_cache.copy()

        with self._lock:
            data = self._data

        if data is None:
            # No data at all (no cache, no live fetch) — show error message
            draw = ImageDraw.Draw(canvas)
            lines = ['No weather data', 'API unavailable']
            y = max(4, (self.height - len(lines) * (self._font_sm.size + 2)) // 2)
            for line in lines:
                tw = self._text_w(line, self._font_sm)
                draw.text(((self.width - tw) // 2, y), line,
                          font=self._font_sm, fill=(200, 80, 80))
                y += self._font_sm.size + 2
            return np.array(canvas, dtype=np.uint8)

        with self._lock:
            stale = self._stale

        draw    = ImageDraw.Draw(canvas)
        if stale:
            # Faint indicator that this is cached/offline data
            draw.text((2, 2), '⚠', font=self._font_sm, fill=(180, 120, 40))
        cur     = data.get('current', {})
        daily   = data.get('daily', {})
        temp    = cur.get('temperature_2m', '?')
        code    = cur.get('weather_code', 0)
        hum     = cur.get('relative_humidity_2m', None)
        wind    = cur.get('wind_speed_10m', None)
        label, _ = WMO.get(code, ('?', 'cloudy'))
        sym     = '°C' if self._units == 'celsius' else '°F'

        if self._days == 1:
            # Full-screen current conditions
            icon_size = min(self.height - 20, self.width // 3)
            icon      = self._get_icon(code, icon_size)
            ix        = (self.width // 3 - icon_size) // 2
            iy        = (self.height - icon_size) // 2
            canvas.paste(icon, (ix, iy), icon)

            tx = self.width // 3 + 4
            ty = 4
            if self._name:
                draw.text((tx, ty), self._name,
                          font=self._font_sm, fill=(180, 180, 255))
                ty += self._font_sm.size + 2
            t_str = f"{temp}{sym}"
            draw.text((tx, ty), t_str, font=self._font_big,
                      fill=(255, 220, 100))
            ty += self._font_big.size + 2
            draw.text((tx, ty), label, font=self._font_med,
                      fill=(200, 200, 200))
            ty += self._font_med.size + 4
            if hum is not None and self._item.get('show_humidity', True):
                draw.text((tx, ty), f"💧{hum}%",
                          font=self._font_sm, fill=(100, 180, 255))
                ty += self._font_sm.size + 2
            if wind is not None and self._item.get('show_wind', True):
                draw.text((tx, ty), f"💨{wind}km/h",
                          font=self._font_sm, fill=(180, 220, 180))

        else:
            # Top strip: current conditions
            top_h    = self.height // 2
            icon_size = top_h - 8
            icon      = self._get_icon(code, icon_size)
            canvas.paste(icon, (4, 4), icon)

            tx = icon_size + 10
            if self._name:
                draw.text((tx, 4), self._name,
                          font=self._font_sm, fill=(180, 180, 255))
            draw.text((tx, 4 + (self._font_sm.size if self._name else 0)),
                      f"{temp}{sym}  {label}",
                      font=self._font_med, fill=(255, 220, 100))

            # Divider
            draw.line([(0, top_h), (self.width, top_h)],
                      fill=(60, 60, 80), width=1)

            # Forecast strip
            codes = daily.get('weather_code', [])
            t_max = daily.get('temperature_2m_max', [])
            t_min = daily.get('temperature_2m_min', [])
            times = daily.get('time', [])

            n_days     = min(self._days, len(codes))
            col_w      = self.width // max(1, n_days)
            # Compute icon size from actual bottom-half height
            row_h      = self.height - top_h
            label_h    = self._font_sm.size + 1
            temp_h     = self._font_sm.size + 1
            icon_h     = max(8, row_h - label_h - temp_h - 4)

            for i in range(n_days):
                x     = i * col_w + col_w // 2
                y     = top_h + 2
                d_code = codes[i] if i < len(codes) else 0
                d_max  = t_max[i] if i < len(t_max) else '?'
                d_min  = t_min[i] if i < len(t_min) else '?'
                d_time = times[i] if i < len(times) else ''

                # Day name
                try:
                    dt    = datetime.strptime(d_time, '%Y-%m-%d')
                    dname = DAY_NAMES[dt.weekday()]
                except Exception:
                    dname = '?'

                dw = self._text_w(dname, self._font_sm)
                draw.text((x - dw//2, y), dname,
                          font=self._font_sm, fill=(160, 160, 200))
                y += label_h

                icon = self._get_icon(d_code, icon_h)
                canvas.paste(icon, (x - icon.width//2, y), icon)
                y += icon.height + 2

                temp_str = f"{int(d_max)}°"
                tw = self._text_w(temp_str, self._font_sm)
                draw.text((x - tw//2, y), temp_str,
                          font=self._font_sm, fill=(255, 200, 80))

        return np.array(canvas, dtype=np.uint8)

    def first_frame(self) -> np.ndarray:
        # Check under lock, render outside to avoid deadlock with _lock in _render()
        with self._lock:
            frame = self._frame
        if frame is None:
            frame = self._render()
            with self._lock:
                if self._frame is None:
                    self._frame = frame
                else:
                    frame = self._frame
        return frame.copy()

    def frames(self):
        """
        Yield frames at ~1fps — content only changes once a minute
        but we must yield frequently so the watchdog stays happy.
        The rendered frame is cached and only rebuilt every 60 seconds.
        """
        frame_period  = 1.0   # seconds between yields
        redraw_every  = 60    # seconds between full re-renders
        last_render   = 0.0

        while True:
            now = time.time()

            # Kick off a data refresh in background if due (atomic check-and-set)
            with self._lock:
                needs_refresh = now - self._last_fetch > self._interval
                if needs_refresh:
                    self._last_fetch = now
            if needs_refresh:
                threading.Thread(target=self._refresh,
                                 daemon=True).start()

            # Re-render frame once per minute (or on first call)
            # NOTE: _render() acquires _lock internally to read self._data,
            # so we must NOT hold _lock here — that would deadlock.
            if now - last_render >= redraw_every or self._frame is None:
                self._frame = self._render()
                last_render = now

            f = self._frame.copy()

            yield f
            time.sleep(frame_period)
