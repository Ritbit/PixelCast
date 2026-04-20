"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/web/api.py                                              ║
║ Version:     1.0.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: REST API blueprint (mounted at /api/v1/) - provides complete    ║
║              JSON API for playlist, files, alerts, settings, and system      ║
║              control. Bearer token or query param authentication.            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import json
import time
import logging
import secrets
import functools

from flask import Blueprint, request, jsonify, current_app, Response

log = logging.getLogger('api')

api_bp = Blueprint('api', __name__)

_USERS_PATH  = None   # set by app factory
_API_KEY_KEY = 'api_key'


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_api_key():
    """Return the configured API key, generating one if missing."""
    try:
        with open(_USERS_PATH) as f:
            users = json.load(f)
    except Exception:
        users = {}
    if _API_KEY_KEY not in users:
        users[_API_KEY_KEY] = secrets.token_urlsafe(32)
        try:
            with open(_USERS_PATH, 'w') as f:
                json.dump(users, f, indent=2)
        except Exception:
            pass
    return users[_API_KEY_KEY]


def _check_auth():
    key = _get_api_key()
    # Check Authorization: Bearer <key>
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer ') and auth[7:] == key:
        return True
    # Check ?api_key=<key>
    if request.args.get('api_key') == key:
        return True
    return False


def require_api_key(f):
    @functools.wraps(f)
    def wrapper(*a, **kw):
        if not _check_auth():
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        return f(*a, **kw)
    return wrapper


def ok(**kwargs):
    return jsonify({'ok': True, **kwargs})


def err(msg, code=400):
    return jsonify({'ok': False, 'error': msg}), code


# ---------------------------------------------------------------------------
# Status / health
# ---------------------------------------------------------------------------

_start = time.time()


@api_bp.route('/health')
def health():
    """No auth — for monitoring."""
    engine   = current_app.config['ENGINE']
    playlist = current_app.config['PLAYLIST']
    age      = time.time() - engine._last_frame_time
    status   = 'paused' if engine._pause_event.is_set() else \
               'error'  if age > 10 else 'ok'
    item     = engine.get_status().get('current')
    return jsonify({
        'ok':             True,
        'status':         status,
        'uptime_seconds': int(time.time() - _start),
        'current_item':   item.get('name') if item else None,
        'current_type':   item.get('type') if item else None,
        'brightness':     engine.cfg.get('brightness', 80),
        'paused':         engine._pause_event.is_set(),
        'last_frame_age': round(age, 2),
        'playlist_length': len(playlist),
    })


@api_bp.route('/status')
@require_api_key
def status():
    engine   = current_app.config['ENGINE']
    playlist = current_app.config['PLAYLIST']
    st       = engine.get_status()
    return ok(
        engine=st,
        playlist_length=len(playlist),
        uptime_seconds=int(time.time() - _start),
    )


# ---------------------------------------------------------------------------
# Playlist read
# ---------------------------------------------------------------------------

@api_bp.route('/playlist')
@require_api_key
def playlist_get():
    playlist = current_app.config['PLAYLIST']
    return ok(items=playlist.items() if hasattr(playlist, 'items') else playlist.get_all())


@api_bp.route('/playlist/item/<item_id>')
@require_api_key
def playlist_item_get(item_id):
    playlist = current_app.config['PLAYLIST']
    items    = playlist.get_all()
    item     = next((i for i in items if i.get('id') == item_id), None)
    if not item:
        return err('Item not found', 404)
    return ok(item=item)


# ---------------------------------------------------------------------------
# Playlist control
# ---------------------------------------------------------------------------

@api_bp.route('/playlist/skip', methods=['POST'])
@require_api_key
def playlist_skip():
    current_app.config['ENGINE'].skip()
    return ok(action='skip')


@api_bp.route('/playlist/prev', methods=['POST'])
@require_api_key
def playlist_prev():
    playlist = current_app.config['PLAYLIST']
    engine   = current_app.config['ENGINE']
    with playlist._lock:
        n = len(playlist._items)
        if n > 0:
            playlist._index = (playlist._index - 2) % n
    engine.skip()
    return ok(action='prev')


@api_bp.route('/playlist/pause', methods=['POST'])
@require_api_key
def playlist_pause():
    current_app.config['ENGINE'].pause()
    st = current_app.config['ENGINE']._pause_event.is_set()
    return ok(paused=st)


@api_bp.route('/playlist/resume', methods=['POST'])
@require_api_key
def playlist_resume():
    engine = current_app.config['ENGINE']
    if engine._pause_event.is_set():
        engine.pause()   # toggle
    return ok(paused=False)


