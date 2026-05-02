# LED Matrix Signage System — Windsurf Development Prompt

## Your role

You are continuing development of a working Raspberry Pi LED matrix signage
system. The codebase is at `/opt/PixelCast/led-signage/` on the target Pi, but you
should read the actual files before making changes — do not assume file
contents from this document alone, as the document describes the state at the
end of the previous session and minor drifts may have occurred.

Read this entire document first, then read the key source files listed in
"Files to read before starting", then begin implementing the requested
features one at a time, testing each before moving to the next.

---

## Hardware (do not change these assumptions)

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

**Working panel flags** (always use these unless explicitly changing them):
```
--led-gpio-mapping=regular --led-rows=64 --led-cols=128
--led-chain=2 --led-parallel=2 --led-slowdown-gpio=4
--led-pwm-bits=7 --led-pwm-lsb-nanoseconds=50 --led-pwm-dither-bits=1
```

---

## Files to read before starting

Read these files in order before writing any code:

1. `/opt/PixelCast/led-signage/signage/matrix.py` — display loop, transition logic,
   `prev_wipeout_target` anti-double-show mechanism
2. `/opt/PixelCast/led-signage/signage/renderer/base.py` — BaseRenderer ABC
3. `/opt/PixelCast/led-signage/signage/renderer/video.py` — current video renderer
4. `/opt/PixelCast/led-signage/signage/web/routes.py` — all Flask routes
5. `/opt/PixelCast/led-signage/signage/web/templates/base.html` — nav, CSS design system
6. `/opt/PixelCast/led-signage/signage/web/filters.py` — custom Jinja2 filters
7. `/opt/PixelCast/led-signage/config/panel.json` — current hardware config

---

## Project structure

