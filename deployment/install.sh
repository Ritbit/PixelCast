#!/bin/bash
# ==============================================================================
# PixelCast - Professional LED Matrix Signage System
# ==============================================================================
# File:        deployment/install.sh
# Version:     1.3.1
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
# Pre-configure initramfs before installing packages so postinst hooks work correctly.
# MODULES=most: mkinitramfs skips root device detection (fails on PARTUUID-based Pi roots).
# overlay: must be in the initramfs so overlayroot activates on boot with the RT kernel.
if grep -q '^MODULES=' /etc/initramfs-tools/initramfs.conf 2>/dev/null; then
    sed -i 's/^MODULES=.*/MODULES=most/' /etc/initramfs-tools/initramfs.conf
else
    echo 'MODULES=most' >> /etc/initramfs-tools/initramfs.conf
fi
grep -qx 'overlay' /etc/initramfs-tools/modules 2>/dev/null || echo 'overlay' >> /etc/initramfs-tools/modules
log "initramfs pre-configured (MODULES=most, overlay module)"

apt-get update
apt-get install -y \
    git build-essential pkg-config cmake \
    python3 python3-pip python3-dev cython3 \
    python3-flask python3-flask-login \
    python3-pil python3-numpy \
    ffmpeg \
    libavcodec-dev libavformat-dev libswscale-dev \
    libavdevice-dev libavutil-dev \
    fonts-dejavu-core fonts-freefont-ttf \
    wget curl nginx \
    lm-sensors \
    rsync \
    openssh-server \
    avahi-daemon libnss-mdns \
    overlayroot \
    linux-image-rt-arm64 \
    chrony
log "Dependencies installed"

# chrony: replace any existing makestep directive with 'makestep 1 -1'
# so the clock is stepped immediately on first NTP sync regardless of offset.
# Pi 4 has no hardware RTC; without this the clock can be weeks off after reboot.
sed -i '/^makestep /d' /etc/chrony/chrony.conf
echo 'makestep 1 -1' >> /etc/chrony/chrony.conf
log "chrony configured (makestep 1 -1)"

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
if [ -d "$MATRIX_DIR/.git" ]; then
    warn "Already exists, pulling latest..."
    git -C "$MATRIX_DIR" pull
else
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git "$MATRIX_DIR"
fi

# Apply Pi 5 / RP1 support patch (PR #1886 — not yet merged in main branch)
# Fetch the PR branch and cherry-pick the single Pi5 commit
git -C "$MATRIX_DIR" fetch origin pull/1886/head:pr-pi5-fix 2>/dev/null || warn "Could not fetch PR #1886 (offline?)"
if git -C "$MATRIX_DIR" cat-file -e pr-pi5-fix 2>/dev/null; then
    ALREADY=$(git -C "$MATRIX_DIR" log --oneline | grep -c "Raspberry Pi5" || true)
    if [ "$ALREADY" -eq 0 ]; then
        git -C "$MATRIX_DIR" \
            -c user.email="install@localhost" -c user.name="Installer" \
            cherry-pick pr-pi5-fix && log "Pi 5 patch applied" || warn "Pi 5 patch failed — may already be applied"
    else
        log "Pi 5 patch already applied"
    fi
fi
log "rpi-rgb-led-matrix ready"

# =============================================================================
step "4. Build rpi-rgb-led-matrix"
# =============================================================================
make -C "$MATRIX_DIR/lib"
make -C "$MATRIX_DIR/examples-api-use"
# utils/ skipped — led-image-viewer needs GraphicsMagick (not installed) and
# video-viewer is unused; PixelCast uses PyAV for all video rendering.

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
if [ ! -f "$SIGNAGE_DIR/daemon.py" ]; then
    warn "Signage source not found at $SIGNAGE_DIR"
    warn "Copy the source tree with:"
    warn "  cp -r /path/to/pixelcast/. $SIGNAGE_DIR/"
    warn "Note: use trailing /. to copy contents, not the folder itself"
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
step "8. Enable mDNS (avahi) for .local hostname access"
# =============================================================================
systemctl enable --now avahi-daemon
log "Avahi mDNS daemon enabled — device reachable as $(hostname).local"

# =============================================================================
step "9. Install systemd service"
# =============================================================================
SERVICE_SRC="$SIGNAGE_DIR/deployment/systemd/PixelCast.service"
SERVICE_DST="/etc/systemd/system/PixelCast.service"

if [ -f "$SERVICE_SRC" ]; then
    # Generate random secret key for Flask session security
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    
    # Copy service file and replace placeholder with actual secret
    cp "$SERVICE_SRC" "$SERVICE_DST"
    sed -i "s/CHANGE_THIS_TO_A_RANDOM_SECRET_KEY/$SECRET_KEY/" "$SERVICE_DST"
    
    systemctl daemon-reload
    systemctl enable PixelCast
    log "Systemd service installed and enabled with generated secret key"
