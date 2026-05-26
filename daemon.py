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

#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        daemon.py                                                       ║
║ Version:     1.1.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Main daemon entry point - initializes and coordinates all       ║
║              system components including matrix engine, web UI, scheduler,   ║
║              watchdog, and alert manager.                                    ║
║                                                                              ║
║ Important:   Must run as root for GPIO access. Starts all subsystems as      ║
║              daemon threads and waits for shutdown signal.                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import signal
import logging
import threading
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signage.matrix import MatrixEngine
from signage.playlist import PlaylistManager
from signage.scheduler import Scheduler
from signage.watchdog import Watchdog
from signage.alert import AlertManager
from signage.web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('daemon')

engine:    MatrixEngine = None
scheduler: Scheduler   = None
shutdown_event = threading.Event()


def signal_handler(sig, frame):
    log.info("Shutdown signal received")
    shutdown_event.set()
    if scheduler:
        scheduler.stop()
    if engine:
        engine.stop()
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description='LED Matrix Signage Daemon')
    parser.add_argument('--config',    default='config/panel.json')
    parser.add_argument('--playlist',  default='config/playlist.json')
    parser.add_argument('--schedule',  default='config/schedule.json')
    parser.add_argument('--users',     default='config/users.json')
    parser.add_argument('--media-dir', default='media')
    parser.add_argument('--port',      type=int, default=5000)
    parser.add_argument('--host',      default='0.0.0.0')
    parser.add_argument('--no-web',    action='store_true')
    parser.add_argument('--debug',     action='store_true')
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if os.geteuid() != 0:
        log.error("Must run as root: sudo python3 daemon.py")
        sys.exit(1)

    try:
        os.nice(-10)
        log.info("Daemon process priority raised (nice -10)")
    except OSError as e:
        log.warning(f"Could not raise process priority: {e}")

    signal.signal(signal.SIGINT,  signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log.info("=== LED Signage Daemon starting ===")

    # Generate missing thumbnails for any pre-existing media files
    import threading as _t
    from signage.thumbnailer import generate_all_missing as _gen_thumbs
    _t.Thread(
        target=_gen_thumbs,
        args=(args.media_dir,),
        daemon=True,
        name='ThumbStartup'
    ).start()

    playlist = PlaylistManager(
        playlist_path=args.playlist,
        media_dir=args.media_dir
    )

    global engine, scheduler
    watchdog: Watchdog = None
    engine = MatrixEngine(config_path=args.config, playlist=playlist)

    engine_thread = threading.Thread(
        target=engine.run, name='MatrixEngine', daemon=True)
    engine_thread.start()
    log.info("Matrix engine started")

    scheduler = Scheduler(config_path=args.schedule, engine=engine)
    scheduler.start()

    # Watchdog — restarts daemon if engine freezes
    watchdog_timeout = engine.cfg.get('watchdog_timeout', 30)
    watchdog = Watchdog(engine, timeout_s=watchdog_timeout)
    watchdog.start()

    # Alert manager — high-priority overlay
    alert_mgr = AlertManager(engine)
    engine.set_alert_manager(alert_mgr)

    if not args.no_web:
        app = create_app(
            engine=engine,
            playlist=playlist,
            scheduler=scheduler,
            media_dir=args.media_dir,
            users_path=args.users,
            alert_manager=alert_mgr
        )
        web_thread = threading.Thread(
            target=lambda: app.run(
                host=args.host, port=args.port,
                debug=False, use_reloader=False
            ),
            name='WebUI', daemon=True
        )
        web_thread.start()
        log.info(f"Web UI started on http://{args.host}:{args.port}")

    log.info("Daemon running. Ctrl+C or SIGTERM to stop.")
    shutdown_event.wait()


if __name__ == '__main__':
    main()