```
/opt/PixelCast/led-signage/
├── daemon.py                    # Entry: starts MatrixEngine + Scheduler + Flask
├── install.sh
├── led-signage.service          # Systemd unit
├── nginx-led-signage.conf
├── requirements.txt
├── config/
│   ├── panel.json               # Hardware config (hzeller params)
│   ├── playlist.json            # Playlist (auto-saved)
│   ├── schedule.json            # On/off/dim schedule
│   └── users.json               # SHA256-hashed credentials
├── media/                       # Uploaded media
├── fonts/                       # Custom TTF fonts
└── signage/
    ├── matrix.py                # MatrixEngine — sole owner of RGBMatrix
    ├── playlist.py              # PlaylistManager (thread-safe)
    ├── scheduler.py             # Time-based on/off/dim
    ├── timecode.py              # Timecode parser (ss, ss.ff, mm:ss, hh:mm:ss.ff)
    ├── renderer/
    │   ├── __init__.py          # get_renderer() factory
    │   ├── base.py              # BaseRenderer ABC
    │   ├── image.py             # Static images + corner bg sampling
    │   ├── gif.py               # Animated GIF
    │   ├── video.py             # Video via PyAV, start_offset, loop modes
    │   ├── clock.py             # Digital clock + date
    │   └── text.py              # Multi-line, per-line font/color, scroll,
    │                            #   inline §Crrggbb; §Fname; §Snn; §R codes
    ├── transitions/
    │   ├── __init__.py          # get_transition(name, duration_seconds)
    │   └── effects.py           # 20 effects (fade, wipe_*, slide_*, zoom_*,
    │                            #   dissolve, melt, snow, spiral, drop,
    │                            #   blinds_h/v, checkerboard, pixelate)
    └── web/
        ├── app.py               # Flask factory + error handlers
        ├── auth.py              # Flask-Login, users.json
        ├── filters.py           # Jinja2: basename, rgb_hex, timecode
        ├── routes.py            # Blueprints: main, playlist, files,
        │                        #   control, schedule
        └── templates/
            ├── base.html        # Nav + CSS design tokens
            ├── login.html
            ├── index.html       # Dashboard: MJPEG preview, controls
            ├── playlist.html    # Playlist CRUD + import/export
            ├── edit_item.html   # Per-item editor
            ├── files.html       # Media manager
            ├── schedule.html    # Time schedule
            ├── settings.html    # Panel config + system controls
            └── error.html       # Custom error pages
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

## Known bugs to fix first

### 1. Video flickering (priority — fix before new features)

**Cause:** Two separate issues:
- `time.sleep()` drift accumulates causing irregular frame delivery
- Panel internal refresh rate is not a clean multiple of video FPS, causing
  partial-refresh tearing (like monitor screen-tear without V-sync)

**Fix A — limit_refresh (quick win):**
`panel.json` already has a `limit_refresh` field (default 0 = no limit).
In `matrix.py` `_init_matrix()`, pass it to `RGBMatrixOptions`:
```python
options.limit_refresh_rate_hz = self.cfg.get('limit_refresh', 0)
```
The Settings page already saves this field — it just isn't being applied.
Expose it clearly in Settings with advice: set to a multiple of video FPS
(e.g. 50 for 25fps video, 60 for 30fps video, 0 for auto).

**Fix B — pre-buffer mode for video renderer:**
Add `"prebuffer": true` option to video playlist items.
When enabled, decode all frames into a list in RAM during `__init__`,
then `frames()` loops over the list with `time.perf_counter()` based
pacing (more accurate than sleep). Show a warning in the UI if the
buffered video would exceed 200MB RAM.

RAM estimate: `frames × width × height × 3 bytes`
For a 30s / 25fps / 256×128 video: `750 × 256 × 128 × 3 = 73.7 MB` — fine.

---

## Features to implement

Implement these in order. Complete and test each before starting the next.
For each feature, update the web UI, the relevant backend module, and
add appropriate routes. Keep changes minimal and focused.

---

### Feature 1: Overlay system

A persistent rendering layer drawn on top of all playlist content.
Configured globally (not per-playlist-item), stored in `config/overlay.json`.

**Overlay types:**
- `clock` — small digital clock in a corner (HH:MM or HH:MM:SS)
- `text` — static text string in a corner
- `ticker` — scrolling text across the bottom or top edge

**Config schema** (`config/overlay.json`):
```json
{
  "enabled": false,
  "items": [
    {
      "type": "clock",
      "position": "top-right",
      "format": "%H:%M",
      "color": [255, 255, 0],
      "font": "FreeSans.ttf",
      "font_size": 10,
      "bg_color": null,
      "bg_alpha": 0,
      "apply_to": "all"
    },
    {
      "type": "ticker",
      "position": "bottom",
      "text": "Welcome to our display",
      "color": [255, 255, 255],
      "font_size": 10,
      "speed": 1,
      "apply_to": "all"
    }
  ]
}
```

`apply_to`: `"all"` or a list of playlist item IDs.
`position`: `"top-left"`, `"top-right"`, `"bottom-left"`, `"bottom-right"`,
            `"bottom"` (full width ticker), `"top"` (full width ticker).
`bg_color`: null = transparent, or `[R,G,B]` for a background box.

**Implementation:**
- Add `OverlayRenderer` class in `signage/overlay.py`
- It holds its own state (ticker scroll position, clock update timing)
- `MatrixEngine` calls `overlay.render(frame)` after getting the frame
  from the content renderer, before calling `show_frame()`. The overlay
  draws on top by compositing into the numpy array.
- `OverlayRenderer.render(frame)` modifies the frame in-place and returns it
- Add `/overlay/` route (GET/POST) for configuration UI
- Add Overlay link to nav in `base.html`

---

### Feature 2: Weather widget renderer

New playlist item type: `weather`.

**Data source:** Open-Meteo API — free, no API key, no account needed.
Endpoint: `https://api.open-meteo.com/v1/forecast`

**Config schema:**
```json
{
  "type": "weather",
  "name": "Weather",
  "duration": 20,
  "latitude": 52.44,
  "longitude": 4.82,
  "location_name": "Zaandam",
  "units": "celsius",
  "forecast_days": 1,
  "bg_color": [0, 0, 30],
  "bg_image": "/opt/PixelCast/led-signage/media/weather-bg.jpg",
  "text_color": [255, 255, 255],
  "accent_color": [100, 180, 255],
  "update_interval": 600
}
```

**Layout (256×128):**
```
┌──────────────────────────────────┐
│ Zaandam          14°C    ☁ Cloudy│  ← current conditions, top row
│                                  │
│  Mon  Tue  Wed                   │  ← forecast strip (if days > 1)
│  12°  15°  11°                   │
│  ☀    ⛅    🌧                    │
└──────────────────────────────────┘
```

