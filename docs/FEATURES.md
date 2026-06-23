# PixelCast — Implemented Features Reference

**Last Updated**: June 2026 | Version: 1.3.1

This document describes all implemented features in the current codebase.

---

## Hardware

Tested and supported configuration:

| Item             | Value                                                              |
|------------------|--------------------------------------------------------------------|
| Controller       | Raspberry Pi 4B                                                    |
| HAT              | ElectroDragon MPC1073 HUB75                                        |
| Panels           | 4× P2.5 128×64 HUB75E, arranged 2×2                                |
| Total resolution | **256×128 pixels**                                                 |
| GPIO mapping     | `regular` (never `adafruit-hat`)                                   |
| OS               | Raspberry Pi OS Lite 64-bit, Bookworm/Debian 13                    |
| Python           | 3.13                                                               |
| Display driver   | hzeller/rpi-rgb-led-matrix at `/opt/PixelCast/rpi-rgb-led-matrix/` |

**Confirmed working panel flags:**

```text
--led-gpio-mapping=regular --led-rows=64 --led-cols=128
--led-chain=2 --led-parallel=2 --led-slowdown-gpio=4
--led-pwm-bits=7 --led-pwm-lsb-nanoseconds=50 --led-pwm-dither-bits=0
```

---

## Key source files

| File                             | Purpose                                                            |
|----------------------------------|--------------------------------------------------------------------|
| `daemon.py`                      | Entry point — starts engine, web, scheduler, watchdog              |
| `signage/matrix.py`              | `MatrixEngine` — display loop, transitions, frame cache            |
| `signage/playlist.py`            | Thread-safe playlist CRUD and navigation                           |
| `signage/scheduler.py`           | Time-based on/off/dim rules                                        |
| `signage/alert.py`               | High-priority overlay alert system                                 |
| `signage/watchdog.py`            | Engine health monitor, auto-restarts on freeze                     |
| `signage/beeper.py`              | Active buzzer support via configurable GPIO pin                    |
| `signage/screentest.py`          | Hardware test patterns (colour, grid, gradient)                    |
| `signage/sysinfo.py`             | CPU/memory/temperature/disk via `/proc`                            |
| `signage/overlay.py`             | Persistent clock/text/ticker layer over content                    |
| `signage/outputs.py`             | `GPIOOutput` (HUB75) and `UDPOutput` backends                      |
| `signage/renderer/`              | One file per content type (see Content Types below)                |
| `signage/transitions/effects.py` | 22 transition effects                                              |
| `signage/web/routes.py`          | All Flask blueprints and routes                                    |
| `signage/web/filters.py`         | Jinja2 filters: `basename`, `rgb_hex`, `timecode`, `fmt_duration`  |

---

## Project structure

```text
/opt/PixelCast/led-signage/
├── daemon.py                    # Entry point
├── requirements.txt
├── deployment/
│   ├── install.sh               # Full installer
│   ├── systemd/PixelCast.service
│   └── nginx/pixelcast.conf
└── signage/
    ├── matrix.py                # MatrixEngine — sole owner of RGBMatrix
    ├── playlist.py              # PlaylistManager (thread-safe RLock)
    ├── scheduler.py             # Time-based on/off/dim
    ├── alert.py                 # High-priority overlay alert
    ├── watchdog.py              # Engine health + auto-restart
    ├── beeper.py                # Active buzzer via GPIO
    ├── screentest.py            # Hardware test patterns
    ├── sysinfo.py               # CPU/mem/temp/disk (via /proc)
    ├── overlay.py               # Persistent content overlay
    ├── outputs.py               # GPIOOutput (HUB75) + UDPOutput
    ├── transcoder.py            # ffmpeg video optimisation
    ├── thumbnailer.py           # Thumbnail generation
    ├── timecode.py              # Timecode parser
    ├── renderer/
    │   ├── base.py              # BaseRenderer ABC
    │   ├── image.py             # Static images
    │   ├── gif.py               # Animated GIF
    │   ├── video.py             # Video (PyAV), loop modes, prebuffer
    │   ├── clock.py             # Digital clock + date line
    │   ├── text.py              # Multi-line, scroll, inline §-codes
    │   ├── weather.py           # Open-Meteo live weather
    │   ├── countdown.py         # Countdown/countup timer
    │   └── utils.py             # Shared rendering helpers
    ├── transitions/
    │   └── effects.py           # 22 effects
    └── web/
        ├── app.py               # Flask factory
        ├── auth.py              # Flask-Login, RBAC (viewer/editor/admin)
        ├── api.py               # REST API blueprint (/api/v1/)
        ├── filters.py           # Jinja2: basename, rgb_hex, timecode, fmt_duration
        ├── routes.py            # All UI blueprints + control routes
        └── templates/           # HTML templates (base, index, playlist, …)
```

---

## Architecture rules — read carefully, never violate

**Threading:**
- `MatrixEngine` runs in one daemon thread and is the **sole** caller of
  `matrix.SetImage()` and `matrix.brightness`. Nothing else may touch
  the RGBMatrix object.
- Flask runs in a separate daemon thread. Never call matrix methods directly
  from a route — use the public API on `MatrixEngine` (skip, pause,
  set_brightness, etc.).
- `Scheduler` runs in a third daemon thread, also uses only the public API.

