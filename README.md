# PixelCast

<p align="center">
  <img src="media/pixelcast-logo-adaptive.svg" alt="PixelCast Logo" width="400">
</p>

<p align="center">
  <strong>Professional LED Matrix Signage System for Raspberry Pi</strong>
</p>

---

## Overview

**PixelCast** is a production-ready LED matrix signage system designed for Raspberry Pi with HUB75 LED panels. It provides a complete solution for displaying dynamic content including images, videos, text, clocks, weather information, and countdowns on LED matrix displays.

### Key Features

- 🎨 **Rich Content Types**: Images, GIF animations, videos, text, clocks, weather, countdowns
- 🎬 **Advanced Transitions**: 22 professional transition effects (fade, slide, zoom, dissolve, etc.)
- 📱 **Web Interface**: Full-featured web UI with live preview, playlist management, and system controls
- 🔐 **Role-Based Access**: Three-tier authentication (viewer, editor, admin)
- 📡 **REST API**: Complete API for external integrations
- ⏰ **Scheduling**: Time-based on/off/dim scheduling with day-of-week support
- 🚨 **Alert System**: High-priority overlay alerts with custom styling
- 🎥 **Auto-Transcoding**: Automatic video optimization for LED display
- 🔄 **Auto-Updates**: Background pre-rendering and smooth transitions

---

## Hardware Requirements

| Component | Specification |
|-----------|---------------|
| **Controller** | Raspberry Pi 4B (or compatible) |
| **HAT** | ElectroDragon MPC1073 HUB75 HAT (or compatible) |
| **LED Panels** | HUB75/HUB75E compatible panels |
| **Tested Config** | 4× P2.5 128×64 panels (2×2 arrangement = 256×128 total) |
| **Power Supply** | Dedicated 5V PSU for LED panels (NOT from Pi GPIO) |
| **OS** | Raspberry Pi OS Lite 64-bit (Bookworm/Debian 13) |
| **Python** | 3.11+ |

---

## Quick Start

### Installation

1. **Clone or download** the project to your Raspberry Pi:
   ```bash
   cd /opt/PixelCast
   git clone <repository-url> led-signage
   cd led-signage
   ```

2. **Run the installation script**:
   ```bash
   sudo bash deployment/install.sh
   ```

   This will:
   - Install system dependencies (Python, ffmpeg, Nginx)
   - Build RGB matrix library (hzeller/rpi-rgb-led-matrix)
   - Install Python packages
   - Configure systemd service with auto-generated secret key
   - Set up directory structure (`/opt/PixelCast/{config,media}`)
   - Configure hardware (disable audio to avoid PWM conflicts)

3. **Access the web interface**:
   - Open `http://<raspberry-pi-ip>` in your browser
   - Default credentials: `admin` / `admin` (change immediately!)

### Deployment & Updates

For updates from your development machine:

```bash
cd /path/to/pixelcast
./deploy.sh
```

This deploys code to `/opt/PixelCast/led-signage` while preserving config and media.

See [DEPLOY_INSTRUCTIONS.md](DEPLOY_INSTRUCTIONS.md) for detailed deployment guide.

---

## Directory Structure

### Development (Repository)
```
pixelcast/
├── daemon.py                    # Main entry point
├── requirements.txt             # Python dependencies
├── deploy.sh                    # Deployment script
├── README.md                    # This file
│
├── docs/                        # 📚 Documentation
│   ├── DOCUMENTATION_GUIDE.md   # Code documentation standards
│   ├── FEATURES.md              # Feature list and roadmap
│   └── STRUCTURE.md             # Project structure guide
│
├── deployment/                  # 🚀 Deployment files
│   ├── install.sh               # Installation script
│   ├── README.md                # Deployment guide
│   ├── systemd/
│   │   └── led-signage.service  # Systemd service file
│   └── nginx/
│       └── pixelcast.conf       # Nginx reverse proxy config
│
├── config/                      # ⚙️ Runtime configuration
│   ├── panel.json               # Hardware configuration
│   ├── playlist.json            # Content playlist
│   ├── schedule.json            # On/off/dim schedule
│   └── users.json               # User credentials
│
├── media/                       # 🎨 Media files & assets
│   ├── pixelcast-*.svg          # Branding assets
│   └── [uploaded media]         # User-uploaded content
│
├── signage/                     # 🐍 Python package
│   ├── matrix.py                # Display engine
│   ├── playlist.py              # Playlist management
│   ├── scheduler.py            # Time-based scheduling
│   ├── alert.py                # Alert system
│   ├── watchdog.py             # Health monitoring
│   ├── transcoder.py           # Video transcoding
│   ├── thumbnailer.py          # Thumbnail generation
│   ├── renderer/               # Content renderers
│   ├── transitions/            # Transition effects
│   └── web/                    # Web interface
└── fonts/                      # TTF fonts
```

---

## Content Types

### Supported Formats