@api_bp.route('/playlist/restart', methods=['POST'])
@require_api_key
def playlist_restart():
    playlist = current_app.config['PLAYLIST']
    engine   = current_app.config['ENGINE']
    with playlist._lock:
        playlist._index = -1
    engine.skip()
    return ok(action='restart')


@api_bp.route('/playlist/goto/<item_id>', methods=['POST'])
@require_api_key
def playlist_goto(item_id):
    playlist = current_app.config['PLAYLIST']
    engine   = current_app.config['ENGINE']
    with playlist._lock:
        items = playlist._items
        idx   = next((i for i, it in enumerate(items)
                      if it.get('id') == item_id), None)
        if idx is None:
            return err('Item not found', 404)
        playlist._index = idx - 1
    engine.skip()
    return ok(action='goto', item_id=item_id)


# ---------------------------------------------------------------------------
# Playlist CRUD
# ---------------------------------------------------------------------------

@api_bp.route('/playlist/item', methods=['POST'])
@require_api_key
def playlist_item_add():
    data = request.get_json(silent=True) or {}
    if 'type' not in data:
        return err('type is required')
    playlist = current_app.config['PLAYLIST']
    engine   = current_app.config['ENGINE']
    item     = playlist.add_item(data)
    engine.reload_playlist()
    return ok(item=item), 201


@api_bp.route('/playlist/item/<item_id>', methods=['PUT'])
@require_api_key
def playlist_item_update(item_id):
    data = request.get_json(silent=True) or {}
    playlist = current_app.config['PLAYLIST']
    engine   = current_app.config['ENGINE']
    success  = playlist.update_item(item_id, data)
    if not success:
        return err('Item not found', 404)
    engine.reload_playlist()
    return ok(item_id=item_id)


@api_bp.route('/playlist/item/<item_id>', methods=['DELETE'])
@require_api_key
def playlist_item_delete(item_id):
    playlist = current_app.config['PLAYLIST']
    engine   = current_app.config['ENGINE']
    success  = playlist.delete_item(item_id)
    if not success:
        return err('Item not found', 404)
    engine.reload_playlist()
    return ok(item_id=item_id)


# ---------------------------------------------------------------------------
# Brightness
# ---------------------------------------------------------------------------

@api_bp.route('/brightness', methods=['GET'])
@require_api_key
def brightness_get():
    engine = current_app.config['ENGINE']
    return ok(brightness=engine.cfg.get('brightness', 80))


@api_bp.route('/brightness', methods=['PUT'])
@require_api_key
def brightness_set():
    data  = request.get_json(silent=True) or {}
    value = data.get('value')
    if value is None:
        return err('value required (0-100)')
    try:
        value = int(value)
    except (TypeError, ValueError):
        return err('value must be integer 0-100')
    if not 0 <= value <= 100:
        return err('value must be 0-100')
    current_app.config['ENGINE'].set_brightness(value)
    return ok(brightness=value)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@api_bp.route('/settings')
@require_api_key
def settings_get():
    engine = current_app.config['ENGINE']
    return ok(settings=dict(engine.cfg))


@api_bp.route('/settings', methods=['PUT'])
@require_api_key
def settings_put():
    data = request.get_json(silent=True) or {}
    engine = current_app.config['ENGINE']
    cfg_path = current_app.config.get('CONFIG_PATH', 'config/panel.json')
    engine.cfg.update(data)
    if 'brightness' in data:
        engine.set_brightness(int(data['brightness']))
    try:
        with open(cfg_path, 'w') as f:
            json.dump(engine.cfg, f, indent=2)
    except Exception as e:
        return err(f'Could not save settings: {e}')
    return ok(settings=dict(engine.cfg))


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

@api_bp.route('/files')
@require_api_key
def files_list():
    from signage.web.routes import allowed_file, file_type
    media_dir = current_app.config['MEDIA_DIR']
    files = []
    if os.path.isdir(media_dir):
        for fn in sorted(os.listdir(media_dir)):
            if '.matrix.' in fn or fn.startswith('.'):
                continue
            if allowed_file(fn):
                path = os.path.join(media_dir, fn)
                files.append({
                    'name': fn,
                    'type': file_type(fn),
                    'size': os.path.getsize(path),
                    'path': path,
                })
    return ok(files=files)


