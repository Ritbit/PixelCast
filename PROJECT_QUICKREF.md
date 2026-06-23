# LED Signage — Quick Reference Cheatsheet

## Deployment
```bash
cd /opt/PixelCast && tar -xzf /root/led-signage.tar.gz && sudo systemctl restart led-signage
journalctl -u led-signage -f
```

**Important:** The systemd service requires `SIGNAGE_SECRET` environment variable for Flask session security. This is auto-generated during installation, or set manually in `/etc/systemd/system/led-signage.service`.

## Key Paths
| What | Path |
|---|---|
| Application code | `/opt/PixelCast/led-signage/` |
| Config files | `/opt/PixelCast/config/` |
| Media files | `/opt/PixelCast/media/` |
| Playlist | `/opt/PixelCast/config/playlist.json` |
| Users + API key | `/opt/PixelCast/config/users.json` |
| Panel config | `/opt/PixelCast/config/panel.json` |
| Transcoded video | `/opt/PixelCast/media/*.matrix.mp4` |
| Thumbnails | `/opt/PixelCast/media/.thumbs/` |
| Weather icons | `/opt/PixelCast/media/weather-icons/` |
| Fonts | `/opt/PixelCast/led-signage/fonts/` + system fonts |

**Note:** Config and media are at `/opt/PixelCast` level (persistent), code is in `/opt/PixelCast/led-signage` (replaceable).

## Display
- Resolution: **256×128** px
- Frame format: `numpy (128, 256, 3) uint8 RGB`
- `show_frame()` submits frame to `_OutputThread` (non-blocking) — never blocks on GPIO
- `_OutputThread` calls `FrameCanvas.SetImage(pil, unsafe=True)` then `matrix.SwapOnVSync(canvas)` — tearing-free double-buffer swap
- PIL image is a zero-copy `Image.frombuffer()` view into the numpy array (no allocation)
- Queue `maxsize=1` — stale frames dropped, display always shows latest
- CPU layout: render→core 1, output→core 2, C++ GPIO refresh→core 3
- Brightness: 0–100 (stored in panel.json, applied at matrix init)
- `engine.get_perf_stats()` → `{frames_output, frames_dropped, canvas_mode}` | `GET /system/perf`

## Adding a New Renderer
1. Create `signage/renderer/mytype.py` extending `BaseRenderer`
2. Implement `first_frame() → ndarray`, `frames() → generator`, `close()`
3. Add to `signage/renderer/__init__.py` `get_renderer()` factory
4. Add item type to `VALID_TYPES` in routes.py
5. Add editor section to `edit_item.html` (`{% if item.type == 'mytype' %}`)
6. Add to `STATIC_TYPES` in matrix.py if it has a stable first frame

## Adding a New Route
```python
@blueprint.route('/path', methods=['GET','POST'])
@login_required
@require_role('editor')   # or @require_admin
def my_view():
    ...
```

## Playlist Item — Required Fields
```json
{"id": "uuid4", "type": "text", "name": "...", "duration": 10}
```
All other fields are optional with renderer defaults.

## Text Line — Full Schema
```json
{
  "text": "Hello",
  "color": [255, 255, 255],
  "font": "FreeSans.ttf",
  "font_size": 20,
  "align": "center",
  "position": null,
  "scroll": false,
  "scroll_speed": 2.0,
  "scroll_gap": 40,
  "loop_count": 0,
  "wrap": true,
  "pixel_font": false
}
```

## Scroll Directions
`"left"` `"right"` `"up"` `"down"` `false`
Speed is px/frame (float, e.g. `0.5` = very slow).
`loop_count: 0` = infinite, `1` = once then freeze, `N` = N passes.

## Auto Duration
```json
{"duration": "auto"}
```
Renderer must set `self._done = True` when content complete.
0.15s grace period after `_done` before engine advances.

## Inline Text Codes
```
§Cff0000;   → red
§FFreeSansBold.ttf;  → bold font
§S28;       → 28px size
§R          → reset to line defaults
```