- **Images**: JPG, PNG, BMP, WebP
- **Animations**: GIF
- **Video**: MP4, AVI, MOV (auto-transcoded to display resolution)
- **Text**: Multi-line with inline styling, scrolling, custom fonts
- **Clock**: Digital clock with customizable format and fonts
- **Weather**: Live weather from Open-Meteo API
- **Countdown**: Countdown/countup timers

### Transition Effects (22 types)

`fade`, `fade_black`, `wipe_left`, `wipe_right`, `wipe_up`, `wipe_down`, `slide_left`, `slide_right`, `slide_up`, `slide_down`, `zoom_in`, `zoom_out`, `dissolve`, `melt`, `snow`, `spiral`, `drop`, `blinds_h`, `blinds_v`, `checkerboard`, `pixelate`, `none`

---

## Web Interface

### Dashboard
- Live MJPEG preview of current display
- Playback controls (play/pause, skip, previous)
- Brightness control
- System status

### Playlist Manager
- Drag-and-drop reordering
- Per-item configuration
- Import/export playlists
- Duplicate items
- Date range filtering

### File Manager
- Drag-and-drop upload
- Thumbnail previews
- Auto-transcoding status
- Delete with cascade

### Schedule Editor
- Time-based on/off/dim rules
- Day-of-week selection
- Multiple rule support

### Settings
- Hardware configuration
- User management (admin only)
- API key management
- System controls (restart, reboot, power off)

---

## REST API

Base URL: `/api/v1/`

Authentication: `Authorization: Bearer <api_key>` or `?api_key=<key>`

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check (no auth) |
| GET | `/status` | Full system status |
| GET | `/playlist` | Get all playlist items |
| POST | `/playlist/item` | Add playlist item |
| PUT | `/playlist/item/<id>` | Update item |
| DELETE | `/playlist/item/<id>` | Delete item |
| POST | `/playlist/skip` | Skip to next item |
| GET/PUT | `/brightness` | Get/set brightness |
| GET | `/snapshot` | Current frame as JPEG |
| POST | `/alert` | Show priority alert |
| DELETE | `/alert` | Clear alert |

See `CLAUDE_PROJECT_CONTEXT.md` for complete API documentation.

---

## Configuration

### Panel Configuration (`config/panel.json`)

```json
{
  "rows": 64,
  "cols": 128,
  "chain": 2,
  "parallel": 2,
  "gpio_mapping": "regular",
  "slowdown": 4,
  "pwm_bits": 7,
  "pwm_lsb_nanoseconds": 50,
  "pwm_dither_bits": 1,
  "brightness": 80
}
```

### Hardware Setup Notes

**Critical**: Onboard audio MUST be disabled to avoid PWM conflicts:

```bash
# In /boot/config.txt
dtparam=audio=off

# Blacklist audio module
echo "blacklist snd_bcm2835" | sudo tee /etc/modprobe.d/blacklist-rgb-matrix.conf
```

---

## Authentication & Roles

Three role levels with ascending privileges:

| Role | View | Edit Playlist | Upload Files | Send Alerts | Settings | User Mgmt | System |
|------|------|---------------|--------------|-------------|----------|-----------|--------|
| **viewer** | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| **editor** | ✓ | ✓ | ✓ | ✓ | brightness | ✗ | ✗ |
| **admin** | ✓ | ✓ | ✓ | ✓ | full | ✓ | ✓ |

Default credentials: `admin` / `admin` — **change immediately after first login!**

---

## Development

### Running Manually

```bash
sudo python3 /opt/PixelCast/led-signage/daemon.py
```

### Watching Logs

```bash
journalctl -u led-signage -f
```

### Before Packaging

1. Compile all Python files: `python3 -m py_compile <file>.py`
2. Verify Jinja2 templates: `python3 -c "from jinja2 import Template; Template('{{1}}').render()"`
3. Clean cache: `find . -name __pycache__ -exec rm -rf {} +`
4. Package: `tar -czf led-signage.tar.gz --exclude='**/__pycache__' led-signage/`

---

## Troubleshooting

### Display Issues

- **Flickering**: Increase `slowdown` value in panel config
- **Wrong colors**: Check `gpio_mapping` (should be `regular` for MPC1073)
- **No display**: Verify power supply, check GPIO connections
- **Ghosting**: Adjust `pwm_bits` and `pwm_lsb_nanoseconds`

### Service Issues

```bash
# Check service status
sudo systemctl status led-signage

# Restart service
sudo systemctl restart led-signage

# View logs
journalctl -u led-signage -n 100
```

### Web Interface

- **502 Bad Gateway**: Service not running, check `systemctl status`
- **Login fails**: Check `config/users.json` permissions
- **Upload fails**: Check disk space and `media/` permissions

---

## Credits

- **LED Matrix Library**: [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix)
- **Weather Data**: [Open-Meteo](https://open-meteo.com/)
- **Video Processing**: FFmpeg via PyAV

---

## License

This project is provided as-is for personal and commercial use.

---

## Support

For detailed technical documentation, see `CLAUDE_PROJECT_CONTEXT.md`.

For feature requests and issues, please contact the project maintainer.

---

**PixelCast** — Professional LED Matrix Signage Made Simple