@api_bp.route('/files/<filename>', methods=['DELETE'])
@require_api_key
def files_delete(filename):
    import glob
    from werkzeug.utils import secure_filename
    from signage.transcoder import matrix_path
    from signage.thumbnailer import thumb_path
    media_dir = current_app.config['MEDIA_DIR']
    fn        = secure_filename(filename)
    path      = os.path.join(media_dir, fn)
    if not os.path.exists(path):
        return err('File not found', 404)
    os.remove(path)
    for extra in [matrix_path(path), matrix_path(path) + '.tmp.mp4',
                  thumb_path(media_dir, fn)]:
        if os.path.exists(extra):
            try: os.remove(extra)
            except: pass
    for f in glob.glob(os.path.splitext(path)[0] + '.bgcache_*.jpg'):
        try: os.remove(f)
        except: pass
    return ok(deleted=fn)


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------

@api_bp.route('/alert', methods=['POST'])
@require_api_key
def alert_post():
    """
    Display a high-priority alert over the playlist.

    Body (JSON):
      text      : str  (required)
      duration  : int  seconds (default 10)
      color     : [R,G,B] (default [255,50,50])
      bg_color  : [R,G,B] (default [0,0,0])
      font_size : int (default 20)
      scroll    : 'left'|'right'|'up'|'down'|false (default false)
      scroll_speed: float (default 2)
      align     : 'center'|'left'|'right' (default 'center')
    """
    data     = request.get_json(silent=True) or {}
    alert_mgr = current_app.config.get('ALERT_MANAGER')
    if not alert_mgr:
        return err('Alert manager not available', 503)

    # Accept either legacy {text:..} or new {lines:[...]} format
    if 'lines' not in data and 'text' not in data:
        return err('lines or text is required')

    # Normalise: if plain text provided, wrap as single line
    if 'lines' not in data:
        data['lines'] = [{
            'text':      data.get('text', ''),
            'color':     data.get('color', [255, 50, 50]),
            'font_size': data.get('font_size', 20),
            'align':     data.get('align', 'center'),
            'scroll':    data.get('scroll', False),
            'scroll_speed': data.get('scroll_speed', 2),
        }]

    if not any(l.get('text','').strip() for l in data['lines']):
        return err('At least one line must have text')

    alert_mgr.show(data)
    return ok(active=True, lines=len(data['lines']))


@api_bp.route('/alert', methods=['DELETE'])
@require_api_key
def alert_delete():
    alert_mgr = current_app.config.get('ALERT_MANAGER')
    if alert_mgr:
        alert_mgr.clear()
    return ok(active=False)


@api_bp.route('/alert', methods=['GET'])
@require_api_key
def alert_status():
    alert_mgr = current_app.config.get('ALERT_MANAGER')
    if not alert_mgr:
        return ok(active=False)
    return ok(active=alert_mgr.is_active(),
              remaining=alert_mgr.remaining_seconds())


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

@api_bp.route('/snapshot')
@require_api_key
def snapshot():
    import io
    from PIL import Image
    engine = current_app.config['ENGINE']
    frame  = engine.get_current_frame()
    scale  = int(request.args.get('scale', 4))
    img    = Image.fromarray(frame.astype('uint8'), 'RGB')
    img    = img.resize((frame.shape[1] * scale, frame.shape[0] * scale),
                        Image.NEAREST)
    buf    = io.BytesIO()
    img.save(buf, 'JPEG', quality=85)
    buf.seek(0)
    return Response(buf.read(), mimetype='image/jpeg',
                    headers={'Content-Disposition':
                             'inline; filename=snapshot.jpg'})


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

@api_bp.route('/logs')
@require_api_key
def logs():
    lines = min(int(request.args.get('lines', 100)), 1000)
    try:
        import subprocess
        result = subprocess.run(
            ['journalctl', '-u', 'led-signage', '-n', str(lines),
             '--no-pager', '--output=short-iso'],
            capture_output=True, text=True, timeout=5)
        raw = result.stdout.strip().split('\n') if result.stdout else []
    except Exception as e:
        raw = [f'Error: {e}']
    return ok(lines=raw, count=len(raw))


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

@api_bp.route('/system/restart', methods=['POST'])
@require_api_key
def system_restart():
    import subprocess
    subprocess.Popen(['systemctl', 'restart', 'led-signage'])
    return ok(action='restart')


@api_bp.route('/system/reboot', methods=['POST'])
@require_api_key
def system_reboot():
    import subprocess
    subprocess.Popen(['reboot'])
    return ok(action='reboot')


@api_bp.route('/system/poweroff', methods=['POST'])
@require_api_key
def system_poweroff():
    import subprocess
    subprocess.Popen(['shutdown', '-h', 'now'])
    return ok(action='poweroff')
