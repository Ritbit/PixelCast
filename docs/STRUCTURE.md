# PixelCast Project Structure

**Last Updated**: April 28, 2026

This document describes the project structure with clean separation between code and data.

## Development Structure (Repository)

```
pixelcast/
├── daemon.py                       # Main entry point
├── requirements.txt                # Python dependencies
├── deploy.sh                       # Deployment script
├── README.md                       # Main project documentation
├── .gitignore                      # Git ignore patterns
│
├── docs/                           # 📚 Documentation
│   ├── README.md                   # Documentation index
│   ├── DOCUMENTATION_GUIDE.md      # Code documentation standards
│   ├── FEATURES.md                 # Feature list and roadmap
│   └── STRUCTURE.md                # This file
│
├── deployment/                     # 🚀 Deployment & Installation
│   ├── README.md                   # Deployment guide
│   ├── install.sh                  # Main installation script
│   ├── systemd/
│   │   └── PixelCast.service       # Systemd service unit
│   └── nginx/
│       └── pixelcast.conf          # Nginx reverse proxy config
│
└── signage/                        # 🐍 Python Package
    ├── __init__.py                 # Package initialization
    ├── matrix.py                   # LED matrix display engine
    ├── playlist.py                 # Playlist management
    ├── scheduler.py                # Time-based scheduling
    ├── alert.py                    # Alert overlay system
    ├── watchdog.py                 # Health monitoring
    ├── transcoder.py               # Video transcoding
    ├── thumbnailer.py              # Thumbnail generation
    ├── timecode.py                 # Timecode parsing utilities
    ├── screentest.py               # Screen test patterns
    ├── sysinfo.py                  # System information
    │
    ├── renderer/                   # Content Renderers
    │   ├── __init__.py             # Renderer factory
    │   ├── base.py                 # Base renderer class
    │   ├── image.py                # Image/GIF renderer
    │   ├── video.py                # Video renderer
    │   ├── text.py                 # Text renderer
    │   ├── clock.py                # Clock renderer
    │   ├── weather.py              # Weather renderer
    │   ├── countdown.py            # Countdown renderer
    │   └── utils.py                # Rendering utilities
    │
    ├── transitions/                # Transition Effects
    │   ├── __init__.py             # Transition factory
    │   └── effects.py              # 22 transition implementations
    │
    └── web/                        # Web Interface
        ├── __init__.py             # Web package init
        ├── app.py                  # Flask application factory
        ├── auth.py                 # Authentication & RBAC
        ├── api.py                  # REST API blueprint
        ├── routes.py               # Web UI routes
        ├── filters.py              # Jinja2 template filters
        ├── templates/              # HTML templates
        └── static/                 # Static assets (CSS, JS, brand)
            └── brand/              # Brand assets (logos, favicons)
```

## Production Structure (Deployed)

```
/opt/PixelCast/
├── led-signage/                    # 📦 Application Code (replaceable)
│   ├── daemon.py
│   ├── requirements.txt
│   ├── deployment/
│   └── signage/
│       └── web/
│           └── static/
│               └── brand/          # Brand assets served by Nginx
│
├── config/                         # ⚙️ Configuration (persistent)
│   ├── panel.json                  # Hardware configuration
│   ├── playlist.json               # Content playlist
│   ├── schedule.json               # Scheduling rules
│   └── users.json                  # User credentials & API keys
│
├── media/                          # 🎨 Media Files (persistent)
│   ├── *.mp4                       # User-uploaded videos
│   ├── *.jpg                       # User-uploaded images
│   ├── *.matrix.mp4                # Transcoded videos
│   ├── .thumbs/                    # Generated thumbnails
│   └── weather-icons/              # Weather icons (optional)
│
└── rpi-rgb-led-matrix/             # 🔌 HUB75 Driver Library
    ├── lib/
    ├── bindings/python/
    └── utils/
```

## Design Principles

### 1. Code/Data Separation (Production)
In production (`/opt/PixelCast`), code and data are completely separated:
- **Application code** (`led-signage/`) - Can be replaced during updates
- **Configuration** (`config/`) - Persistent, survives updates
- **Media files** (`media/`) - Persistent, survives updates
- **Relative paths** - Playlist uses `media/video.mp4`, not absolute paths

**Benefits:**
- Clean updates without touching user data
- Easy backups (just backup `config/` and `media/`)
- No path fixing needed after updates
- Clear separation of concerns

### 2. Separation of Concerns (Development)
- **Source code** (`signage/`) - Python package
- **Documentation** (`docs/`) - All project documentation
- **Deployment** (`deployment/`) - Installation and configuration
- **Static assets** (`signage/web/static/brand/`) - Brand assets served by Nginx

### 3. Clear Entry Points
- `daemon.py` - Main application entry point
- `deployment/install.sh` - Installation entry point
- `deploy.sh` - Deployment script for updates

### 4. Git-Friendly
- Runtime data excluded via .gitignore
- Brand assets included in repo at `signage/web/static/brand/`
- Config templates can be versioned
- Clear separation of code vs. data

## Key Paths Reference

### Production Paths
| Component     | Path                                             | Purpose                    |
|---------------|--------------------------------------------------|----------------------------|
| Application   | `/opt/PixelCast/led-signage/`                    | Replaceable code           |
| Config        | `/opt/PixelCast/config/`                         | Persistent configuration   |
| Media         | `/opt/PixelCast/media/`                          | Persistent media files     |
| Matrix Library| `/opt/PixelCast/rpi-rgb-led-matrix/`             | HUB75 driver               |
| Static Assets | `/opt/PixelCast/led-signage/signage/web/static/` | Served by Nginx            |

### Deployment
- **Install**: `sudo bash deployment/install.sh`
- **Update**: `./deploy.sh` (from development machine)
- **Service**: `sudo systemctl {start|stop|restart|status} led-signage`
- **Logs**: `journalctl -u led-signage -f`

## Benefits

1. **Clean Updates** - Replace code without touching config/media
2. **Easy Backups** - Backup `/opt/PixelCast/{config,media}` separately
3. **Professional Structure** - Follows industry best practices
4. **Easy Navigation** - Clear where to find specific file types
5. **CI/CD Ready** - Clear separation makes automation easier
6. **Scalable** - Easy to add new components in logical places

## Deployment Workflow

### Initial Installation
```bash
# On Raspberry Pi
sudo bash deployment/install.sh
```

### Updates
```bash
# From development machine
./deploy.sh

# This deploys to /opt/PixelCast/led-signage
# Config and media at /opt/PixelCast level are preserved
```

## Maintenance

When adding new files:

1. **Documentation** → `docs/`
2. **Deployment/Install** → `deployment/`
3. **Source Code** → `signage/` (appropriate submodule)
4. **Static Assets** → `signage/web/static/`
5. **Brand Assets** → `signage/web/static/brand/`

Keep the root directory clean - only essential entry points and standard files (README, requirements, deploy.sh, etc.) belong there.
