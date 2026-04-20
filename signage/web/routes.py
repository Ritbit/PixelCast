"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/web/routes.py                                           ║
║ Version:     1.0.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: All Flask route blueprints - dashboard, playlist, files,        ║
║              control, schedule, settings, alerts, logs, and system routes.   ║
║              Implements full web UI with role-based access control.          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import json
import subprocess
import logging
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, jsonify, current_app,
                   send_from_directory, abort)
from flask_login import login_required, login_user, logout_user, current_user
from .auth import (require_role, require_admin, require_editor,
                   load_users, save_users, hash_password, verify_password,
                   _load_full, _save_full)
from werkzeug.utils import secure_filename

from .auth import load_users, verify_password, hash_password, User
from signage.transitions import REGISTRY as TRANSITION_REGISTRY
from signage.playlist import VALID_TYPES

log = logging.getLogger('web.routes')

ALLOWED_EXTENSIONS = {
    'image': {'png', 'jpg', 'jpeg', 'bmp', 'webp'},
    'gif':   {'gif'},
    'video': {'mp4', 'webm', 'avi', 'mkv', 'mov'},
}
ALL_ALLOWED = set().union(*ALLOWED_EXTENSIONS.values())


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALL_ALLOWED


def file_type(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    for t, exts in ALLOWED_EXTENSIONS.items():
        if ext in exts:
            return t
    return 'unknown'


# ---------------------------------------------------------------------------
# Main blueprint (login, dashboard)
# ---------------------------------------------------------------------------
main_bp = Blueprint('main', __name__)

import pathlib as _pathlib
_BRAND_DIR = _pathlib.Path(__file__).parent.parent.parent / 'media'


@main_bp.route('/brand/<path:filename>')
def brand(filename):
    """Serve branding assets (favicons, logos) without requiring login."""
    return send_from_directory(str(_BRAND_DIR), filename)


@main_bp.route('/')
@login_required
def index():
    engine   = current_app.config['ENGINE']
    playlist = current_app.config['PLAYLIST']
    return render_template('index.html',
                           status=engine.get_status(),
                           playlist=playlist.get_all(),
                           transitions=sorted(TRANSITION_REGISTRY.keys()))


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        users    = load_users(current_app.config['USERS_PATH'])

        if username in users and \
           verify_password(password, users[username]['password_hash']):
            user = User(username, users[username])
            login_user(user, remember=True)
            log.info(f"Login: {username}")
            return redirect(url_for('main.index'))
        else:
            flash('Invalid username or password.', 'error')

    return render_template('login.html')


@main_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.login'))


@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@require_role('editor')
def settings():
    engine     = current_app.config['ENGINE']
    users_path = current_app.config['USERS_PATH']

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'brightness':
            pct = int(request.form.get('brightness', 80))
            engine.set_brightness(pct)
            flash(f'Brightness set to {pct}%', 'success')

        elif action == 'change_password':
            old_pw  = request.form.get('old_password', '')
            new_pw  = request.form.get('new_password', '')
            confirm = request.form.get('confirm_password', '')
            users   = load_users(users_path)

            if not verify_password(old_pw, users[current_user.id]['password_hash']):
                flash('Current password incorrect.', 'error')
            elif new_pw != confirm:
                flash('New passwords do not match.', 'error')
            elif len(new_pw) < 4:
                flash('Password too short (min 4 chars).', 'error')
            else:
                users[current_user.id]['password_hash'] = hash_password(new_pw)
                with open(users_path, 'w') as f:
                    json.dump(users, f, indent=2)
                flash('Password changed.', 'success')

        elif action == 'add_user':
            if not current_user.has_role('admin'):
                flash('Admin access required.', 'error')
            else:
                users_path = current_app.config['USERS_PATH']
                users = load_users(users_path)
                uname = request.form.get('new_username','').strip().lower()
                pw    = request.form.get('new_password','')
                role  = request.form.get('new_role', 'viewer')
                if not uname or not pw:
                    flash('Username and password required.', 'error')
                elif uname in users:
                    flash(f'User "{uname}" already exists.', 'error')
                else:
                    users[uname] = {'password_hash': hash_password(pw), 'role': role}
                    save_users(users_path, users)
                    flash(f'User "{uname}" added as {role}.', 'success')

        elif action == 'delete_user':
            if not current_user.has_role('admin'):
                flash('Admin access required.', 'error')
            else:
                users_path = current_app.config['USERS_PATH']
                users = load_users(users_path)
                uname = request.form.get('target_user','')
                if uname == current_user.id:
                    flash('Cannot delete your own account.', 'error')
                elif uname not in users:
                    flash('User not found.', 'error')
                elif (sum(1 for u in users.values() if u.get('role')=='admin') < 2
                      and users[uname].get('role') == 'admin'):
                    flash('Cannot delete the last admin account.', 'error')
                else:
                    del users[uname]
                    save_users(users_path, users)
                    flash(f'User "{uname}" deleted.', 'success')

        elif action == 'change_role':
            if not current_user.has_role('admin'):
                flash('Admin access required.', 'error')
            else:
                users_path = current_app.config['USERS_PATH']
                users = load_users(users_path)
                uname   = request.form.get('target_user','')
                new_role = request.form.get('new_role', 'viewer')
                if uname == current_user.id:
                    flash('Cannot change your own role.', 'error')
                elif uname not in users:
                    flash('User not found.', 'error')
                elif (sum(1 for u in users.values() if u.get('role')=='admin') < 2
                      and users[uname].get('role') == 'admin' and new_role != 'admin'):
                    flash('Cannot demote the last admin.', 'error')
                else:
                    users[uname]['role'] = new_role
                    save_users(users_path, users)
                    flash(f'Role for "{uname}" set to {new_role}.', 'success')

        elif action == 'reset_password':
            if not current_user.has_role('admin'):
                flash('Admin access required.', 'error')
            else:
                users_path = current_app.config['USERS_PATH']
                users = load_users(users_path)
                uname = request.form.get('target_user','')
                pw    = request.form.get('new_password','')
                if uname not in users:
                    flash('User not found.', 'error')
                elif not pw:
                    flash('Password cannot be empty.', 'error')
                else:
                    users[uname]['password_hash'] = hash_password(pw)
                    save_users(users_path, users)
                    flash(f'Password reset for "{uname}".', 'success')

        elif action == 'regenerate_api_key':
            if not current_user.has_role('admin'):
                flash('Admin access required.', 'error')
            else:
                import secrets as _sec
                full = _load_full(current_app.config['USERS_PATH'])
                full['api_key'] = _sec.token_urlsafe(32)
                _save_full(current_app.config['USERS_PATH'], full)
                flash('API key regenerated.', 'success')

        elif action == 'save_panel':
            import json as _json
            cfg_path = current_app.config.get('CONFIG_PATH', 'config/panel.json')
            try:
                new_cfg = {
                    'gpio_mapping':        request.form.get('gpio_mapping', 'regular'),
                    'rows':                int(request.form.get('rows', 64)),
                    'cols':                int(request.form.get('cols', 128)),
                    'chain':               int(request.form.get('chain', 2)),
                    'parallel':            int(request.form.get('parallel', 2)),
                    'slowdown_gpio':       int(request.form.get('slowdown_gpio', 4)),
                    'pwm_bits':            int(request.form.get('pwm_bits', 7)),
                    'pwm_lsb_nanoseconds': int(request.form.get('pwm_lsb_nanoseconds', 50)),
                    'pwm_dither_bits':     int(request.form.get('pwm_dither_bits', 1)),
                    'display_width':       int(request.form.get('display_width', 256)),
                    'display_height':      int(request.form.get('display_height', 128)),
                    'brightness':          int(request.form.get('brightness_panel', 80)),
                    'scan_mode':           int(request.form.get('scan_mode', 0)),
                    'row_addr_type':       int(request.form.get('row_addr_type', 0)),
                    'multiplexing':        int(request.form.get('multiplexing', 0)),
                    'rgb_sequence':        request.form.get('rgb_sequence', 'RGB'),
                    'panel_type':          request.form.get('panel_type', ''),
                    'pixel_mapper':        request.form.get('pixel_mapper', ''),
                    'limit_refresh':       int(request.form.get('limit_refresh', 0)),
                    'disable_hardware_pulsing': request.form.get('disable_hardware_pulsing') == '1',
                    'show_refresh_rate':   request.form.get('show_refresh_rate') == '1',
                }
                os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
                with open(cfg_path, 'w') as f:
                    _json.dump(new_cfg, f, indent=2)
                engine.set_brightness(new_cfg['brightness'])
                engine.cfg.update(new_cfg)
                flash('Panel config saved. Restart daemon for hardware changes to take effect.', 'success')
            except Exception as e:
                flash(f'Failed to save panel config: {e}', 'error')

        return redirect(url_for('main.settings'))

    from signage.web.api import _get_api_key
    users_path = current_app.config['USERS_PATH']
    users = load_users(users_path)
    return render_template('settings.html',
                           brightness=engine.cfg.get('brightness', 80),
                           panel_cfg=engine.cfg,
                           api_key=_get_api_key(),
                           users=users)


# ---------------------------------------------------------------------------
# Playlist blueprint
# ---------------------------------------------------------------------------
playlist_bp = Blueprint('playlist', __name__)


@playlist_bp.route('/')
@login_required
def index():
    playlist = current_app.config['PLAYLIST']
    transitions = sorted(TRANSITION_REGISTRY.keys())
    media_dir = current_app.config['MEDIA_DIR']

    # List available media files
    media_files = []
    if os.path.isdir(media_dir):
        for fn in sorted(os.listdir(media_dir)):
            if '.matrix.' in fn or fn.startswith('.'):
                continue
            if allowed_file(fn):
                media_files.append({'name': fn, 'type': file_type(fn)})

    return render_template('playlist.html',
                           items=playlist.get_all(),
                           transitions=transitions,
                           media_files=media_files,
                           media_dir=media_dir,
                           valid_types=sorted(VALID_TYPES))


@playlist_bp.route('/add', methods=['POST'])
@login_required
@require_role('editor')
def add():
    playlist = current_app.config['PLAYLIST']
    data     = request.form.to_dict()

    # Convert numeric fields
    for field in ('duration', 'font_size', 'scroll_speed'):
        if field in data:
            try:
                data[field] = int(data[field])
            except ValueError:
                pass

    # Parse color fields — accept hex strings from <input type=color>
    for field in ('color', 'bg_color', 'date_color', 'number_color',
                  'label_color', 'prefix_color', 'suffix_color', 'finished_color'):
        if field in data and isinstance(data[field], str):
            try:
                hex_c = data[field].lstrip('#')
                data[field] = [int(hex_c[i:i+2], 16) for i in (0, 2, 4)]
            except Exception:
                data.pop(field, None)

    # Build lines for text items
    if data.get('type') == 'text':
        lines_text   = request.form.getlist('line_text')
        lines_color  = request.form.getlist('line_color')
        lines_size   = request.form.getlist('line_size')
        lines_align  = request.form.getlist('line_align')
        lines = []
        for i, txt in enumerate(lines_text):
            if not txt.strip():
                continue
            color = [255, 255, 255]
            try:
                hc    = (lines_color[i] if i < len(lines_color) else '#ffffff').lstrip('#')
                color = [int(hc[j:j+2], 16) for j in (0, 2, 4)]
            except Exception:
                pass
            lines.append({
                'text':      txt,
                'color':     color,
                'font_size': int(lines_size[i]) if i < len(lines_size) else 20,
                'align':     lines_align[i] if i < len(lines_align) else 'center'
            })
        data['lines'] = lines

    # Attach file path for media items
    if data.get('type') in ('image', 'gif', 'video'):
        fname = data.pop('media_file', '')
        if fname:
            data['file'] = os.path.join(current_app.config['MEDIA_DIR'], fname)

    item = playlist.add_item(data)
    current_app.config['ENGINE'].reload_playlist()
    # Redirect to edit page so all type-specific fields are available
    return redirect(url_for('playlist.edit', item_id=item['id']))


@playlist_bp.route('/delete/<item_id>', methods=['POST'])
@login_required
@require_role('editor')
def delete(item_id):
    playlist = current_app.config['PLAYLIST']
    if playlist.delete_item(item_id):
        current_app.config['ENGINE'].reload_playlist()
        flash('Item deleted.', 'success')
    else:
        flash('Item not found.', 'error')
    return redirect(url_for('playlist.index'))


@playlist_bp.route('/move/<item_id>/<direction>', methods=['POST'])
@login_required
@require_role('editor')
def move(item_id, direction):
    playlist = current_app.config['PLAYLIST']
    playlist.move_item(item_id, direction)
    return redirect(url_for('playlist.index'))


@playlist_bp.route('/duplicate/<item_id>', methods=['POST'])
@login_required
@require_role('editor')
def duplicate(item_id):
    playlist = current_app.config['PLAYLIST']
    playlist.duplicate_item(item_id)
    return redirect(url_for('playlist.index'))


@playlist_bp.route('/reorder', methods=['POST'])
@login_required
@require_role('editor')
def reorder():
    playlist    = current_app.config['PLAYLIST']
    ordered_ids = request.json.get('ids', [])
    if playlist.reorder(ordered_ids):
        current_app.config['ENGINE'].reload_playlist()
        return jsonify({'ok': True})
    return jsonify({'ok': False}), 400


@playlist_bp.route('/edit/<item_id>', methods=['GET', 'POST'])
@login_required
def edit(item_id):
    playlist    = current_app.config['PLAYLIST']
    transitions = sorted(TRANSITION_REGISTRY.keys())
    item        = playlist.get_item(item_id)

    if item is None:
        flash('Item not found.', 'error')
        return redirect(url_for('playlist.index'))

    if request.method == 'POST':
        updates = request.form.to_dict()
        for field in ('duration', 'font_size', 'scroll_speed'):
            if field in updates:
                try:
                    updates[field] = int(updates[field])
                except ValueError:
                    pass
        for field in ('color', 'bg_color', 'date_color'):
            if field in updates:
                try:
                    hc = updates[field].lstrip('#')
                    updates[field] = [int(hc[i:i+2], 16) for i in (0, 2, 4)]
                except Exception:
                    updates.pop(field, None)

        if updates.get('type') == 'text':
            lines_text     = request.form.getlist('line_text')
            lines_color    = request.form.getlist('line_color')
            lines_size     = request.form.getlist('line_size')
            lines_align    = request.form.getlist('line_align')
            lines_font     = request.form.getlist('line_font')
            lines_pos      = request.form.getlist('line_position')
            lines_scroll   = request.form.getlist('line_scroll')
            lines_speed    = request.form.getlist('line_scroll_speed')
            lines_loopct   = request.form.getlist('line_loop_count')
            # Checkboxes: collect sentinels (always present) paired with
            # checkbox values. A sentinel marks each line's position;
            # the checkbox only appears if checked.
            raw_form   = request.form.to_dict(flat=False)
            wrap_sents = raw_form.get('line_wrap_sentinel', [])
            wrap_vals  = raw_form.get('line_wrap', [])
            pixel_sents= raw_form.get('line_pixel_sentinel', [])
            pixel_vals = raw_form.get('line_pixel_font', [])
            # Build positional booleans from sentinel count
            lines_wrap  = []
            lines_pixel = []
            wi = pi = 0
            for si in range(len(wrap_sents)):
                # Each sentinel corresponds to one line
                # checkbox value appears after its sentinel if checked
                lines_wrap.append(wi < len(wrap_vals) and wrap_vals[wi] == '1')
                if wi < len(wrap_vals): wi += 1
            for si in range(len(pixel_sents)):
                lines_pixel.append(pi < len(pixel_vals) and pixel_vals[pi] == '1')
                if pi < len(pixel_vals): pi += 1
            lines = []
            for i, txt in enumerate(lines_text):
                if not txt.strip():
                    continue
                color = [255, 255, 255]
                try:
                    hc    = (lines_color[i] if i < len(lines_color) else '#ffffff').lstrip('#')
                    color = [int(hc[j:j+2], 16) for j in (0, 2, 4)]
                except Exception:
                    pass
                line = {
                    'text':         txt,
                    'color':        color,
                    'font_size':    int(lines_size[i]) if i < len(lines_size) else 16,
                    'align':        lines_align[i] if i < len(lines_align) else 'center',
                    'font':         lines_font[i] if i < len(lines_font) else 'FreeSans.ttf',
                    'scroll':       lines_scroll[i] if i < len(lines_scroll) else '',
                    'scroll_speed': float(lines_speed[i]) if i < len(lines_speed) and lines_speed[i].strip() else 2.0,
                    'wrap':         lines_wrap[i] if i < len(lines_wrap) else True,
                    'pixel_font':   lines_pixel[i] if i < len(lines_pixel) else False,
                    'loop_count':   int(lines_loopct[i]) if i < len(lines_loopct) and lines_loopct[i].strip() else 0,
                }
                pos = lines_pos[i] if i < len(lines_pos) else ''
                if pos:
                    line['position'] = pos
                lines.append(line)
            updates['lines'] = lines

        # Countdown format_parts come as a list of checkbox values
        if item.get('type') == 'countdown' or updates.get('type') == 'countdown':
            fp = request.form.getlist('format_parts')
            if fp:
                updates['format_parts'] = fp

        # Boolean fields for weather / countdown
        for field in ('show_humidity', 'show_wind', 'show_labels'):
            if field in updates:
                updates[field] = updates[field] in ('1', 'true', 'True', True)

        # Handle auto duration
        if updates.get('duration_auto') in ('1', 1, True):
            updates['duration'] = 'auto'
        elif 'duration' in updates:
            try:
                updates['duration'] = int(updates['duration'])
            except (ValueError, TypeError):
                updates['duration'] = 10
        updates.pop('duration_auto', None)

        # Float fields
        # loop_count for video items
        if 'loop_count' in updates:
            try: updates['loop_count'] = int(updates['loop_count'])
            except: updates['loop_count'] = 0

        # Weather font sizes — remove if blank (use auto)
        for fkey in ('font_size_big', 'font_size_med', 'font_size_sm'):
            if fkey in updates:
                val = str(updates[fkey]).strip()
                if val:
                    try: updates[fkey] = int(val)
                    except: del updates[fkey]
                else:
                    del updates[fkey]

        for field in ('wipe_in_speed', 'wipe_out_speed', 'fps_override',
                      'scale_factor', 'kb_zoom_start', 'kb_zoom_end',
                      'bg_dim', 'bg_scale_factor', 'bg_offset_x', 'bg_offset_y'):
            if field in updates:
                try:
                    updates[field] = float(updates[field])
                except ValueError:
                    updates[field] = 1.0

        # Keep start_offset as raw string (timecode format preserved)
        # The renderer will parse it via timecode.parse_timecode()

        # Boolean fields
        for field in ('scroll', 'loop', 'blink_separator', 'prebuffer', 'ken_burns', 'v_center'):
            if field in updates:
                updates[field] = updates[field] in ('1', 'true', 'True', True)

        # scale_mode replaces old 'scale' key
        if 'scale_mode' in updates:
            updates['scale'] = updates['scale_mode']

        # Resolve video file to transcoded version if available
        if 'file' in updates and updates['file']:
            from signage.transcoder import resolve_video_path
            updates['file'] = resolve_video_path(updates['file'])

        # Convert all hex color strings to [R,G,B] lists
        for _cf in ('bg_color', 'color', 'date_color', 'number_color',
                    'label_color', 'prefix_color', 'suffix_color', 'finished_color'):
            if _cf in updates and isinstance(updates[_cf], str):
                try:
                    hc = updates[_cf].lstrip('#')
                    updates[_cf] = [int(hc[i:i+2], 16) for i in (0, 2, 4)]
                except Exception:
                    updates.pop(_cf, None)

        playlist.update_item(item_id, updates)
        current_app.config['ENGINE'].reload_playlist()
        flash('Item updated.', 'success')
        return redirect(url_for('playlist.index'))

    media_dir  = current_app.config['MEDIA_DIR']
    media_files = []
    if os.path.isdir(media_dir):
        for fn in sorted(os.listdir(media_dir)):
            if '.matrix.' not in fn and allowed_file(fn):
                media_files.append({'name': fn, 'type': file_type(fn)})
    return render_template('edit_item.html',
                           item=item,
                           transitions=transitions,
                           media_files=media_files,
                           media_dir=media_dir)


# ---------------------------------------------------------------------------
# Files blueprint
# ---------------------------------------------------------------------------
files_bp = Blueprint('files', __name__)


@files_bp.route('/')
@login_required
def index():
    from signage.transcoder import matrix_path, is_transcoded
    media_dir = current_app.config['MEDIA_DIR']
    engine    = current_app.config['ENGINE']
    w = engine.cfg.get('display_width',  256)
    h = engine.cfg.get('display_height', 128)
    files = []
    if os.path.isdir(media_dir):
        for fn in sorted(os.listdir(media_dir)):
            # Hide transcoded .matrix.* files — they're internal
            if '.matrix.' in fn:
                continue
            if allowed_file(fn):
                path = os.path.join(media_dir, fn)
                size = os.path.getsize(path)
                ftype = file_type(fn)
                entry = {
                    'name':     fn,
                    'type':     ftype,
                    'size':     size,
                    'size_str': _human_size(size)
                }
                # For videos, show transcode status
                if ftype == 'video':
                    mp = matrix_path(path)
                    entry['transcoded']  = is_transcoded(path)
                    entry['processing']  = (
                        os.path.exists(mp + '.tmp.mp4') or
                        (os.path.exists(mp) and not is_transcoded(path))
                    )
                files.append(entry)
    return render_template('files.html', files=files,
                           display_width=w, display_height=h)


@files_bp.route('/upload', methods=['POST'])
@login_required
@require_role('editor')
def upload():
    media_dir = current_app.config['MEDIA_DIR']
    os.makedirs(media_dir, exist_ok=True)

    from signage.transcoder import (transcode_async, needs_transcode,
                                      matrix_path)
    engine   = current_app.config['ENGINE']
    w        = engine.cfg.get('display_width',  256)
    h        = engine.cfg.get('display_height', 128)
    uploaded = request.files.getlist('files')
    count    = 0
    queued   = 0
    for f in uploaded:
        if f and f.filename and allowed_file(f.filename):
            filename = secure_filename(f.filename)
            # Reject internal .matrix. files from being uploaded directly
            if '.matrix.' in filename:
                continue
            dest = os.path.join(media_dir, filename)
            f.save(dest)
            count += 1
            log.info(f"Uploaded: {filename}")
            # Generate thumbnail in background thread
            import threading as _t
            from signage.thumbnailer import generate as _gen_thumb
            _t.Thread(target=_gen_thumb, args=(media_dir, filename),
                      daemon=True, name=f'Thumb-{filename}').start()
            # Auto-transcode videos in background
            if file_type(filename) == 'video' and needs_transcode(dest, w, h):
                def _done(success, out, fn=filename):
                    if success:
                        log.info(f"Auto-transcode complete: {fn}")
                    else:
                        log.error(f"Auto-transcode failed: {fn}")
                transcode_async(dest, w, h, on_complete=_done)
                queued += 1
                log.info(f"Auto-transcode queued: {filename}")

    msg = f'{count} file(s) uploaded.'
    if queued:
        msg += (f' {queued} video(s) queued for optimisation '
                f'(shown with ⏳ in the file list).')
    flash(msg, 'success')
    return redirect(url_for('files.index'))


@files_bp.route('/delete/<filename>', methods=['POST'])
@login_required
@require_role('editor')
def delete(filename):
    from signage.transcoder import matrix_path
    media_dir = current_app.config['MEDIA_DIR']
    filename  = secure_filename(filename)
    path      = os.path.join(media_dir, filename)
    if os.path.exists(path):
        os.remove(path)
        log.info(f"Deleted media: {filename}")
        # Also delete the optimised matrix version if it exists
        mp = matrix_path(path)
        if os.path.exists(mp):
            os.remove(mp)
            log.info(f"Deleted matrix version: {os.path.basename(mp)}")
        # And any incomplete tmp file
        tmp = mp + '.tmp.mp4'
        if os.path.exists(tmp):
            os.remove(tmp)
        # Delete thumbnail
        from signage.thumbnailer import thumb_path as _tp
        tp = _tp(media_dir, filename)
        if os.path.exists(tp):
            os.remove(tp)
        # Delete any bg cache files for this image
        base = os.path.splitext(path)[0]
        import glob
        for cache_f in glob.glob(base + '.bgcache_*.jpg'):
            try:
                os.remove(cache_f)
            except Exception:
                pass
        flash(f'Deleted: {filename}', 'success')
    else:
        flash('File not found.', 'error')
    return redirect(url_for('files.index'))


@files_bp.route('/serve/<filename>')
@login_required
def serve(filename):
    media_dir = current_app.config['MEDIA_DIR']
    return send_from_directory(media_dir, filename)


@files_bp.route('/thumb/<filename>')
@login_required
def thumb(filename):
    """Serve a thumbnail, generating it on demand if missing."""
    from signage.thumbnailer import (thumb_path, thumb_exists,
                                     generate, thumb_dir)
    media_dir = current_app.config['MEDIA_DIR']
    filename  = secure_filename(filename)

    if not thumb_exists(media_dir, filename):
        generate(media_dir, filename)

    tp = thumb_path(media_dir, filename)
    if os.path.exists(tp):
        return send_from_directory(thumb_dir(media_dir),
                                   os.path.basename(tp))
    # Return a tiny placeholder if generation failed
    from flask import Response
    # 1x1 dark grey JPEG
    import base64
    grey_jpg = base64.b64decode(
        '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkS'
        'Ew8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAAR'
        'CAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAA'
        'AAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/EABQRAQAAAAAA'
        'AAAAAAAAAAAAAP/aAAwDAQACEQMRAD8AJQAB/9k='
    )
    return Response(grey_jpg, mimetype='image/jpeg')


@files_bp.route('/transcode/<filename>', methods=['POST'])
@login_required
def transcode_video(filename):
    """Start background transcode of a video to display resolution."""
    from signage.transcoder import (transcode_async, matrix_path,
                                    is_transcoded, needs_transcode)
    media_dir = current_app.config['MEDIA_DIR']
    engine    = current_app.config['ENGINE']
    filename  = secure_filename(filename)
    path      = os.path.join(media_dir, filename)

    if not os.path.exists(path):
        return jsonify({'ok': False, 'message': 'File not found'}), 404

    w = engine.cfg.get('display_width',  256)
    h = engine.cfg.get('display_height', 128)

    if is_transcoded(path):
        mp   = matrix_path(path)
        size = os.path.getsize(mp) // 1024
        return jsonify({'ok': True,
                        'message': f'Already transcoded ({size}KB)',
                        'already_done': True})

    def on_complete(success, out_path):
        if success:
            log.info(f"Transcode done: {out_path}")
        else:
            log.error(f"Transcode failed for {path}")

    transcode_async(path, w, h, on_complete=on_complete)
    return jsonify({'ok': True,
                    'message': f'Transcoding to {w}×{h} in background...'})


@files_bp.route('/transcode_status/<filename>')
@login_required
def transcode_status(filename):
    """Check if a transcoded version exists."""
    from signage.transcoder import matrix_path, is_transcoded
    media_dir = current_app.config['MEDIA_DIR']
    filename  = secure_filename(filename)
    path      = os.path.join(media_dir, filename)
    mp        = matrix_path(path)
    done      = is_transcoded(path)
    size      = os.path.getsize(mp) // 1024 if done else 0
    return jsonify({'done': done, 'size_kb': size,
                    'matrix_file': os.path.basename(mp) if done else None})


# ---------------------------------------------------------------------------
# Control blueprint (AJAX endpoints for live control + MJPEG preview)
# ---------------------------------------------------------------------------
control_bp = Blueprint('control', __name__)

import io
import time as _time

def _jpeg_frame(engine, scale: int = 3) -> bytes:
    """
    Grab the current frame from the engine and encode as JPEG.
    scale: integer upscale factor so the preview is not tiny
           (256x128 * 3 = 768x384 — fits nicely on a dashboard)
    """
    from PIL import Image as PILImage
    frame = engine.get_current_frame()          # numpy (H, W, 3)
    img   = PILImage.fromarray(frame, 'RGB')
    # Upscale with nearest-neighbour to preserve LED pixel look
    w, h  = img.size
    img   = img.resize((w * scale, h * scale), PILImage.NEAREST)
    buf   = io.BytesIO()
    img.save(buf, format='JPEG', quality=75, optimize=False)
    return buf.getvalue()


@control_bp.route('/skip', methods=['POST'])
@login_required
def skip():
    current_app.config['ENGINE'].skip()
    return jsonify({'ok': True})


@control_bp.route('/pause', methods=['POST'])
@login_required
def pause():
    current_app.config['ENGINE'].pause()
    return jsonify({'ok': True})


@control_bp.route('/prev', methods=['POST'])
@login_required
def prev():
    """Go back one item in the playlist."""
    playlist = current_app.config['PLAYLIST']
    engine   = current_app.config['ENGINE']
    # Step back two positions — engine will advance by one on next tick
    with playlist._lock:
        n = len(playlist._items)
        if n > 0:
            playlist._index = (playlist._index - 2) % n
    engine.skip()
    return jsonify({'ok': True})


@control_bp.route('/restart_item', methods=['POST'])
@login_required
def restart_item():
    """Restart the current playlist item from the beginning."""
    playlist = current_app.config['PLAYLIST']
    engine   = current_app.config['ENGINE']
    with playlist._lock:
        n = len(playlist._items)
        if n > 0:
            playlist._index = (playlist._index - 1) % n
    engine.skip()
    return jsonify({'ok': True})


@control_bp.route('/brightness', methods=['POST'])
@login_required
def brightness():
    pct = int(request.json.get('value', 80))
    current_app.config['ENGINE'].set_brightness(pct)
    return jsonify({'ok': True, 'brightness': pct})


@control_bp.route('/status')
@login_required
def status():
    return jsonify(current_app.config['ENGINE'].get_status())


@control_bp.route('/screentest', methods=['POST'])
@login_required
def screentest():
    from signage.screentest import ScreenTester
    engine = current_app.config['ENGINE']
    if not hasattr(current_app, '_screentester'):
        current_app._screentester = ScreenTester(engine)
    data     = request.get_json() or {}
    t_type   = data.get('type', 'solid')
    param    = data.get('param', '#ffffff')
    duration = int(data.get('duration', 10))
    current_app._screentester.run(t_type, param, duration)
    return jsonify({'ok': True})


@control_bp.route('/screentest/stop', methods=['POST'])
@login_required
def screentest_stop():
    if hasattr(current_app, '_screentester'):
        current_app._screentester.stop()
    return jsonify({'ok': True})


@control_bp.route('/restart_daemon', methods=['POST'])
@login_required
def restart_daemon():
    """Restart the led-signage systemd service."""
    import subprocess
    try:
        subprocess.Popen(['systemctl', 'restart', 'led-signage'])
        return jsonify({'ok': True, 'message': 'Daemon restarting...'})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@control_bp.route('/poweroff', methods=['POST'])
@login_required
@require_admin
def poweroff():
    """Shut down the Raspberry Pi."""
    import subprocess
    try:
        subprocess.Popen(['shutdown', '-h', 'now'])
        return jsonify({'ok': True, 'message': 'System shutting down...'})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@control_bp.route('/reboot', methods=['POST'])
@login_required
@require_admin
def reboot():
    """Reboot the Raspberry Pi."""
    import subprocess
    try:
        subprocess.Popen(['reboot'])
        return jsonify({'ok': True, 'message': 'System rebooting...'})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@control_bp.route('/stream')
@login_required
def stream():
    """
    MJPEG stream of the current matrix output.
    Streams at ~10fps — low enough to be light on CPU,
    high enough to see transitions and video playing.
    Query params:
      fps=N    : target frame rate (1-30, default 10)
      scale=N  : pixel upscale factor (1-6, default 3)
    """
    from flask import Response, stream_with_context

    engine = current_app.config['ENGINE']
    fps    = min(30, max(1, int(request.args.get('fps',   10))))
    scale  = min(6,  max(1, int(request.args.get('scale',  3))))
    delay  = 1.0 / fps

    def generate():
        while True:
            try:
                jpeg = _jpeg_frame(engine, scale)
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' +
                    jpeg +
                    b'\r\n'
                )
            except Exception:
                pass
            _time.sleep(delay)

    return Response(
        stream_with_context(generate()),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'X-Accel-Buffering': 'no'   # tell nginx not to buffer the stream
        }
    )


