# PixelCast Deployment

This directory contains all files needed for deploying PixelCast to a Raspberry Pi.

## Quick Start

```bash
# On your Raspberry Pi, run:
sudo bash deployment/install.sh
```

## Directory Structure

```text
deployment/
├── install.sh              # Main installation script
├── systemd/
│   ├── PixelCast.service                    # Main daemon systemd unit
│   ├── PixelCast-logdiscovery.service       # mDNS log-server discovery (+ .timer)
│   ├── PixelCast-ssl-cert.service           # Ensures self-signed TLS cert exists before nginx starts
│   └── nginx-pixelcast-ssl.override.conf    # nginx.service drop-in (Requires=PixelCast-ssl-cert.service)
├── scripts/
│   ├── discover-logserver.sh               # Log-forwarding discovery logic
│   └── generate-ssl-cert.sh                # Self-signed TLS cert generation (idempotent)
├── logserver/                          # Setup for the remote log server side
└── nginx/
    └── pixelcast.conf      # Nginx reverse proxy configuration (HTTP + HTTPS)
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
8. **Systemd Service** - Installs and enables the PixelCast service

### Requirements

- Raspberry Pi 4 (or compatible, NOTE Pi 5 support is very experimental!)
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
sudo systemctl start PixelCast

# Check status
sudo systemctl status PixelCast

# View logs
sudo journalctl -u PixelCast -f
```

## Systemd Service

The service file (`systemd/PixelCast.service`) configures:

- Runs as root (required for GPIO access)
- Auto-restart on failure
- Starts after network is available
- Working directory: `/opt/PixelCast/led-signage`
- **SIGNAGE_SECRET**: Flask session secret key (auto-generated during install)

### Manual Secret Key Setup

If installing manually, generate a secret key and update the service file:

```bash
# Generate a random secret key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Edit the service file
sudo nano /etc/systemd/system/PixelCast.service

# Replace CHANGE_THIS_TO_A_RANDOM_SECRET_KEY with your generated key
# Then reload systemd
sudo systemctl daemon-reload
sudo systemctl restart PixelCast
```

## Nginx Configuration

The `nginx/pixelcast.conf` file provides:

- Reverse proxy from port 80/443 to Flask (port 5000)
- HTTPS with a self-signed certificate (port 443, alongside plain HTTP on port 80)
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

### HTTPS / Self-Signed Certificate

`ssl_certificate`/`ssl_certificate_key` in `pixelcast.conf` point at
`/etc/nginx/ssl/pixelcast.{crt,key}`. These are generated automatically by
`scripts/generate-ssl-cert.sh`, run by the `PixelCast-ssl-cert.service`
oneshot unit which is ordered before `nginx.service` via the
`nginx-pixelcast-ssl.override.conf` drop-in — so the cert always exists by
the time nginx starts.

- If a USB stick is mounted at `/media/usb`, the cert's private key material
  is stored at `/media/usb/config/ssl/` so it survives reboots (same
  fingerprint every time). Without a USB stick it's generated directly into
  `/etc/nginx/ssl/` and may be regenerated on reboot if the root overlay
  doesn't persist it — still fine, since it's only used for LAN transport
  encryption.
- Browsers will show an "untrusted certificate" warning for `https://` —
  expected for a self-signed cert. The connection is still encrypted; just
  click through the warning (or add an exception) once per browser.
- To install/refresh manually:

  ```bash
  sudo bash deployment/scripts/generate-ssl-cert.sh
  sudo cp deployment/systemd/PixelCast-ssl-cert.service /etc/systemd/system/
  sudo mkdir -p /etc/systemd/system/nginx.service.d
  sudo cp deployment/systemd/nginx-pixelcast-ssl.override.conf \
      /etc/systemd/system/nginx.service.d/pixelcast-ssl.conf
  sudo systemctl daemon-reload
  sudo systemctl enable --now PixelCast-ssl-cert.service
  sudo nginx -t && sudo systemctl reload nginx
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
sudo journalctl -u PixelCast -n 50

# Test manually
sudo python3 /opt/PixelCast/led-signage/daemon.py
```

### Display issues

```bash
# Test hardware with demo
sudo /opt/PixelCast/rpi-rgb-led-matrix/examples-api-use/demo \
  --led-gpio-mapping=regular --led-rows=64 --led-cols=128 \
  --led-chain=2 --led-parallel=2 --led-slowdown-gpio=4
```

### Audio conflicts

Ensure audio is disabled in `/boot/firmware/config.txt` (or `/boot/config.txt`):

```text
dtparam=audio=off
```

Reboot after changing.

## Updating

To update an existing installation:

```bash
# Stop the service
sudo systemctl stop PixelCast

# Pull latest code
cd /opt/PixelCast/led-signage
git pull

# Restart service
sudo systemctl start PixelCast
```

### Updating the base OS

Debian and kernel updates need a different procedure, because install.sh
(step 10) leaves the SD card read-only behind a tmpfs overlay. A plain
`sudo apt upgrade` will exhaust the RAM disk, fail with half-configured
packages, and then discard everything on the next reboot.

See [../docs/OS-UPDATES.md](../docs/OS-UPDATES.md) for the full runbook.

## Uninstall

```bash
# Stop and disable service
sudo systemctl stop PixelCast
sudo systemctl disable PixelCast

# Remove service file
sudo rm /etc/systemd/system/PixelCast.service
sudo systemctl daemon-reload

# Remove installation (optional)
sudo rm -rf /opt/PixelCast/led-signage
sudo rm -rf /opt/PixelCast/rpi-rgb-led-matrix
```
