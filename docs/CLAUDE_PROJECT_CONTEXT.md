# PixelCast — Project Context

> **For AI assistants:** Read this entire document before writing any code.
> This is a live production system on a Raspberry Pi. All changes are deployed
> via `tar -xzf led-signage.tar.gz && sudo systemctl restart led-signage`.

---

## Hardware

| Component | Detail |
|---|---|
| Controller | Raspberry Pi 4B |
| HAT | ElectroDragon MPC1073 HUB75 HAT |
| Panels | 4× P2.5 128×64 HUB75E panels, arranged 2×2 |
| Total resolution | **256×128 pixels** |
| Panel scan | 1/32 scan, requires E address line jumper on MPC1073 |
| GPIO mapping | `regular` (NOT adafruit-hat) |
| OS | Raspberry Pi OS Lite 64-bit (Bookworm/Debian 13) |
| Python | 3.13 |

**Critical hardware notes:**
- Onboard audio MUST be disabled (`dtparam=audio=off` + blacklist `snd_bcm2835`) — conflicts with matrix PWM
- MPC1073 has 3 parallel outputs: P0→panels 1+2 (top row), P1→panels 3+4 (bottom row)
- All binaries and daemon must run as root for GPIO access
- Panels need dedicated 5V PSU — NOT from Pi GPIO rail

**Working hzeller flags:**
```
--led-gpio-mapping=regular
--led-rows=64 --led-cols=128
--led-chain=2 --led-parallel=2
--led-slowdown-gpio=4
--led-pwm-bits=7 --led-pwm-lsb-nanoseconds=50 --led-pwm-dither-bits=1
```

---

## Project File Structure

```
/root/led-signage/
├── daemon.py                    # Entry point — starts engine + web + scheduler
├── install.sh                   # Full redeploy script
├── led-signage.service          # Systemd unit file
├── nginx-led-signage.conf       # Nginx reverse proxy config
├── requirements.txt
├── fonts/                       # TTF fonts (system fonts also searched)
├── config/
│   ├── panel.json               # Hardware config + display dimensions
│   ├── playlist.json            # Live playlist (auto-saved on every change)
│   ├── schedule.json            # On/off/dim schedule rules
│   └── users.json               # Auth credentials + API key + roles
├── media/                       # Uploaded media files
│   ├── *.matrix.mp4             # Auto-transcoded video (256×128 25fps)
│   ├── .thumbs/                 # Generated thumbnails (160×90 JPEG)
│   └── weather-icons/           # WMO-numbered PNGs (0.png, 61.png …)
└── signage/
    ├── __init__.py
    ├── matrix.py                # MatrixEngine — owns display, runs render loop
    ├── playlist.py              # PlaylistManager — thread-safe CRUD + navigation
    ├── scheduler.py             # Scheduler — on/off/dim by time+day
    ├── alert.py                 # AlertManager — high-priority overlay
    ├── watchdog.py              # Watchdog — frame-age based restart
    ├── transcoder.py            # ffmpeg video transcoding to display size
    ├── thumbnailer.py           # ffmpeg thumbnail generation
    ├── timecode.py              # Timecode parser (ss, ss.ff, mm:ss, hh:mm:ss)
    ├── renderer/
    │   ├── __init__.py          # get_renderer(item, w, h, lightweight=False)
    │   ├── base.py              # BaseRenderer ABC
    │   ├── utils.py             # load_background(), fit_image(), parse_color(), KenBurns
    │   ├── image.py             # Static images (JPG/PNG/BMP/WebP) + Ken Burns
    │   ├── gif.py               # Animated GIF
    │   ├── video.py             # Video via PyAV (ffmpeg), start_offset, loop modes
    │   ├── clock.py             # Digital clock, configurable fonts/sizes, pixel rendering
    │   ├── text.py              # Multi-line text, per-line options, scroll strips, pixel rendering
    │   ├── weather.py           # Open-Meteo weather, WMO icons, configurable fonts
    │   └── countdown.py        # Countdown/countup timer
    ├── transitions/
    │   ├── __init__.py          # get_transition(name, speed) factory
    │   └── effects.py           # 22 effects (see list below)
    └── web/
        ├── __init__.py
        ├── app.py               # Flask factory — registers all blueprints
        ├── auth.py              # Flask-Login, roles (viewer/editor/admin), SHA-256 passwords
        ├── api.py               # REST API blueprint at /api/v1/
        ├── filters.py           # Jinja2 filters: basename, rgb_hex, timecode
        ├── routes.py            # All web blueprints: main, playlist, files, control, schedule, system
        └── templates/
            ├── base.html        # Nav (role-gated), flash messages, CSS design system
            ├── login.html
            ├── index.html       # Dashboard: MJPEG live preview, controls, brightness
            ├── playlist.html    # Playlist CRUD + drag-drop reorder + import/export + file picker modal
            ├── edit_item.html   # Per-item editor with all type-specific options
            ├── files.html       # Media upload/manage (drag-drop, XHR progress, thumbnails)
            ├── schedule.html    # On/off/dim rules by time+day
            ├── settings.html    # Panel config + user management + API key + system controls
            ├── alert.html       # Priority alert sender with full text editor UI
            ├── screentest.html  # Screen test patterns
            ├── logs.html        # Live log viewer
            ├── stats.html       # System stats
            └── error.html       # Custom error pages
```