**Weather icons:** render as emoji using a font that supports them, OR
draw simple geometric icons (sun = yellow circle + rays, cloud = white
ellipses, rain = blue lines). Geometric is more reliable on LED panels.

**Implementation:**
- `signage/renderer/weather.py` — fetches data on init and every
  `update_interval` seconds in a background thread
- Renders to numpy frame using Pillow
- Gracefully shows "No data" if fetch fails
- Cache last good data so a failed refresh doesn't blank the display
- Add to `get_renderer()` factory in `renderer/__init__.py`
- Add `weather` to `VALID_TYPES` in `playlist.py`
- Add weather item UI to `playlist.html` add form and `edit_item.html`

---

### Feature 3: Gamma / colour correction

LED panels have a non-linear response that makes images from a monitor look
washed out or over-saturated on the physical display.

**Implementation:**
- Add gamma LUT to `MatrixEngine`
- In `show_frame()`, apply LUT before `SetImage()`:
  ```python
  # Build LUT once: lut[i] = int((i/255)^gamma * 255)
  # Apply: frame = self._gamma_lut[frame]  # numpy advanced indexing
  ```
- Config in `panel.json`:
  ```json
  "gamma": 2.2,
  "gamma_r": 1.0,
  "gamma_g": 1.0,
  "gamma_b": 1.0
  ```
  `gamma` is a global multiplier. Per-channel overrides allow white balance
  correction (e.g. if your panels look too green, set `gamma_g: 1.1`).
- Rebuild LUT whenever gamma settings change (not on every frame)
- Add sliders to Settings page: global gamma (0.5–3.0, default 2.2) and
  per-channel R/G/B trim (0.5–2.0, default 1.0). Apply immediately without
  restart.

---

### Feature 4: LED-optimised text rendering

Anti-aliased text at small sizes (≤16px) on LED panels looks blurry because
sub-pixel colour bleed is clearly visible at 2.5mm pixel pitch.

**Implementation:**
- In `renderer/text.py` and `renderer/clock.py`, detect when font size ≤ 16
- For small sizes, render text at 1× with `ImageFont` but use
  `draw.text(..., stroke_width=0)` and convert the image to `'1'` (1-bit)
  mode first, then back to `'RGB'` — this forces hard pixel boundaries
- For sizes > 16, keep current anti-aliased rendering (it looks fine at
  larger sizes on the panels)
- Add `"pixel_font": true` option per text line to force this mode
  regardless of size

---

### Feature 5: Ken Burns effect on images

Makes static image pages dynamic by slowly panning and zooming.

**Implementation:**
- Add `"ken_burns": true` option to image playlist items
- Optional: `"ken_burns_zoom_start": 1.0`, `"ken_burns_zoom_end": 1.3`,
  `"ken_burns_direction": "random|left|right|up|down"`
- In `ImageRenderer`, if ken_burns is enabled:
  - Load image at 2× display resolution for zoom headroom
  - `frames()` generator computes a crop rectangle that slowly moves
    and scales across the item's duration
  - Use `item.get('duration', 10)` to calculate total frames at ~25fps
  - Interpolate zoom and pan position using eased lerp

---

### Feature 6: Countdown timer renderer

New playlist item type: `countdown`.

**Config schema:**
```json
{
  "type": "countdown",
  "name": "Until Christmas",
  "duration": 15,
  "target_date": "2026-12-25T00:00:00",
  "label": "Until Christmas",
  "finished_text": "🎄 Merry Christmas!",
  "bg_color": [0, 0, 20],
  "bg_image": "/opt/PixelCast/led-signage/media/xmas-bg.jpg",
  "number_color": [255, 220, 0],
  "label_color": [200, 200, 255],
  "show_seconds": false
}
```

**Layout:**
```
┌─────────────────────────────────┐
│         Until Christmas         │
│                                 │
│      47 days  3 hours           │
│                                 │
└─────────────────────────────────┘
```

---

### Feature 7: Startup sequence

A designated playlist item (or short playlist) that plays **once** on daemon
start before the normal loop begins.

**Implementation:**
- Add `"startup": true` flag to any playlist item
- In `PlaylistManager`, `startup_items()` returns items with this flag
- In `MatrixEngine.run()`, before the main loop, play startup items once
  (no looping, no wipe-out to next item — just play and move on)
