# PixelCast Deployment

This directory contains all files needed for deploying PixelCast to a Raspberry Pi.

## Quick Start

```bash
# On your Raspberry Pi, run:
sudo bash deployment/install.sh
```

## Directory Structure

```
deployment/
├── install.sh              # Main installation script
├── systemd/
│   └── led-signage.service # Systemd service unit file
└── nginx/
    └── pixelcast.conf      # Nginx reverse proxy configuration
```

## Installation Script

The `install.sh` script performs the following:

1. **System Dependencies** - Installs required packages (Python, ffmpeg, build tools, fonts)
2. **Audio Disable** - Disables onboard audio to prevent PWM conflicts with LED matrix
3. **RGB Matrix Library** - Clones and builds hzeller/rpi-rgb-led-matrix
4. **Python Bindings** - Installs Python bindings for the RGB matrix library
5. **Python Packages** - Installs Flask, Pillow, NumPy, PyAV
6. **Directory Setup** - Creates media/, fonts/, config/ directories
7. **Panel Config** - Generates default panel.json configuration
8. **Systemd Service** - Installs and enables the led-signage service

### Requirements

- Raspberry Pi 4 (or compatible)
- Fresh Raspberry Pi OS installation
- Root access
- Internet connection

### Usage

```bash
# From the project root on your Raspberry Pi:
sudo bash deployment/install.sh
```

After installation:
```bash
# Start the service
sudo systemctl start led-signage

# Check status
sudo systemctl status led-signage

# View logs
sudo journalctl -u led-signage -f
```

## Systemd Service

The service file (`systemd/led-signage.service`) configures:
- Runs as root (required for GPIO access)
- Auto-restart on failure
- Starts after network is available
- Working directory: `/root/led-signage`

## Nginx Configuration

The `nginx/pixelcast.conf` file provides:
- Reverse proxy from port 80 to Flask (port 5000)
- WebSocket support for real-time updates
- Static file serving
- Proper headers and timeouts

### Installing Nginx Config

```bash
sudo cp deployment/nginx/pixelcast.conf /etc/nginx/sites-available/pixelcast
sudo ln -s /etc/nginx/sites-available/pixelcast /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Hardware Configuration

Default configuration for:
- **Panels**: 4x P2.5 128x64 HUB75E panels (2x2 grid)
- **Resolution**: 256x128 pixels total
- **HAT**: ElectroDragon MPC1073 HUB75 HAT
- **GPIO Mapping**: regular
- **PWM Settings**: Optimized for flicker-free display

Edit `config/panel.json` after installation to customize.

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u led-signage -n 50

# Test manually
sudo python3 /root/led-signage/daemon.py
```

### Display issues
```bash
# Test hardware with demo
sudo /root/rpi-rgb-led-matrix/examples-api-use/demo \
  --led-gpio-mapping=regular --led-rows=64 --led-cols=128 \
  --led-chain=2 --led-parallel=2 --led-slowdown-gpio=4
```

### Audio conflicts
Ensure audio is disabled in `/boot/firmware/config.txt` (or `/boot/config.txt`):
```
dtparam=audio=off
```

Reboot after changing.

## Updating

To update an existing installation:

```bash
# Stop the service
sudo systemctl stop led-signage

# Pull latest code
cd /root/led-signage
git pull

# Restart service
sudo systemctl start led-signage
```

## Uninstall

```bash
# Stop and disable service
sudo systemctl stop led-signage
sudo systemctl disable led-signage

# Remove service file
sudo rm /etc/systemd/system/led-signage.service
sudo systemctl daemon-reload

# Remove installation (optional)
sudo rm -rf /root/led-signage
sudo rm -rf /root/rpi-rgb-led-matrix
```