---

## Architecture

### Threading model
```
main thread       → shutdown_event.wait()
MatrixEngine      → daemon thread, owns RGBMatrix exclusively
Scheduler         → daemon thread, checks rules every 30s
Watchdog          → daemon thread, restarts engine if frame age > timeout
Flask/Werkzeug    → daemon thread
AlertManager      → no thread — composites in show_frame() on engine thread
PreRender         → short-lived daemon threads, one per next-item peek
VideoPreBuffer    → daemon thread per video item
```

### Display loop (matrix.py — MatrixEngine.run())
```
advance playlist → check date range → create renderer → get first_frame()
→ background pre-render of next static item
→ run wipe-in transition (skip if prev wipe-out already landed on this frame)
→ render loop: yield frames until duration expires, _done fires, or skip signal
→ peek next item → run wipe-out transition to next item's first frame
→ track prev_wipeout_target to avoid double-show
→ repeat
```

**Critical details:**
- `prev_wipeout_target`: if wipe-out already displayed next item's first frame, skip the wipe-in. Prevents double-show.
- `_test_mode` (threading.Event): set → engine idles; `show_frame(_from_test=True)` bypasses the guard
- `_done` flag on renderer: used by engine for auto-duration items
- Alert overlay: `show_frame()` calls `_alert_mgr.get_frame()` and replaces frame if alert active
- Frame cache: `{item_id → numpy frame}` — pre-renders next static item during current item's playback
- Auto-duration grace: 0.15s after `_done` fires before advancing (lets last content clear screen)

### Renderer contract
```python
renderer.first_frame() → np.ndarray (H, W, 3) uint8 RGB
renderer.frames()      → generator yielding np.ndarray, runs until close()
renderer.close()       → cleanup resources
renderer._done         → bool, set True when content complete (for auto-duration)
```
- `lightweight=True` in constructor → skip network fetches and pre-buffering (used for peek/transition)
- All renderers call `time.sleep()` inside `frames()` to pace output
- `renderer._first` attribute may be injected by engine if a pre-rendered frame is available

---

## Playlist Item Schema

