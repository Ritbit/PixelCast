"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/web/app.py                                              ║
║ Version:     1.0.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Flask application factory - creates and configures Flask app    ║
║              with all blueprints, authentication, and filters.               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import logging
from flask import Flask
from .auth import init_auth
from .filters import register_filters

log = logging.getLogger('signage.web.app')


def create_app(engine, playlist, scheduler, media_dir, users_path, alert_manager=None) -> Flask:
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    secret_key = os.environ.get('SIGNAGE_SECRET')
    if not secret_key:
        log.error('SIGNAGE_SECRET environment variable not set!')
        log.error('Generate one with: python3 -c "import secrets; print(secrets.token_hex(32))"')
        raise RuntimeError('SIGNAGE_SECRET must be set for security. Refusing to start.')
    app.secret_key = secret_key
    app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024
    app.config['MEDIA_DIR']    = os.path.abspath(media_dir)
    app.config['USERS_PATH']   = users_path
    app.config['ENGINE']       = engine
    app.config['ALERT_MANAGER']  = alert_manager
    app.config['PLAYLIST']     = playlist
    app.config['SCHEDULER']    = scheduler
    # Store config path so settings route can save panel.json
    import inspect, os as _os
    # We infer it from engine.cfg — but simpler to just hardcode relative path
    app.config['CONFIG_PATH']  = 'config/panel.json'

    init_auth(app, users_path)
    register_filters(app)

    from .routes import main_bp, playlist_bp, files_bp, control_bp, schedule_bp, system_bp
    from .api import api_bp, _USERS_PATH as _api_users_path
    app.register_blueprint(main_bp)
    app.register_blueprint(playlist_bp, url_prefix='/playlist')
    app.register_blueprint(files_bp,    url_prefix='/files')
    app.register_blueprint(control_bp,  url_prefix='/control')
    app.register_blueprint(schedule_bp, url_prefix='/schedule')
    app.register_blueprint(system_bp,   url_prefix='/system')
    # API — load users_path into api module
    import signage.web.api as _api_mod
    _api_mod._USERS_PATH = users_path
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    register_error_handlers(app)
    log.info("Flask app created")
    return app


def register_error_handlers(app):
    from flask import render_template

    @app.errorhandler(400)
    def bad_request(e):
        return render_template('error.html', code=400,
                               message='Bad request.', detail=str(e)), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html', code=403,
                               message='Access denied.', detail=None), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html', code=404,
                               message='Page not found.', detail=None), 404

    @app.errorhandler(500)
    def server_error(e):
        import traceback
        detail = traceback.format_exc()
        log.error(f"500 error: {e}\n{detail}")
        # Only show traceback in debug mode
        show_detail = detail if app.debug else None
        return render_template('error.html', code=500,
                               message='Something went wrong on the server.',
                               detail=show_detail), 500