- In `edit_item.html`, add a "Play on startup" checkbox
- In `playlist.html`, mark startup items with a distinctive badge

---

### Feature 8: Watchdog

Detects a frozen or crashed MatrixEngine and restarts the daemon.

**Implementation:**
- `MatrixEngine` updates `self._last_frame_time = time.time()` in `show_frame()`
- Add `signage/watchdog.py`:
  ```python
  class Watchdog:
      def __init__(self, engine, timeout=30):
          ...
      def run(self):
          while not self._stop.is_set():
              age = time.time() - engine._last_frame_time
              if age > self.timeout:
                  log.error(f"Engine appears frozen ({age:.0f}s). Restarting.")
                  subprocess.Popen(['systemctl', 'restart', 'led-signage'])
                  return
              self._stop.wait(10)
  ```
- Start watchdog thread in `daemon.py`
- Watchdog is disabled while display is paused (check `engine._pause_event`)
- Config: `"watchdog_timeout": 30` in `panel.json`

---

### Feature 9: Health check endpoint

**Route:** `GET /health` (no auth required — for external monitoring)

**Response:**
```json
{
  "status": "ok",
  "uptime_seconds": 3642,
  "current_item": "Clock",
  "current_type": "clock",
  "brightness": 80,
  "paused": false,
  "last_frame_age_seconds": 0.04,
  "playlist_length": 5,
  "version": "1.0.0"
}
```

Status is `"ok"`, `"paused"`, or `"error"` (if last_frame_age > 10s).
Add to `control_bp` in `routes.py`. No `@login_required` on this route.

---

### Feature 10: REST API

A JSON API for external control. All endpoints require an API key passed
as `Authorization: Bearer <key>` header OR as `?api_key=<key>` query param.

API key stored in `config/users.json` as `"api_key": "..."`. Generate a
random key on first boot if not present. Show it in Settings.

**Endpoints (all under `/api/v1/`):**

```
GET    /api/v1/status              → same as /health but auth required
GET    /api/v1/playlist            → full playlist JSON
POST   /api/v1/playlist/skip       → skip to next item
POST   /api/v1/playlist/pause      → pause/unpause
POST   /api/v1/playlist/goto/<id>  → jump to specific item by id
PUT    /api/v1/brightness          → body: {"value": 80}
POST   /api/v1/overlay/text        → body: {"text": "...", "duration": 10}
                                     temporarily override overlay text
```

Document the API in Settings page with copy-paste examples for curl,
Home Assistant REST sensor, and Node-RED HTTP node.

---

### Feature 11: Log viewer

**Route:** `GET /logs` — requires login

**Implementation:**
- Read last N lines from systemd journal using:
  ```python
  subprocess.run(['journalctl', '-u', 'led-signage', '-n', '200',
                  '--no-pager', '--output=short-iso'],
                 capture_output=True, text=True)
  ```
- Auto-refresh every 5 seconds via JavaScript fetch to
  `GET /logs/data?lines=200` which returns JSON `{"lines": [...]}`
- Colour-code lines: ERROR=red, WARNING=yellow, INFO=default
- Add Logs link to nav

---

### Feature 12: Config backup and restore

**Routes:**
- `GET /settings/backup` — download zip of `config/` + `media/`
- `POST /settings/restore` — upload zip, extract, restart daemon

**Implementation:**
```python
# Backup
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in Path('config').rglob('*'):
        zf.write(f)
    for f in Path('media').rglob('*'):
        zf.write(f)
```

Add Backup and Restore buttons to the Settings page below the system
controls. Restore warns that it will restart the daemon.

---

### Feature 13: Media thumbnails

Auto-generate 80×40px thumbnails when files are uploaded.

**Implementation:**
- After saving an uploaded file, call `generate_thumbnail(path)`
- Store thumbnails in `media/.thumbs/filename.jpg`
- `generate_thumbnail()`:
  - Images: Pillow resize
  - GIFs: first frame via Pillow
  - Videos: first frame via PyAV (same as `VideoRenderer.first_frame()`)
- In `files.html`, show thumbnails in the file grid (already has
  `<img>` placeholder logic — wire it up to `/files/thumb/<filename>`)
- In `playlist.html`, show small thumbnail next to each media item
- Route: `GET /files/thumb/<filename>` — serves from `.thumbs/` or generates on demand

---