```json
{
  "id": "uuid4",
  "type": "clock|text|image|gif|video|weather|countdown",
  "name": "Display name",
  "enabled": true,
  "duration": 15,
  "duration": "auto",
  "wipe_in": "fade",
  "wipe_in_speed": 1.0,
  "wipe_out": "slide_left",
  "wipe_out_speed": 1.0,
  "date_from": "2026-01-01T00:00:00",
  "date_to":   "2026-12-31T23:59:59",

  "bg_mode":          "color|corner|image",
  "bg_color":         [0, 0, 0],
  "bg_corner":        "top-left|top-right|bottom-left|bottom-right",
  "bg_image":         "/root/led-signage/media/bg.jpg",
  "bg_dim":           0,
  "bg_scale":         "cover|contain|stretch|custom",
  "bg_scale_factor":  1.0,
  "bg_offset_x":      0,
  "bg_offset_y":      0,

  "clock": {
    "format":          "%H:%M:%S",
    "date_format":     "%A %d %B %Y",
    "color":           [255, 220, 0],
    "date_color":      [180, 180, 180],
    "time_font":       "FreeSansBold.ttf",
    "date_font":       "FreeSans.ttf",
    "time_size":       null,
    "date_size":       null,
    "blink_separator": true,
    "pixel_font":      false
  },

  "text": {
    "v_center": false,
    "lines": [
      {
        "text":         "Hello §Cff0000;World§R;",
        "color":        [255, 255, 255],
        "font":         "FreeSans.ttf",
        "font_size":    20,
        "align":        "center|left|right",
        "position":     null,
        "scroll":       false,
        "scroll_speed": 2.0,
        "scroll_gap":   40,
        "loop_count":   0,
        "wrap":         true,
        "pixel_font":   false
      }
    ]
  },

  "image_gif": {
    "file":         "/root/led-signage/media/image.png",
    "scale_mode":   "fit|fill|stretch|custom",
    "scale_factor": 1.0,
    "position":     "center",
    "ken_burns":    false,
    "kb_zoom_start": 1.0,
    "kb_zoom_end":   1.25,
    "kb_direction":  "random|in|out|pan_left|pan_right|pan_up|pan_down"
  },

  "video": {
    "file":         "/root/led-signage/media/video.matrix.mp4",
    "scale_mode":   "fit|fill|stretch",
    "loop":         true,
    "loop_mode":    "restart|pingpong",
    "loop_count":   0,
    "start_offset": "1:30.12",
    "fps_override": null,
    "prebuffer":    false
  },

  "weather": {
    "latitude":      52.37,
    "longitude":     4.89,
    "location_name": "Amsterdam",
    "units":         "celsius|fahrenheit",
    "forecast_days": 3,
    "show_humidity": true,
    "show_wind":     true,
    "icon_dir":      "/root/led-signage/media/weather-icons",
    "font":          "FreeSansBold.ttf",
    "font_regular":  "FreeSans.ttf",
    "font_size_big": null,
    "font_size_med": null,
    "font_size_sm":  null
  },

  "countdown": {
    "target_date":   "2027-01-01T00:00:00",
    "direction":     "down",
    "format_parts":  ["days","hours","minutes","seconds"],
    "separator":     " ",
    "show_labels":   true,
    "label_style":   "short",
    "number_color":  [255, 200, 0],
    "prefix_text":   "",
    "suffix_text":   "",
    "finished_text": "Done!"
  }
}
```

---

## Text Inline Style Codes

```
§Crrggbb;   — change color (hex, e.g. §Cff0000; = red)
§Fname;     — change font (e.g. §FFreeSansBold.ttf;)
§Snn;       — change font size (e.g. §S24;)
§R          — reset to line defaults
```

Newlines (`\n`) in text split into separate wrapped visual lines.
Control characters below ASCII 32 are stripped (except `\n` and `\t`).

---

## LED Pixel Rendering

Fonts at ≤16px use hard-pixel rendering (no anti-aliasing):
- Renders to greyscale `L` image, thresholds at 32/255, converts to binary mask
- Eliminates sub-pixel colour bleed visible at 2.5mm LED pitch
- `pixel_font: true` on any item forces this mode regardless of size
- Text renderer auto-selects DejaVuSans (better hinting) at ≤16px when no font explicitly set
- Applies to: `text.py` (per line), `clock.py` (time + date independently)

---

## Auto Duration

Set `"duration": "auto"` on an item. Engine advances when `renderer._done = True`:
- **Text**: fires after all scrolling lines complete `loop_count` passes (default 1 for auto-dur)
- **Video**: fires after `loop_count` plays
- 0.15s grace period after `_done` so last pixel clears the screen

`loop_count` (text per-line, video global): 0 = infinite, 1 = play once, N = N times.

---

## Scroll Strip Caching

Left/right/up/down scrolls pre-render a full numpy strip in `__init__`:
- H-scroll: `(display_h, text_w + gap × 2, 3)` strip, sliced each frame
- V-scroll: `(display_h + content_h + display_h, display_w, 3)` strip
- Background tiled into strip during build
- `frames()` just slices with numpy indexing — no per-frame Pillow drawing