else
    warn "Service file not found at $SERVICE_SRC — skipping systemd setup"
fi

# =============================================================================
step "10. SD card protection — overlay filesystem"
# =============================================================================
# Configures the root filesystem as read-only with a tmpfs overlay so that
# normal runtime writes (logs, tmp files) go to RAM and are discarded on
# reboot.  Application updates are written through the overlay via deploy.sh.
#
# Three things are needed that raspi-config alone does NOT do:
#   1. overlayroot=tmpfs in cmdline.txt          (raspi-config does this)
#   2. /etc/overlayroot.local.conf               (overrides package default)
#   3. 'overlay' listed in initramfs-tools/modules so modules.dep is correct

CMDLINE="/boot/firmware/cmdline.txt"
[ -f "$CMDLINE" ] || CMDLINE="/boot/cmdline.txt"

# 1. Ensure overlayroot=tmpfs is in cmdline.txt
if ! grep -q 'overlayroot=tmpfs' "$CMDLINE"; then
    # Prepend so it is read early by the initramfs
    sed -i 's/^/overlayroot=tmpfs /' "$CMDLINE"
    log "overlayroot=tmpfs added to $CMDLINE"
else
    log "overlayroot=tmpfs already in $CMDLINE"
fi

# 2. Create overlayroot.local.conf (takes precedence over package-managed conf)
if [ ! -f /etc/overlayroot.local.conf ]; then
    echo 'overlayroot="tmpfs"' > /etc/overlayroot.local.conf
    log "Created /etc/overlayroot.local.conf"
else
    log "/etc/overlayroot.local.conf already exists"
fi

# 3. Ensure the overlay kernel module is indexed in the initramfs modules.dep
if ! grep -qx 'overlay' /etc/initramfs-tools/modules 2>/dev/null; then
    echo 'overlay' >> /etc/initramfs-tools/modules
    log "overlay module added to /etc/initramfs-tools/modules"
else
    log "overlay module already in /etc/initramfs-tools/modules"
fi

# Rebuild initramfs with all three changes baked in
update-initramfs -u
log "Initramfs rebuilt — overlay will activate on next reboot"

# =============================================================================
step "11. RT kernel boot setup"
# =============================================================================
# The Debian RT kernel postinst (z50-raspi-firmware) skips Pi firmware setup
# for non-Pi kernels — copy vmlinuz + initrd manually and point config.txt at them.
# iomem=relaxed: rpi-rgb-led-matrix mmaps /dev/mem for GPIO register access;
# the RT kernel has CONFIG_STRICT_DEVMEM enabled which blocks this without it.

RT_KERNEL=$(ls /boot/vmlinuz-*-rt-arm64 2>/dev/null | sort -V | tail -1)
RT_INITRD=$(ls /boot/initrd.img-*-rt-arm64 2>/dev/null | sort -V | tail -1)

if [ -z "$RT_KERNEL" ] || [ -z "$RT_INITRD" ]; then
    warn "RT kernel or initrd not found in /boot — skipping firmware copy"
else
    RT_NAME=$(basename "$RT_KERNEL" | sed 's/vmlinuz-//')
    cp "$RT_KERNEL" /boot/firmware/vmlinuz-rt
    cp "$RT_INITRD" /boot/firmware/initrd.img-rt
    log "RT kernel copied to /boot/firmware ($RT_NAME)"

    if ! grep -q 'kernel=vmlinuz-rt' "$CONFIG_FILE"; then
        printf '\n[all]\nkernel=vmlinuz-rt\ninitramfs initrd.img-rt followkernel\n' >> "$CONFIG_FILE"
        log "RT kernel configured in $CONFIG_FILE"
    else
        log "RT kernel already configured in $CONFIG_FILE"
    fi
fi

if ! grep -q 'iomem=relaxed' "$CMDLINE"; then
    sed -i 's/$/ iomem=relaxed/' "$CMDLINE"
    log "iomem=relaxed added to $CMDLINE"
else
    log "iomem=relaxed already in $CMDLINE"
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
echo " Start PixelCast signage daemon:"
echo "  sudo python3 $SIGNAGE_DIR/daemon.py"
echo ""
echo " Or via systemd:"
echo "  sudo systemctl start PixelCast"
echo "  sudo systemctl status PixelCast"
echo ""
echo " Web UI: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo " IMPORTANT: On first access, you will be prompted to create"
echo " an admin account. Please choose a strong password."
echo ""
echo " NOTE: Reboot required to activate:"
echo "        - Audio disable (PWM conflict fix)"
echo "        - RT kernel (PREEMPT_RT — flicker-free LED display)"
echo "        - Overlay filesystem (read-only SD card protection)"
echo "============================================================"
