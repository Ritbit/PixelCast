#!/bin/bash
# Deployment script for PixelCast LED Signage
# Supports read-only root filesystem (Raspberry Pi overlay-fs mode).
#
# Usage: ./deploy.sh [server_ip]
#
# Overlay-fs strategy:
#   The Pi may run with an overlay filesystem (raspi-config → overlay mode)
#   where the root partition is read-only and all writes go to a RAM tmpfs
#   (lost on reboot).  To persist application updates to the SD card we must
#   write to the underlying lower layer, not the overlay:
#
#   Strategy A — overlay lower-dir available (default Pi OS overlay setup):
#     /overlay/lower is a bind-mount of the real root partition (read-only).
#     We remount it rw, write files there, remount ro.
#
#   Strategy B — lower-dir not accessible (different overlay setup):
#     Detect root block device from /proc/cmdline, mount it directly at
#     /mnt/root-rw, write files there, unmount.
#
#   Strategy C — no overlay (plain read-write root):
#     Write directly to / as usual.
#
#   In all cases the service is stopped before any writes (prevents the
#   overlay's tmpfs upper layer from caching paths we are about to update
#   on the SD card) and restarted after.

set -e

SERVER="${1:-172.17.124.195}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== PixelCast Deployment ==="
echo "Server: root@$SERVER"
echo "Project: $PROJECT_DIR"
echo ""