---

## Video Transcoding

On upload, every video is automatically transcoded to 256×128 25fps H.264:
- `transcoder.transcode_async()` runs in background thread
- Output: `media/original_name.matrix.mp4`
- `resolve_video_path()` transparently returns `.matrix.mp4` if it exists
- `.matrix.` files are hidden from all file pickers and listings
- Delete cascades to `.matrix.mp4` and thumbnail

---

## Transitions (22 effects)

`fade`, `fade_black`, `wipe_left`, `wipe_right`, `wipe_up`, `wipe_down`,
`slide_left`, `slide_right`, `slide_up`, `slide_down`,
`zoom_in`, `zoom_out`, `dissolve`, `melt`, `snow`, `spiral`,
`drop`, `blinds_h`, `blinds_v`, `checkerboard`, `pixelate`, `none`

Each has `wipe_in` / `wipe_out` + `wipe_in_speed` / `wipe_out_speed` (0.1–5.0).

---

## Authentication & Roles

Three roles with ascending privilege:

| Role | Dashboard | Playlist R | Playlist W | Files W | Alert | Settings | User Mgmt | Reboot |
|---|---|---|---|---|---|---|---|---|
| viewer | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| editor | ✓ | ✓ | ✓ | ✓ | ✓ | brightness | ✗ | ✗ |
| admin  | ✓ | ✓ | ✓ | ✓ | ✓ | full | ✓ | ✓ |

- Credentials in `config/users.json` (SHA-256 hashed passwords)
- Default: `admin` / `admin` — change immediately
- `require_role('editor')` / `require_admin` decorators in `auth.py`
- User management UI in Settings (admin only): add/remove users, change roles, reset passwords
- Cannot delete last admin or demote self

---

## REST API

