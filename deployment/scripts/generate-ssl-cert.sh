#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# PixelCast — Copyright (C) 2026 Bas van Ritbergen
#
# generate-ssl-cert.sh — Ensure a self-signed TLS certificate exists for the
# Nginx HTTPS listener. Idempotent: does nothing if a valid cert is already
# in place. Called by PixelCast-ssl-cert.service before nginx.service starts.
#
# Persistence strategy:
#   The device's root filesystem may be an overlay (writes lost on reboot).
#   /media/usb is a real, persistent partition, so the cert's private
#   material is generated/stored there when available and copied into
#   /etc/nginx/ssl (the stable path Nginx actually reads) on every boot.
#   Without a USB stick, the cert is generated directly into /etc/nginx/ssl
#   and will simply be regenerated on next boot if the overlay upper layer
#   doesn't persist it — still fine, since it's self-signed and only used
#   for transport encryption on the LAN.

USB_MOUNT="/media/usb"
USB_SSL_DIR="$USB_MOUNT/config/ssl"
LIVE_SSL_DIR="/etc/nginx/ssl"
CERT_NAME="pixelcast"
DAYS_VALID=3650

mkdir -p "$LIVE_SSL_DIR"

# ── Decide where the cert's source material should live ────────────────────
if mountpoint -q "$USB_MOUNT" 2>/dev/null; then
    mkdir -p "$USB_SSL_DIR"
    SRC_DIR="$USB_SSL_DIR"
else
    SRC_DIR="$LIVE_SSL_DIR"
fi

CRT="$SRC_DIR/$CERT_NAME.crt"
KEY="$SRC_DIR/$CERT_NAME.key"

# ── Generate only if missing (idempotent — keeps the same fingerprint) ─────
if [ ! -s "$CRT" ] || [ ! -s "$KEY" ]; then
    echo "[ssl-cert] No existing certificate at $SRC_DIR — generating…"

    HOST=$(hostname)
    SAN="DNS:${HOST},DNS:${HOST}.local,IP:127.0.0.1"
    for ip in $(hostname -I 2>/dev/null); do
        SAN="${SAN},IP:${ip}"
    done

    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "$KEY" -out "$CRT" \
        -days "$DAYS_VALID" \
        -subj "/CN=${HOST}" \
        -addext "subjectAltName=${SAN}" \
        2>/dev/null

    if [ -s "$CRT" ] && [ -s "$KEY" ]; then
        chmod 600 "$KEY"
        echo "[ssl-cert] Generated self-signed certificate (SAN: $SAN)"
    else
        echo "[ssl-cert] Certificate generation failed"
        exit 1
    fi
else
    echo "[ssl-cert] Existing certificate found at $SRC_DIR — reusing"
fi

# ── Mirror into the stable path Nginx points to ─────────────────────────────
if [ "$SRC_DIR" != "$LIVE_SSL_DIR" ]; then
    cp "$CRT" "$LIVE_SSL_DIR/$CERT_NAME.crt"
    cp "$KEY" "$LIVE_SSL_DIR/$CERT_NAME.key"
    chmod 600 "$LIVE_SSL_DIR/$CERT_NAME.key"
fi

echo "[ssl-cert] Ready: $LIVE_SSL_DIR/$CERT_NAME.crt"
exit 0