**Frame format:**
- All frames are `numpy (H, W, 3) uint8 RGB` arrays.
- `engine.show_frame(arr)` is the only way to push a frame to the display.
- `engine.get_current_frame()` returns a thread-safe copy of the last frame.

**Renderer contract:**
- `first_frame()` → single numpy array (used by transition engine as dst)
- `frames()` → generator yielding numpy arrays indefinitely
- `close()` → release resources
- Renderers must NOT sleep for longer than one frame period inside `frames()`

**Transition contract:**
- `get_transition(name, duration_seconds)` returns a transition instance
- `.frames(src, dst, w, h)` → generator of intermediate numpy frames
- The LAST frame yielded must be exactly `dst` — no colour drift allowed
- The engine sets `prev_wipeout_target = dst.copy()` after a wipe-out so
  the next iteration can skip its wipe-in (avoids double-show artifact)

**Playlist item colors:** always `[R, G, B]` lists, never hex strings
**File paths:** always absolute in playlist.json
**Flask:** `debug=False, use_reloader=False` always — reloader breaks threading

---

## Critical Jinja2 constraints

These Python builtins are NOT available in Jinja2 templates:
- `tuple()` → use `| rgb_hex` filter instead for color conversion
- `enumerate()` → use `loop.index0` instead
- `range()` → use `{% for i in range(n) %}` only works if passed from route

Custom filters (registered in `filters.py`, available in all templates):
- `{{ color_list | rgb_hex }}` → `'#rrggbb'` string for `<input type=color>`
- `{{ path | basename }}` → filename only
- `{{ offset | timecode }}` → display-friendly timecode string

Template block structure (must match exactly):
```jinja
{% extends 'base.html' %}
{% block title %}Page Title{% endblock %}
{% block head %}...optional CSS...{% endblock %}
{% block content %}
  ...page content...
{% endblock %}
{% block scripts %}
  ...optional JS...
{% endblock %}
```
Always verify block open/close counts match before saving a template.

---

## Implemented features

### Content types

- **Image** — JPG, PNG, BMP, WebP; fit/fill/stretch/crop scaling; background modes
- **GIF** — Animated GIF with configurable loop count
- **Video** — MP4/AVI/MOV via PyAV; auto-transcoded; start offset; loop modes; optional RAM prebuffer; auto-duration
- **Text** — Multi-line; per-line font/size/color/scroll; inline §-codes; pixel-font mode
- **Clock** — Digital clock with date line; customisable format, font, color
- **Weather** — Open-Meteo (no API key); current + multi-day forecast; WMO icons; wttr.in fallback
- **Countdown** — Countdown/countup to a target datetime

### Transitions (22 effects)

`fade` `fade_black` `wipe_left/right/up/down` `slide_left/right/up/down`
`zoom_in/out` `dissolve` `melt` `snow` `spiral` `drop`
`blinds_h/v` `checkerboard` `pixelate` `none` `random`

Per-item wipe-in and wipe-out with configurable speed.

### Playlist

- Drag-and-drop reorder, duplicate, per-item date-range filtering
- Import/export JSON; auto-save on every change
- Go-to item by number from the dashboard
- Fixed and auto-duration (renderer signals done via `_done` flag)

### Web interface

- **Dashboard** — MJPEG preview, playback controls (play/pause/skip/prev/goto), brightness, formatted duration display, system stats
- **Playlist editor** — full CRUD, per-item config UI
- **File manager** — drag-and-drop upload, thumbnails, delete with cascade
- **Schedule editor** — time-based on/off/dim rules with day-of-week selection
- **Settings** — hardware config, user management, beeper test, screen test, system controls
- **Alerts** — POST from UI or API with custom styling and priority

### REST API (`/api/v1/`)

Bearer-token auth. Key endpoints: `GET /status`, `GET /playlist`,
`POST /playlist/item`, `PUT/DELETE /playlist/item/<id>`, `POST /playlist/skip`,
`GET/PUT /brightness`, `GET /snapshot`, `POST /alert`, `DELETE /alert`.

### Authentication & RBAC

Three roles: `viewer` (read-only), `editor` (content + files + alerts + brightness),
`admin` (full access including users, hardware settings, reboot).

### System

- **Overlay** — persistent clock/text/ticker layer on top of all content
- **Beeper** — active buzzer on configurable GPIO pin with test UI
- **Scheduler** — time-based on/off/dim with day-of-week rules
- **Watchdog** — restarts service if engine freezes beyond configurable timeout
- **Screen test** — colour bars, grid, gradient test patterns
- **USB storage** — auto-mount at `/media/usb`; config/media can live on USB
- **Overlay filesystem** — read-only SD card; `deploy.sh` writes through to SD card
- **Boot blanking** — GPIO 18/17/4 driven by Pi firmware before kernel; panels dark during boot
- **RT kernel** — PREEMPT_RT; render→core 1, output→core 2, C++ GPIO refresh→core 3

### Jinja2 template filters

| Filter         | Usage                         | Output                    |
|----------------|-------------------------------|---------------------------|
| `basename`     | `{{ path \| basename }}`      | filename only             |
| `rgb_hex`      | `{{ color_list \| rgb_hex }}` | `#rrggbb`                 |
| `timecode`     | `{{ seconds \| timecode }}`   | `mm:ss`                   |
| `fmt_duration` | `{{ secs \| fmt_duration }}`  | `Xs` / `M:SS` / `H:MM:SS` |