### Feature 14: Playlist templates

Save and restore named playlist snapshots.

**Storage:** `config/playlist_templates/` — one JSON file per template.

**Routes:**
- `GET /playlist/templates` — list available templates
- `POST /playlist/templates/save` — body: `{"name": "Weekday"}` — saves current playlist
- `POST /playlist/templates/load/<name>` — replaces current playlist
- `DELETE /playlist/templates/delete/<name>`

**UI:** Add a "Templates" panel to `playlist.html` with save/load/delete.

---

### Feature 15: Multi-user support

Add `viewer` and `editor` roles alongside the existing `admin` role.

| Role | Dashboard | Playlist | Files | Settings | Schedule |
|---|---|---|---|---|---|
| viewer | read | read | read | no | no |
| editor | full | full | full | brightness only | read |
| admin | full | full | full | full | full |

**Implementation:**
- Add `role` field to each user in `users.json`
- Add `require_role(role)` decorator in `auth.py`
- Apply to relevant routes: settings panel save requires admin, etc.
- Add user management UI to Settings (admin only): add/remove users,
  change roles, reset passwords

---

### Feature 16: Mobile-friendly UI

**Changes to `base.html`:**
- Add responsive breakpoints for screens < 768px
- Replace top nav with bottom navigation bar on mobile (fixed position,
  5 icons: Dashboard, Playlist, Files, Schedule, Settings)
- Make cards full-width on mobile (remove grid layouts)
- Increase touch target sizes to minimum 44px height for all buttons
- Make the MJPEG preview fill the screen width on mobile

**CSS approach:** use CSS custom properties already in the design system,
add `@media (max-width: 768px)` blocks. No new framework needed.

---

## Implementation notes for all features

### Checklist for each feature

Before marking a feature complete:
- [ ] Python files parse cleanly: `python3 -m py_compile file.py`
- [ ] Template blocks are balanced (count `{% block %}` vs `{% endblock %}`)
- [ ] New routes are registered in the correct blueprint in `routes.py`
  AND the blueprint is registered in `app.py`
- [ ] New config fields have sensible defaults (never crash on missing key)
- [ ] Thread safety: any shared state accessed from multiple threads uses
  a lock or is `threading.Event`/`threading.atomic`
- [ ] New renderer types added to `get_renderer()` factory AND `VALID_TYPES`
  in `playlist.py`
- [ ] New nav items added to `base.html` nav

### Error handling philosophy
- Renderers must never crash the engine thread — wrap `frames()` body in
  try/except, yield a black frame on error, log the error
- Routes must return useful error messages, not bare 500s
- Missing config keys → use `.get(key, default)` everywhere

### Colour handling
- Colors in Python code: tuples `(R, G, B)`
- Colors in JSON/playlist: lists `[R, G, B]`
- Colors in HTML forms: `#rrggbb` hex strings, converted via `rgb_hex` filter
- Convert hex form input back to list in route:
  ```python
  hc = form_value.lstrip('#')
  color = [int(hc[i:i+2], 16) for i in (0, 2, 4)]
  ```

### Deployment
After all changes:
```bash
sudo systemctl restart led-signage
journalctl -u led-signage -f   # watch for errors
```

The web UI is at `http://<Pi-IP>:5000` (or port 80 if nginx is configured).
Default login: admin / admin (should already be changed on this install).

---

## Suggested implementation order

1. **Video flicker fix** — quick win, high impact, existing infrastructure
2. **Gamma correction** — immediate visual improvement, touches only matrix.py
3. **Thumbnails** — improves usability of existing features
4. **Watchdog** — reliability, small and self-contained
5. **Health endpoint** — tiny, enables external monitoring
6. **Log viewer** — saves constant SSH sessions
7. **Overlay system** — most complex, highest value
8. **Weather widget** — new content type, self-contained
9. **Countdown timer** — simpler new content type
10. **Ken Burns** — image enhancement, contained to image renderer
11. **LED text rendering** — polish, contained to text/clock renderers
12. **Startup sequence** — small playlist.py + matrix.py change
13. **Config backup/restore** — straightforward zip operations
14. **Playlist templates** — straightforward file operations
15. **REST API** — new blueprint, well-defined scope
16. **Multi-user** — touches auth throughout, do last
17. **Mobile UI** — CSS-only mostly, do last when features are stable