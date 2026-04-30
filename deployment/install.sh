#!/bin/bash
# ==============================================================================
# PixelCast - Professional LED Matrix Signage System
# ==============================================================================
# File:        deployment/install.sh
# Version:     1.0.0
# Author:      B. van Ritbergen <bas@ritbit.com>    
# Description: Complete installation script for PixelCast on Raspberry Pi.
#              Installs system dependencies, Python packages, RGB matrix
#              library, configures systemd service, and sets up Nginx proxy.
#
# Hardware:    Raspberry Pi 4, ElectroDragon MPC1073 HUB75 HAT,
#              4x P2.5 128x64 HUB75E panels (2x2 = 256x128 total)
#
# Usage:       sudo bash deployment/install.sh
#
# Important:   Must run as root. Disables onboard audio to avoid PWM conflicts.
# ==============================================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
step() { echo -e "\n${YELLOW}>>> $1${NC}"; }

[ "$EUID" -ne 0 ] && fail "Run as root: sudo bash install.sh"

INSTALL_DIR="/opt/PixelCast"
MATRIX_DIR="$INSTALL_DIR/rpi-rgb-led-matrix"
SIGNAGE_DIR="$INSTALL_DIR/led-signage"
mkdir -p "$INSTALL_DIR" "$MATRIX_DIR" "$SIGNAGE_DIR"

# =============================================================================
step "1. System update and dependencies"
# =============================================================================
apt-get update
apt-get install -y \
    git build-essential pkg-config cmake \
    python3 python3-pip python3-dev python3-cython \
    python3-flask python3-flask-login \
    python3-pil python3-numpy \
    ffmpeg \
    libavcodec-dev libavformat-dev libswscale-dev \
    libavdevice-dev libavutil-dev \
    fonts-dejavu-core fonts-freefont-ttf \
    wget curl
log "Dependencies installed"

# =============================================================================
step "2. Disable onboard audio (conflicts with matrix PWM timing)"
# =============================================================================
CONFIG_FILE="/boot/firmware/config.txt"
[ -f "$CONFIG_FILE" ] || CONFIG_FILE="/boot/config.txt"

if ! grep -q "dtparam=audio=off" "$CONFIG_FILE"; then
    sed -i 's/^dtparam=audio=on/#dtparam=audio=on/' "$CONFIG_FILE"
    echo "dtparam=audio=off" >> "$CONFIG_FILE"
    log "Audio disabled in $CONFIG_FILE"
else
    log "Audio already disabled"
fi

BLACKLIST="/etc/modprobe.d/blacklist-audio.conf"
[ -f "$BLACKLIST" ] || { echo "blacklist snd_bcm2835" > "$BLACKLIST"; log "Audio module blacklisted"; }

# =============================================================================
step "3. Clone / update rpi-rgb-led-matrix"
# =============================================================================
if [ -d "$MATRIX_DIR" ]; then
    warn "Already exists, pulling latest..."
    git -C "$MATRIX_DIR" pull
else
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git "$MATRIX_DIR"
fi
log "rpi-rgb-led-matrix ready"

# =============================================================================
step "4. Build rpi-rgb-led-matrix"
# =============================================================================
make -C "$MATRIX_DIR/lib"
make -C "$MATRIX_DIR/examples-api-use"
make -C "$MATRIX_DIR/utils" all

# video-viewer fallback
if [ ! -f "$MATRIX_DIR/utils/video-viewer" ]; then
    warn "Building video-viewer manually..."
    cd "$MATRIX_DIR/utils"
    g++ -o video-viewer video-viewer.cc \
        -I../include ../lib/librgbmatrix.a \
        $(pkg-config --cflags --libs libavcodec libavformat libswscale libavdevice libavutil) \
        -lpthread -lm -O3 -std=c++17 && log "video-viewer built" || warn "video-viewer failed"
fi

# =============================================================================
step "5. Install Python bindings"
# =============================================================================
# pyproject.toml is in the repo ROOT (not bindings/python) and uses
# scikit-build-core + cmake + cython. Install build tool then the package.
pip3 install --break-system-packages scikit-build-core
pip3 install --break-system-packages "$MATRIX_DIR"
log "Python bindings installed"

# =============================================================================
step "6. Install Python signage dependencies"
# =============================================================================
# Flask, Flask-Login, Pillow, NumPy installed via apt above
# Flask-WTF and PyAV are not reliably available in apt — install via pip
pip3 install --break-system-packages flask-wtf av
log "Python signage packages installed"

# =============================================================================
step "7. Deploy signage system"
# =============================================================================
if [ ! -d "$SIGNAGE_DIR" ]; then
    warn "Signage dir not found at $SIGNAGE_DIR"
    warn "Copy the led-signage directory to $SIGNAGE_DIR manually"
else
    log "Signage system found at $SIGNAGE_DIR"
fi

# Create directory structure (config and media at PixelCast level, not inside led-signage)
mkdir -p "$INSTALL_DIR"/{config,media}
mkdir -p "$SIGNAGE_DIR"/{fonts,signage/web/templates,signage/web/static}

# Panel config (only if not existing)
PANEL_CFG="$INSTALL_DIR/config/panel.json"
if [ ! -f "$PANEL_CFG" ]; then
cat > "$PANEL_CFG" << 'EOF'
{
    "board_type": "electrodragon-rpi4",
    "gpio_mapping": "regular",
    "rows": 64,
    "cols": 128,
    "chain": 2,
    "parallel": 2,
    "slowdown_gpio": 4,
    "pwm_bits": 7,
    "pwm_lsb_nanoseconds": 50,
    "pwm_dither_bits": 1,
    "display_width": 256,
    "display_height": 128,
    "brightness": 80
}
EOF
    log "Panel config written"
fi

# =============================================================================
step "8. Install systemd service"
# =============================================================================
SERVICE_SRC="$SIGNAGE_DIR/deployment/systemd/led-signage.service"
SERVICE_DST="/etc/systemd/system/led-signage.service"

if [ -f "$SERVICE_SRC" ]; then
    # Generate random secret key for Flask session security
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    
    # Copy service file and replace placeholder with actual secret
    cp "$SERVICE_SRC" "$SERVICE_DST"
    sed -i "s/CHANGE_THIS_TO_A_RANDOM_SECRET_KEY/$SECRET_KEY/" "$SERVICE_DST"
    
    systemctl daemon-reload
    systemctl enable led-signage
    log "Systemd service installed and enabled with generated secret key"
else
    warn "Service file not found at $SERVICE_SRC — skipping systemd setup"
fi

# =============================================================================
echo ""
echo "============================================================"
echo " Installation complete!"
echo "============================================================"
echo ""
echo " Quick hardware test:"
echo "  sudo $MATRIX_DIR/examples-api-use/demo \\"
echo "    --led-gpio-mapping=regular --led-rows=64 --led-cols=128 \\"
echo "    --led-chain=2 --led-parallel=2 --led-slowdown-gpio=4 \\"
echo "    --led-pwm-bits=7 --led-pwm-lsb-nanoseconds=50 \\"
echo "    --led-pwm-dither-bits=1 -D0"
echo ""
echo " Start signage daemon:"
echo "  sudo python3 $SIGNAGE_DIR/daemon.py"
echo ""
echo " Or via systemd:"
echo "  sudo systemctl start led-signage"
echo "  sudo systemctl status led-signage"
echo ""
echo " Web UI: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo " IMPORTANT: On first access, you will be prompted to create"
echo " an admin account. Please choose a strong password."
echo ""
echo " NOTE: Reboot recommended to apply audio disable."
echo "============================================================"