Base URL: `/api/v1/`
Auth: `Authorization: Bearer <key>` or `?api_key=<key>`
API key: shown in Settings, stored in `config/users.json` as `"api_key"`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/health` | none | Service health check |
| GET | `/status` | ✓ | Full engine + playlist status |
| GET | `/playlist` | ✓ | All playlist items |
| GET | `/playlist/item/<id>` | ✓ | Single item |
| POST | `/playlist/item` | ✓ | Add item (body: item JSON) |
| PUT | `/playlist/item/<id>` | ✓ | Update item (partial JSON) |
| DELETE | `/playlist/item/<id>` | ✓ | Delete item |
| POST | `/playlist/skip` | ✓ | Skip to next |
| POST | `/playlist/prev` | ✓ | Go to previous |
| POST | `/playlist/pause` | ✓ | Pause/resume toggle |
| POST | `/playlist/resume` | ✓ | Resume |
| POST | `/playlist/restart` | ✓ | Jump to start |
| POST | `/playlist/goto/<id>` | ✓ | Jump to item |
| GET | `/brightness` | ✓ | Get brightness |
| PUT | `/brightness` | ✓ | Set brightness `{"value": 0-100}` |
| GET | `/settings` | ✓ | Panel config |
| PUT | `/settings` | ✓ | Update panel config |
| GET | `/files` | ✓ | List media files |
| DELETE | `/files/<filename>` | ✓ | Delete file + derivatives |
| GET | `/alert` | ✓ | Alert status |
| POST | `/alert` | ✓ | Show alert (see schema below) |
| DELETE | `/alert` | ✓ | Clear alert |
| GET | `/snapshot` | ✓ | Current frame as JPEG (`?scale=4`) |
| GET | `/logs` | ✓ | Journald log lines (`?lines=100`) |
| POST | `/system/restart` | ✓ | Restart service |
| POST | `/system/reboot` | ✓ | Reboot Pi |
| POST | `/system/poweroff` | ✓ | Power off Pi |

### Alert API body

```json
{
  "lines": [
    {"text": "ALERT", "font": "FreeSansBold.ttf", "font_size": 28,
     "color": [255, 50, 0], "align": "center",
     "scroll": "left", "scroll_speed": 2.0, "wrap": true}
  ],
  "bg_color": [20, 0, 0],
  "bg_image": "/root/led-signage/media/bg.jpg",
  "bg_dim": 40,
  "v_center": true,
  "duration": 30
}
```

Legacy single-text format also accepted: `{"text": "...", "color": [R,G,B], "duration": 10}`.

---

## Web UI Routes (full list)

| Blueprint | Route | Role | Description |
|---|---|---|---|
| main | GET / | viewer | Dashboard + MJPEG preview |
| main | GET/POST /login | — | Login |
| main | GET /logout | any | Logout |
| main | GET/POST /settings | editor | Settings (hardware save: admin) |
| main | GET /alert | editor | Alert sender UI |
| main | GET /screentest | editor | Screen test patterns |
| main | GET /health | — | Health check (no auth) |
| main | GET /api/fonts | viewer | Available TTF fonts JSON |
| main | GET /api/video_info | viewer | Video metadata JSON |
| playlist | GET /playlist/ | viewer | Playlist manager |
| playlist | POST /playlist/add | editor | Add item |
| playlist | POST /playlist/delete/<id> | editor | Delete item |
| playlist | POST /playlist/move/<id>/<dir> | editor | Reorder |
| playlist | POST /playlist/duplicate/<id> | editor | Clone |
| playlist | POST /playlist/reorder | editor | Drag-drop reorder |
| playlist | GET/POST /playlist/edit/<id> | viewer/editor | Edit item (write: editor) |
| playlist | GET /playlist/export | viewer | Download playlist.json |
| playlist | GET /playlist/export_with_media | viewer | Download zip |
| playlist | POST /playlist/import | editor | Import playlist |
| files | GET /files/ | viewer | File manager |
| files | POST /files/upload | editor | Upload files |
| files | POST /files/delete/<n> | editor | Delete file |
| files | GET /files/serve/<n> | viewer | Serve file |
| files | GET /files/thumb/<n> | viewer | Serve thumbnail |
| files | POST /files/transcode/<n> | editor | Manual transcode |
| control | POST /control/skip | editor | Skip |
| control | POST /control/pause | editor | Pause toggle |
| control | POST /control/prev | editor | Previous |
| control | POST /control/brightness | editor | Set brightness |
| control | GET /control/status | viewer | JSON status |
| control | GET /control/stream | viewer | MJPEG stream |
| control | GET /control/snapshot | viewer | Single JPEG |
| control | POST /control/restart_daemon | admin | Restart service |
| control | POST /control/poweroff | admin | Power off |
| control | POST /control/reboot | admin | Reboot |
| schedule | GET/POST /schedule/ | editor | Schedule editor |
| schedule | POST /schedule/delete_rule/<idx> | editor | Delete rule |
| system | GET /system/logs | viewer | Log viewer |
| system | GET /system/stats | viewer | System stats |
| system | GET /system/backup | viewer | Download backup |
| system | POST /system/restore | admin | Restore backup |

---

## Alert System

`AlertManager` in `signage/alert.py`:
- Wraps a `TextRenderer` instance with the alert config
- `engine.set_alert_manager(mgr)` called at startup
- `show_frame()` calls `alert_mgr.get_frame()` every frame — composites on top if active
- Uses `frames()` generator so scrolling alerts actually scroll
- Alert config matches text item schema (lines, bg_color, bg_image, v_center, duration)
- Auto-clears when duration expires

---

## Pre-render / Frame Cache

When an item is playing, the engine kicks off a background thread to pre-render the *next* item's first frame into `_frame_cache[item_id]` if it's a static type (image, gif, text, clock, countdown, weather). On advance, the cached frame is injected into the renderer as `renderer._first`, making the transition wipe-out start immediately without decode delay.

---

## Background System (utils.py)

`load_background(width, height, item)` builds and **caches** a PIL Image:
- `bg_mode='color'` → solid fill
- `bg_mode='corner'` → sample pixel from image corner
- `bg_mode='image'` → load + resize image, apply dim

Cache key includes size, scale, factor, offsets, dim — stored as `.bgcache_HASH.jpg` sidecar file.

---

## Weather Icons

Extracted from a PNG sprite sheet into `/root/led-signage/media/weather-icons/`.
Named by WMO code: `0.png`, `2.png`, `61.png` etc.
Renderer tries `{code}.png` then `{icon_key}.png`, falls back to built-in geometric icon.
15-minute refresh interval from Open-Meteo (no API key required).

---

## Known Issues & Gotchas

### Jinja2 limitations
- `tuple()`, `enumerate()` NOT available in templates
- Use `loop.index0` instead of `enumerate()`
- Use `| rgb_hex` filter instead of `'%02x%02x%02x' % tuple(color)`
- Always verify block count after editing: `block` count must equal `endblock` count
- Run `jinja2.Environment().get_template()` locally to catch syntax errors before deploy

### Checkbox POST collection
HTML checkboxes only submit when checked — `getlist('name')` returns sparse list.
**Fix**: emit a hidden sentinel field `<input type="hidden" name="foo_sentinel" value="0">` before each checkbox. Collect sentinels to get line count, pair with checkbox values positionally.

### Template block structure
```
{% extends 'base.html' %}
{% block title %}...{% endblock %}
{% block head %}...{% endblock %}      ← optional
{% block content %}
...
{% endblock %}
{% block scripts %}                    ← optional
...
{% endblock %}
```
Each block name must appear **exactly once** in a template. Duplicate block = TemplateAssertionError.

### Screen test exclusivity
`pause_for_test()` sets `_test_mode` Event and calls `_skip_event.set()` to interrupt the running renderer.
Engine idles in a `while _test_mode.is_set()` loop.
`show_frame()` drops calls without `_from_test=True` while test mode is active.
`resume_playlist()` clears test mode and calls `_skip_event.set()` to restart.

### thread_type for PyAV
`stream.thread_type = 'AUTO'` **must** be set immediately after opening the stream, before any `seek()` or `demux()` call — those open the codec and the attribute becomes read-only.
Set it in `VideoRenderer._open()` right after `self._container.streams.video[0]`.

### numpy truth value
`if self._first is None:` — NOT `if not self._first:` (numpy arrays raise ValueError for bool).

### MJPEG preview
Changing `src` on existing `<img>` doesn't reliably reconnect MJPEG in all browsers.
Must remove + recreate the `<img>` element to force new TCP connection.

### Font search order
```python
FONT_SEARCH = [
    '/root/led-signage/fonts/',
    '/usr/share/fonts/truetype/freefont/',
    '/usr/share/fonts/truetype/dejavu/',
    '/usr/share/fonts/truetype/',
]
```
Available fonts: FreeSans, FreeSansBold, FreeMono, FreeSerif, DejaVuSans, DejaVuSans-Bold, DejaVuSansMono

### colors in JSON
Always `[R, G, B]` lists (0–255). `parse_color()` in `utils.py` handles lists, tuples, `"#rrggbb"` strings, and ints.

---

## Development Workflow

```bash
# Deploy on Pi
cd /root && tar -xzf led-signage.tar.gz && sudo systemctl restart led-signage

# Watch logs
journalctl -u led-signage -f

# Manual debug run
sudo python3 /root/led-signage/daemon.py
```

**Before packaging, always:**
1. `python3 -m py_compile signage/renderer/text.py` etc on all changed .py files
2. Check template blocks: `grep -c "block\|endblock" template.html`
3. Verify Jinja2: `python3 -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('signage/web/templates')).get_template('settings.html')"`
4. `find . -name __pycache__ -exec rm -rf {} +` before `tar`
5. Package: `tar -czf led-signage.tar.gz --exclude='led-signage/**/__pycache__' led-signage/`

---

## Pending / Future Features

- **Playlist item preview** — call `renderer.first_frame()` server-side, return as scaled JPEG via `/playlist/preview/<id>`, show as thumbnail in playlist editor
- **Overlay system** — persistent layer (clock corner, news ticker) composited on top of all content, separate from alert system
- **Gamma/colour correction** — per-channel LUT with sliders in Settings
- **Playlist templates** — save/restore named playlist presets
- **GPIO trigger inputs** — physical button → skip/alert/scene
- **Multi-day schedule** — finer-grained day-of-week + date range rules
- **Ken Burns on video** — currently only on ImageRenderer
- **Mobile-friendly nav** — bottom tab bar for phone use