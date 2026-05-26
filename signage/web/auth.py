"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/web/auth.py                                             ║
║ Version:     1.0.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Authentication and role-based access control using Flask-Login. ║
║              Three roles: viewer (read-only), editor (read/write), admin     ║
║              (full access). SHA-256 password hashing.                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import json
import hashlib
import logging
import functools

from flask import redirect, url_for, request, abort, flash
from flask_login import (LoginManager, UserMixin,
                         login_required, current_user)

log = logging.getLogger('web.auth')

ROLE_LEVEL = {'viewer': 0, 'editor': 1, 'admin': 2}

# No default users - first-run setup required


class User(UserMixin):
    def __init__(self, username, data):
        self.id       = username
        self.username = username
        self.role     = data.get('role', 'viewer')

    def has_role(self, required: str) -> bool:
        return ROLE_LEVEL.get(self.role, 0) >= ROLE_LEVEL.get(required, 0)


_DEFAULT_USER = 'admin'
_DEFAULT_PASS = 'admin'


def load_users(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path) as f:
                raw = json.load(f)
            # Return only user records (skip api_key and other top-level keys)
            return {k: v for k, v in raw.items()
                    if isinstance(v, dict) and 'password_hash' in v}
        except Exception as e:
            log.error(f'Failed to load users: {e}')
    else:
        # Seed default credentials so the system is immediately accessible
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        default = {_DEFAULT_USER: {'password_hash': hash_password(_DEFAULT_PASS), 'role': 'admin'}}
        try:
            with open(path, 'w') as f:
                json.dump(default, f, indent=2)
            log.warning('No users file found — created default admin/admin account. '
                        'Change the password via Settings after logging in!')
        except Exception as e:
            log.error(f'Failed to write default users: {e}')
        return default
    return {}


def _load_full(path: str) -> dict:
    """Load the entire users.json including api_key and other metadata."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_full(path: str, data: dict):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def save_users(path: str, users: dict):
    """Merge user records back into the full file preserving api_key etc."""
    full = _load_full(path)
    # Remove old user keys that are dicts with password_hash
    for k in list(full.keys()):
        if isinstance(full[k], dict) and 'password_hash' in full[k]:
            del full[k]
    full.update(users)
    _save_full(path, full)


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def verify_password(pw: str, hashed: str) -> bool:
    return hash_password(pw) == hashed


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def require_role(role: str):
    """Decorator: require at least `role` level. Must come after @login_required."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('main.login', next=request.url))
            if not current_user.has_role(role):
                flash(f'You need {role} access for this.', 'error')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def require_admin(f):
    return login_required(require_role('admin')(f))


def require_editor(f):
    return login_required(require_role('editor')(f))


# ---------------------------------------------------------------------------
# Flask-Login setup
# ---------------------------------------------------------------------------

def init_auth(app, users_path: str):
    lm = LoginManager()
    lm.init_app(app)
    lm.login_view    = 'main.login'

    @lm.user_loader
    def load_user(user_id):
        users = load_users(users_path)
        if user_id in users:
            return User(user_id, users[user_id])
        return None

    app.login_manager = lm