## LED Pixel Rendering
- Auto: font_size ≤ 16px
- Manual: `"pixel_font": true`
- Threshold: grey > 32/255 = on, else off
- DejaVuSans auto-selected at ≤16px (better hinting than FreeSans)

## Background Options
```json
"bg_mode": "color",   "bg_color": [0, 0, 0]
"bg_mode": "corner",  "bg_corner": "top-left"
"bg_mode": "image",   "bg_image": "/root/led-signage/media/bg.jpg",
                      "bg_dim": 40
```

## Transitions
`fade` `fade_black` `wipe_left/right/up/down` `slide_left/right/up/down`
`zoom_in/out` `dissolve` `melt` `snow` `spiral` `drop`
`blinds_h/v` `checkerboard` `pixelate` `none`
Speed: float 0.1–5.0 (higher = faster)

## Roles
```
viewer  → read-only
editor  → content + files + alerts + brightness
admin   → full including users, hardware settings, reboot
```

## API Quick Reference
```bash
KEY="your-api-key"
PI="192.168.2.173"
H="Authorization: Bearer $KEY"

# Status
curl -H "$H" http://$PI/api/v1/status

# Control
curl -X POST -H "$H" http://$PI/api/v1/playlist/skip
curl -X POST -H "$H" http://$PI/api/v1/playlist/pause
curl -X PUT  -H "$H" http://$PI/api/v1/brightness \
     -H "Content-Type: application/json" -d '{"value": 70}'

# Alert
curl -X POST -H "$H" http://$PI/api/v1/alert \
     -H "Content-Type: application/json" \
     -d '{"lines":[{"text":"FIRE!","font_size":32,"color":[255,0,0]}],"duration":60}'
curl -X DELETE -H "$H" http://$PI/api/v1/alert

# Playlist CRUD
curl -H "$H" http://$PI/api/v1/playlist
curl -X POST -H "$H" -H "Content-Type: application/json" \
     http://$PI/api/v1/playlist/item \
     -d '{"type":"text","name":"API Test","duration":10,"lines":[{"text":"Hello","font_size":24}]}'
curl -X DELETE -H "$H" http://$PI/api/v1/playlist/item/ITEM_ID

# Snapshot
curl -H "$H" http://$PI/api/v1/snapshot?scale=4 -o snap.jpg
```

## Gotchas Checklist

| Issue | Fix |
|---|---|
| Template won't load | Block count mismatch — count `{% block %}` vs `{% endblock %}` |
| Checkbox not saving | Need hidden sentinel field before each checkbox |
| `ValueError: truth value ambiguous` | Use `if x is None:` not `if not x:` for numpy arrays |
| `Cannot change thread_type after codec is open` | Set `stream.thread_type='AUTO'` in `_open()` before any seek/demux |
| Alert "not available" | Check `alert_manager=alert_mgr` is passed to `create_app()` |
| `kwargs not defined` in `create_app` | Function uses named params, not `**kwargs` — use param name directly |
| Screentest shows over playlist | `pause_for_test()` must set `_test_mode` Event + `_skip_event.set()` |
| Video loops but auto-dur set | `loop_count` must be > 0 for auto-dur to advance |
| Pixel font checkbox ignored | Check sentinel field is present, check `require_role` isn't blocking POST |
| Duplicate `{% block scripts %}` | Merge scripts into single block — Jinja2 allows only one per name |
| MJPEG not reconnecting | Remove + recreate `<img>` element — don't just change `src` |

## Pre-packaging Checklist
```bash
# 1. Syntax check all changed .py files
python3 -m py_compile signage/renderer/text.py  # repeat for each

# 2. Check template blocks
python3 -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('signage/web/templates'))
for t in ['edit_item.html','playlist.html','settings.html','alert.html']:
    env.get_template(t); print('OK', t)
"

# 3. Remove pycache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true

# 4. Package
tar -czf led-signage.tar.gz --exclude='led-signage/**/__pycache__' led-signage/
```