@control_bp.route('/snapshot')
@login_required
def snapshot():
    """Single JPEG snapshot — for thumbnail use."""
    scale = min(6, max(1, int(request.args.get('scale', 3))))
    jpeg  = _jpeg_frame(current_app.config['ENGINE'], scale)
    return current_app.response_class(
        response=jpeg,
        mimetype='image/jpeg',
        headers={'Cache-Control': 'no-cache'}
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _human_size(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
# Schedule blueprint
# ---------------------------------------------------------------------------
schedule_bp = Blueprint('schedule', __name__)


@schedule_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    scheduler = current_app.config['SCHEDULER']

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'save':
            # Rebuild rules from form
            enabled  = request.form.get('enabled') == '1'
            timezone = request.form.get('timezone', 'Europe/Amsterdam')

            # Parse rules — each rule is a group of fields named rule_N_*
            rules    = []
            n        = 0
            while True:
                prefix = f'rule_{n}_'
                if f'{prefix}time' not in request.form:
                    break
                time_val   = request.form.get(f'{prefix}time', '08:00')
                action_val = request.form.get(f'{prefix}action', 'on')
                brightness = request.form.get(f'{prefix}brightness', '30')
                days_raw   = request.form.getlist(f'{prefix}days')
                days       = [int(d) for d in days_raw if d.isdigit()]

                rule = {
                    'time':   time_val,
                    'action': action_val,
                    'days':   days if days else list(range(7))
                }
                if action_val == 'dim':
                    try:
                        rule['brightness'] = int(brightness)
                    except ValueError:
                        rule['brightness'] = 30
                rules.append(rule)
                n += 1

            cfg = {'enabled': enabled, 'timezone': timezone, 'rules': rules}
            scheduler.update_config(cfg)
            flash('Schedule saved.', 'success')

        elif action == 'add_rule':
            pass   # handled client-side

        return redirect(url_for('schedule.index'))

    cfg = scheduler.get_config()
    return render_template('schedule.html', cfg=cfg,
                           day_names=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'])


@schedule_bp.route('/delete_rule/<int:idx>', methods=['POST'])
@login_required
def delete_rule(idx):
    scheduler = current_app.config['SCHEDULER']
    cfg       = scheduler.get_config()
    rules     = cfg.get('rules', [])
    if 0 <= idx < len(rules):
        rules.pop(idx)
        cfg['rules'] = rules
        scheduler.update_config(cfg)
        flash('Rule deleted.', 'success')
    return redirect(url_for('schedule.index'))


@main_bp.route('/api/fonts')
@login_required
def api_fonts():
    from signage.renderer.text import list_available_fonts
    return jsonify(list_available_fonts())


@main_bp.route('/api/video_info')
@login_required
def api_video_info():
    """Return FPS and recommended settings for a media file."""
    filename = request.args.get('file', '')
    if not filename:
        return jsonify({'error': 'no file specified'}), 400

    media_dir = current_app.config['MEDIA_DIR']
    path      = os.path.join(media_dir, os.path.basename(filename))
    if not os.path.isfile(path):
        return jsonify({'error': 'file not found'}), 404

    try:
        import av
        container = av.open(path)
        stream    = container.streams.video[0]
        fps       = float(stream.average_rate or 25.0)
        duration  = float(container.duration or 0) / 1_000_000
        w         = stream.width
        h         = stream.height
        container.close()

        # Recommended limit_refresh: smallest multiple of fps >= 80Hz
        # Returns 0 if we can't find a good value (leave at no-limit)
        recommended_refresh = 0
        for mult in range(2, 12):
            candidate = round(fps * mult)
            if candidate >= 80:
                recommended_refresh = candidate
                break

        # RAM for pre-buffer
        display_w  = current_app.config['ENGINE'].width
        display_h  = current_app.config['ENGINE'].height
        n_frames   = int(duration * fps)
        ram_mb     = n_frames * display_w * display_h * 3 / 1_048_576

        return jsonify({
            'fps':                fps,
            'duration_seconds':   round(duration, 2),
            'source_resolution':  f'{w}×{h}',
            'recommended_limit_refresh': recommended_refresh,
            'prebuffer_ram_mb':   round(ram_mb, 1),
            'prebuffer_feasible': ram_mb < 300,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Playlist import / export
# ---------------------------------------------------------------------------

@playlist_bp.route('/export')
@login_required
def export_playlist():
    """Download playlist.json."""
    import io
    playlist = current_app.config['PLAYLIST']
    data     = json.dumps(playlist.get_all(), indent=2).encode('utf-8')
    return current_app.response_class(
        response=data,
        status=200,
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=playlist.json'}
    )


@playlist_bp.route('/export_with_media')
@login_required
def export_with_media():
    """Download a zip containing playlist.json + all referenced media files."""
    import io
    import zipfile
    playlist  = current_app.config['PLAYLIST']
    items     = playlist.get_all()
    buf       = io.BytesIO()

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('playlist.json', json.dumps(items, indent=2))
        seen = set()
        for item in items:
            fpath = item.get('file', '')
            if fpath and os.path.isfile(fpath) and fpath not in seen:
                seen.add(fpath)
                zf.write(fpath, os.path.join('media', os.path.basename(fpath)))

    buf.seek(0)
    return current_app.response_class(
        response=buf.read(),
        status=200,
        mimetype='application/zip',
        headers={'Content-Disposition': 'attachment; filename=playlist_export.zip'}
    )


@playlist_bp.route('/import', methods=['POST'])
@login_required
@require_role('editor')
def import_playlist():
    """
    Import a playlist from:
      - a raw playlist.json file, or
      - a zip produced by export_with_media (extracts media too)
    """
    import zipfile
    import io

    f = request.files.get('import_file')
    if not f or not f.filename:
        flash('No file selected.', 'error')
        return redirect(url_for('playlist.index'))

    merge     = request.form.get('import_mode') == 'merge'
    media_dir = current_app.config['MEDIA_DIR']
    os.makedirs(media_dir, exist_ok=True)

    try:
        raw = f.read()

        if f.filename.lower().endswith('.zip'):
            # Extract zip
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                # Extract media files
                for name in zf.namelist():
                    if name.startswith('media/') and not name.endswith('/'):
                        basename = os.path.basename(name)
                        dest     = os.path.join(media_dir, basename)
                        with zf.open(name) as src, open(dest, 'wb') as dst:
                            dst.write(src.read())
                        log.info(f"Imported media: {basename}")

                # Read playlist
                with zf.open('playlist.json') as pf:
                    items = json.load(pf)

            # Fix file paths to point to local media dir
            for item in items:
                if item.get('file'):
                    item['file'] = os.path.join(
                        media_dir, os.path.basename(item['file']))

        else:
            # Plain JSON
            items = json.loads(raw.decode('utf-8'))

        # Validate basic structure
        if not isinstance(items, list):
            raise ValueError("Playlist must be a JSON array")

        playlist = current_app.config['PLAYLIST']

        if merge:
            import uuid
            for item in items:
                item['id'] = str(uuid.uuid4())   # new id to avoid clashes
                playlist.add_item(item)
            flash(f'Merged {len(items)} items into playlist.', 'success')
        else:
            # Replace
            with playlist._lock:
                playlist._items = items
                playlist._index = -1
                playlist._save()
            flash(f'Playlist replaced with {len(items)} imported items.', 'success')

        current_app.config['ENGINE'].reload_playlist()

    except Exception as e:
        log.error(f"Playlist import failed: {e}")
        flash(f'Import failed: {e}', 'error')

    return redirect(url_for('playlist.index'))


# =============================================================================
# System blueprint — health, logs, stats, backup/restore
# =============================================================================
system_bp = Blueprint('system', __name__)


# ---------------------------------------------------------------------------
# Health endpoint (no auth — for Uptime Kuma / Home Assistant / curl)
# ---------------------------------------------------------------------------
@main_bp.route('/screentest')
@login_required
@require_role('editor')
def screentest():
    return render_template('screentest.html')


@main_bp.route('/alert')
@login_required
@require_role('editor')
def alert_page():
    from signage.web.api import _get_api_key
    media_dir   = current_app.config['MEDIA_DIR']
    media_files = []
    if os.path.isdir(media_dir):
        for fn in sorted(os.listdir(media_dir)):
            if '.matrix.' in fn or fn.startswith('.'): continue
            if allowed_file(fn):
                media_files.append({'name': fn, 'type': file_type(fn)})
    return render_template('alert.html',
                           api_key=_get_api_key(),
                           media_files=media_files,
                           media_dir=media_dir)


@main_bp.route('/health')
def health():
    engine   = current_app.config['ENGINE']
    playlist = current_app.config['PLAYLIST']
    item     = engine.get_status().get('current')
    age      = time.time() - engine._last_frame_time

    if engine._pause_event.is_set():
        status = 'paused'
    elif age > 10:
        status = 'error'
    else:
        status = 'ok'

    return jsonify({
        'status':              status,
        'uptime_seconds':      round(time.time() - _daemon_start),
        'current_item':        item.get('name') if item else None,
        'current_type':        item.get('type') if item else None,
        'brightness':          engine.cfg.get('brightness', 80),
        'paused':              engine._pause_event.is_set(),
        'last_frame_age_s':    round(age, 2),
        'playlist_length':     len(playlist),
        'version':             '1.0.0'
    })


# Track daemon start time for health endpoint
import time as _time_mod
_daemon_start = _time_mod.time()


# ---------------------------------------------------------------------------
# Log viewer
# ---------------------------------------------------------------------------
@system_bp.route('/logs')
@login_required
def logs():
    return render_template('logs.html')


@system_bp.route('/logs/data')
@login_required
def logs_data():
    import subprocess
    lines = int(request.args.get('lines', 200))
    lines = min(max(lines, 10), 1000)
    try:
        result = subprocess.run(
            ['journalctl', '-u', 'led-signage', '-n', str(lines),
             '--no-pager', '--output=short-iso'],
            capture_output=True, text=True, timeout=5
        )
        raw_lines = result.stdout.strip().split('\n') if result.stdout else []
    except Exception as e:
        raw_lines = [f'Error reading logs: {e}']
    return jsonify({'lines': raw_lines})


# ---------------------------------------------------------------------------
# System statistics
# ---------------------------------------------------------------------------
@system_bp.route('/stats')
@login_required
def stats():
    return render_template('stats.html')


@system_bp.route('/stats/data')
@login_required
def stats_data():
    from signage.sysinfo import full_stats
    return jsonify(full_stats())


# ---------------------------------------------------------------------------
# Config backup & restore
# ---------------------------------------------------------------------------
@system_bp.route('/backup')
@login_required
def backup():
    import io
    import zipfile
    from pathlib import Path

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Config files
        cfg_dir = Path('config')
        if cfg_dir.is_dir():
            for f in cfg_dir.rglob('*'):
                if f.is_file():
                    zf.write(f, f'config/{f.relative_to(cfg_dir)}')
        # Media files (excluding .matrix. transcoded versions and .thumbs)
        media_dir = Path(current_app.config['MEDIA_DIR'])
        if media_dir.is_dir():
            for f in media_dir.rglob('*'):
                if f.is_file():
                    rel = f.relative_to(media_dir)
                    if '.matrix.' not in str(rel) and '.thumbs' not in str(rel):
                        zf.write(f, f'media/{rel}')

    buf.seek(0)
    from datetime import datetime
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return current_app.response_class(
        response=buf.read(),
        status=200,
        mimetype='application/zip',
        headers={'Content-Disposition':
                 f'attachment; filename=led-signage-backup-{ts}.zip'}
    )


@system_bp.route('/restore', methods=['POST'])
@login_required
@require_admin
def restore():
    import io
    import zipfile

    f = request.files.get('backup_file')
    if not f or not f.filename:
        flash('No file selected.', 'error')
        return redirect(url_for('main.settings'))

    try:
        raw = f.read()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            restored = 0
            for name in names:
                if name.startswith('config/') and not name.endswith('/'):
                    dest = name   # relative path, e.g. config/panel.json
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(name) as src, open(dest, 'wb') as dst:
                        dst.write(src.read())
                    restored += 1
                elif name.startswith('media/') and not name.endswith('/'):
                    media_dir = current_app.config['MEDIA_DIR']
                    rel  = name[len('media/'):]
                    dest = os.path.join(media_dir, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(name) as src, open(dest, 'wb') as dst:
                        dst.write(src.read())
                    restored += 1

        flash(f'Restored {restored} files. Restarting daemon to apply config.',
              'success')
        log.info(f"Backup restored: {restored} files")
        subprocess.Popen(['systemctl', 'restart', 'led-signage'])

    except Exception as e:
        log.error(f"Restore failed: {e}")
        flash(f'Restore failed: {e}', 'error')

    return redirect(url_for('main.settings'))
