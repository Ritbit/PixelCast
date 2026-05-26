#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# PixelCast — Copyright (C) 2026 Bas van Ritbergen
#
# init-usb-data.sh — Seed USB storage with default config and bundled media
# on first boot (or whenever files are missing).
# Called by PixelCast.service as ExecStartPre (failure is non-fatal).

SYSTEM_DIR="/opt/PixelCast/led-signage"
USB_MOUNT="/media/usb"

if ! mountpoint -q "$USB_MOUNT"; then
    echo "[usb-init] USB not mounted — skipping data initialisation"
    exit 0
fi

# Directory structure
mkdir -p "$USB_MOUNT/config"
mkdir -p "$USB_MOUNT/media/weather-icons"
mkdir -p "$USB_MOUNT/cache"

# ── Bundled media ──────────────────────────────────────────────────────────
# Copy any image/gif files that ship with PixelCast to the USB media folder
# (only if they are not already present — never overwrites user files).
BUNDLED="$SYSTEM_DIR/media"
if [ -d "$BUNDLED" ]; then
    for f in "$BUNDLED"/*.png "$BUNDLED"/*.jpg "$BUNDLED"/*.jpeg "$BUNDLED"/*.gif; do
        [ -f "$f" ] || continue
        bn=$(basename "$f")
        if [ ! -f "$USB_MOUNT/media/$bn" ]; then
            cp "$f" "$USB_MOUNT/media/$bn" \
                && echo "[usb-init] Copied bundled media: $bn"
        fi
    done
fi

# ── Default playlist ───────────────────────────────────────────────────────
# Only written on first boot (when no playlist exists on the USB).
DEFAULT_PL="$SYSTEM_DIR/deployment/defaults/playlist.json"
if [ ! -f "$USB_MOUNT/config/playlist.json" ] && [ -f "$DEFAULT_PL" ]; then
    cp "$DEFAULT_PL" "$USB_MOUNT/config/playlist.json" \
        && echo "[usb-init] Created default playlist on USB"
fi

echo "[usb-init] USB data ready at $USB_MOUNT"
exit 0