# ── 1. Package ────────────────────────────────────────────────────────────────
echo "[1/5] Packaging application..."
cd "$PROJECT_DIR"
tar -czf led-signage.tar.gz \
  --no-xattrs \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.git' \
  --exclude='config/*' \
  --exclude='media/*' \
  signage/ daemon.py requirements.txt deployment/
echo "✓ Package created: led-signage.tar.gz"

# ── 2. Upload ─────────────────────────────────────────────────────────────────
echo "[2/5] Uploading to server..."
scp led-signage.tar.gz root@$SERVER:/tmp/led-signage.tar.gz
echo "✓ Upload complete"

# ── 3-5. Remote: stop → write to SD card → restart ───────────────────────────
echo "[3/5] Stopping service..."
ssh root@$SERVER 'systemctl stop PixelCast && echo "✓ Service stopped"'

echo "[4/5] Deploying to SD card (overlay-aware)..."
ssh root@$SERVER << 'ENDSSH'
set -e

# ── Detect write target ───────────────────────────────────────────────────────
# Debian overlayroot package mounts the real root-ro at /media/root-ro;
# some Pi OS variants use /overlay/lower — check both.
MOUNTED_TMP=""
DEPLOY_ROOT=""
OVERLAY_LOWER=""
for candidate in /media/root-ro /overlay/lower; do
    if mountpoint -q "$candidate" 2>/dev/null; then
        OVERLAY_LOWER="$candidate"
        break
    fi
done

if [ -n "$OVERLAY_LOWER" ]; then
    # Strategy A: overlay active.
    # The kernel refuses to remount a filesystem that is in use as an overlay
    # lower dir (EBUSY), so we must NOT do 'remount,ro' on OVERLAY_LOWER.
    # Instead, look up the underlying block device and mount it at a fresh
    # temp path — exactly like Strategy B, but device is from findmnt.
    ROOT_DEV=$(findmnt --noheadings --output SOURCE "$OVERLAY_LOWER" 2>/dev/null | head -1)
    if [ -b "$ROOT_DEV" ]; then
        MOUNTED_TMP="/mnt/root-rw"
        mkdir -p "$MOUNTED_TMP"
        mount -o rw "$ROOT_DEV" "$MOUNTED_TMP"
        DEPLOY_ROOT="$MOUNTED_TMP"
        echo "  Overlay mode (Strategy A) — mounted $ROOT_DEV → $MOUNTED_TMP"
    else
        echo "  ⚠ Overlay at $OVERLAY_LOWER but device not found — falling through to Strategy B"
    fi
fi

if [ -z "$DEPLOY_ROOT" ]; then
    # Strategy B: no overlay lower-dir found (or device lookup failed above).
    # Detect root block device from /proc/cmdline and mount directly.
    ROOT_SPEC=$(grep -oP 'root=\K\S+' /proc/cmdline | head -1)
    if [[ "$ROOT_SPEC" == PARTUUID=* ]]; then
        ROOT_DEV=$(blkid -l -t "PARTUUID=${ROOT_SPEC#PARTUUID=}" -o device 2>/dev/null || true)
    else
        ROOT_DEV="$ROOT_SPEC"
    fi

    if [ -b "$ROOT_DEV" ]; then
        MOUNTED_TMP="/mnt/root-rw"
        mkdir -p "$MOUNTED_TMP"
        mount -o rw "$ROOT_DEV" "$MOUNTED_TMP"
        DEPLOY_ROOT="$MOUNTED_TMP"
        echo "  Overlay mode (Strategy B) — mounted $ROOT_DEV → $MOUNTED_TMP"
    else
        # Strategy C: plain read-write root, no special handling needed
        DEPLOY_ROOT=""
        echo "  Plain filesystem (Strategy C) — writing directly"
    fi
fi

INSTALL_DIR="${DEPLOY_ROOT}/opt/PixelCast/led-signage"

# ── Extract application ───────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"
tar -xzf /tmp/led-signage.tar.gz -C "$INSTALL_DIR" --warning=no-timestamp
rm -f /tmp/led-signage.tar.gz

# Remove stale top-level files left by old bad deploys
rm -f  "${DEPLOY_ROOT}/opt/PixelCast/daemon.py" \
       "${DEPLOY_ROOT}/opt/PixelCast/requirements.txt"
rm -rf "${DEPLOY_ROOT}/opt/PixelCast/signage" \
       "${DEPLOY_ROOT}/opt/PixelCast/deployment" \
       "${DEPLOY_ROOT}/opt/PixelCast/docs"

echo "✓ Files extracted to $INSTALL_DIR"

# ── Update Nginx config on the SD card ───────────────────────────────────────
NGINX_SRC="$INSTALL_DIR/deployment/nginx/pixelcast.conf"
if [ -f "$NGINX_SRC" ]; then
    mkdir -p "${DEPLOY_ROOT}/etc/nginx/sites-available" \
             "${DEPLOY_ROOT}/etc/nginx/sites-enabled"
    cp "$NGINX_SRC" "${DEPLOY_ROOT}/etc/nginx/sites-available/PixelCast"
    # Symlink target must be the live path (as seen through the overlay)
    ln -sf /etc/nginx/sites-available/PixelCast \
           "${DEPLOY_ROOT}/etc/nginx/sites-enabled/PixelCast"
    rm -f "${DEPLOY_ROOT}/etc/nginx/sites-enabled/led-signage" \
          "${DEPLOY_ROOT}/etc/nginx/sites-enabled/default"
    echo "✓ Nginx config written to SD card"
else
    echo "⚠ Nginx config not found — skipping"
fi

# ── Remount lower layer read-only ─────────────────────────────────────────────
if [ -n "$MOUNTED_TMP" ]; then
    umount "$MOUNTED_TMP"
    echo "  Unmounted $MOUNTED_TMP"
elif [ -n "$DEPLOY_ROOT" ]; then
    mount -o remount,ro "$DEPLOY_ROOT"
    echo "  Remounted $DEPLOY_ROOT read-only"
fi

# ── Reload Nginx + start service ──────────────────────────────────────────────
nginx -t && systemctl reload nginx && echo "✓ Nginx reloaded"
ENDSSH

echo "[5/5] Starting service..."
ssh root@$SERVER 'systemctl start PixelCast && echo "✓ Service started"'

echo ""
echo "=== Deployment Complete ==="
echo "Check status: ssh root@$SERVER 'systemctl status PixelCast'"
echo "View logs:    ssh root@$SERVER 'journalctl -u PixelCast -f'"
echo ""
