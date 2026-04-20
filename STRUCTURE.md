# PixelCast Project Structure

**Last Updated**: April 20, 2026

This document describes the reorganized project structure for better maintainability and clarity.

## Directory Layout

```
pixelcast/
├── daemon.py                       # Main entry point
├── requirements.txt                # Python dependencies
├── Deploy_from_Download.sh         # Development deployment helper (kept at root)
├── README.md                       # Main project documentation
├── STRUCTURE.md                    # This file
├── .gitignore                      # Git ignore patterns
│
├── docs/                           # 📚 Documentation
│   ├── README.md                   # Documentation index
│   ├── DOCUMENTATION_GUIDE.md      # Code documentation standards
│   ├── CLAUDE_PROJECT_CONTEXT.md   # Technical reference
│   ├── CLAUDE_PROJECT_QUICKREF.md  # Quick reference notes
│   └── FEATURES.md                 # Feature list and roadmap
│
├── deployment/                     # 🚀 Deployment & Installation
│   ├── README.md                   # Deployment guide
│   ├── install.sh                  # Main installation script
│   ├── systemd/
│   │   └── led-signage.service     # Systemd service unit
│   └── nginx/
│       └── pixelcast.conf          # Nginx reverse proxy config
│
├── scripts/                        # 🔧 Utility Scripts
│   └── (future scripts)            # Development/maintenance scripts
│
├── config/                         # ⚙️ Runtime Configuration
│   ├── .gitkeep                    # Keep directory in git
│   ├── panel.json                  # Hardware configuration (runtime)
│   ├── playlist.json               # Content playlist (runtime)
│   ├── schedule.json               # Scheduling rules (runtime)
│   └── users.json                  # User credentials (runtime)
│
├── media/                          # 🎨 Media Files
│   ├── pixelcast-favicon-16.svg    # Favicon 16x16
│   ├── pixelcast-favicon-32.svg    # Favicon 32x32
│   ├── pixelcast-icon-48.svg       # Icon 48x48
│   ├── pixelcast-icon-96.svg       # Icon 96x96
│   ├── pixelcast-icon-512.svg      # Icon 512x512
│   ├── pixelcast-logo-adaptive.svg # Adaptive logo
│   ├── pixelcast-logo-light-background.svg # Logo for light backgrounds
│   ├── weather-icons/              # Custom weather icons (optional)
│   └── [uploaded-media]            # User-uploaded content (runtime)
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
        └── static/                 # Static assets (CSS, JS)
```

## Design Principles

### 1. Separation of Concerns
- **Source code** (`signage/`) - Python package
- **Documentation** (`docs/`) - All project documentation
- **Deployment** (`deployment/`) - Installation and configuration
- **Runtime data** (`config/`, `media/`) - Generated/uploaded content

### 2. Clear Entry Points
- `daemon.py` - Main application entry point (stays at root)
- `deployment/install.sh` - Installation entry point
- `Deploy_from_Download.sh` - Development workflow (kept at root for convenience)

### 3. Self-Documenting Structure
- Each major directory has a README.md
- Clear naming conventions
- Logical grouping of related files

### 4. Git-Friendly
- Runtime data excluded via .gitignore
- Branding assets included in repo
- Config templates can be versioned
- Clear separation of code vs. data

## File Locations Reference

### Before Reorganization
```
/root/led-signage/
├── install.sh                      ❌ Root clutter
├── led-signage.service             ❌ Root clutter
├── nginx-led-signage.conf          ❌ Root clutter
├── DOCUMENTATION_GUIDE.md          ❌ Root clutter
├── CLAUDE_PROJECT_CONTEXT.md       ❌ Root clutter
└── CLAUDE_Project_Features_to work on.MD  ❌ Root clutter
```

### After Reorganization
```
/root/led-signage/
├── daemon.py                       ✅ Main entry point
├── requirements.txt                ✅ Standard location
├── Deploy_from_Download.sh         ✅ Dev convenience
├── README.md                       ✅ Standard location
├── deployment/                     ✅ Organized
│   ├── install.sh
│   ├── systemd/led-signage.service
│   └── nginx/pixelcast.conf
└── docs/                           ✅ Organized
    ├── DOCUMENTATION_GUIDE.md
    ├── CLAUDE_PROJECT_CONTEXT.md
    └── FEATURES.md
```

## Benefits

1. **Professional Structure** - Follows industry best practices
2. **Easy Navigation** - Clear where to find specific file types
3. **Better Onboarding** - New developers can understand structure quickly
4. **CI/CD Ready** - Clear separation makes automation easier
5. **Scalable** - Easy to add new components in logical places

## Migration Notes

### Updated Paths

| Old Path | New Path | Notes |
|----------|----------|-------|
| `install.sh` | `deployment/install.sh` | Updated internally |
| `led-signage.service` | `deployment/systemd/led-signage.service` | Service file location |
| `nginx-led-signage.conf` | `deployment/nginx/pixelcast.conf` | Renamed for consistency |
| `DOCUMENTATION_GUIDE.md` | `docs/DOCUMENTATION_GUIDE.md` | - |
| `CLAUDE_PROJECT_CONTEXT.md` | `docs/CLAUDE_PROJECT_CONTEXT.md` | - |
| `CLAUDE_Project_Features_to work on.MD` | `docs/FEATURES.md` | Renamed |

### Installation Command

**Old**: `sudo bash install.sh`  
**New**: `sudo bash deployment/install.sh`

### Service File Reference

The install script now looks for the service file at:
```bash
$SIGNAGE_DIR/deployment/systemd/led-signage.service
```

## Future Additions

Potential future directories:

- `tests/` - Unit and integration tests
- `scripts/backup.sh` - Backup utility
- `scripts/update.sh` - Update utility
- `examples/` - Example configurations
- `tools/` - Development tools

## Maintenance

When adding new files:

1. **Documentation** → `docs/`
2. **Deployment/Install** → `deployment/`
3. **Utilities/Scripts** → `scripts/`
4. **Source Code** → `signage/` (appropriate submodule)
5. **Config Templates** → `config/` (with .example suffix)

Keep the root directory clean - only essential entry points and standard files (README, requirements, etc.) belong there.
