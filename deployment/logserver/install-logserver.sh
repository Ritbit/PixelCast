#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# PixelCast — Copyright (C) 2026 Bas van Ritbergen
#
# install-logserver.sh — Turn any RHEL-based host (RHEL/CentOS/Rocky/Fedora)
# into a PixelCast-compatible log server: receives forwarded logs over
# rsyslog, advertises itself via mDNS (_pixelcast-log._tcp) so PixelCast
# devices auto-discover it, and rotates the resulting log files.
#
# Usage: sudo ./install-logserver.sh
#
# Idempotent — safe to re-run.

set -euo pipefail

step() { echo -e "\n=== $* ==="; }

if [ "$EUID" -ne 0 ]; then
    echo "Must be run as root (sudo ./install-logserver.sh)" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

step "1/5 Installing packages (rsyslog, avahi, logrotate)"
dnf install -y rsyslog avahi logrotate firewalld 2>/dev/null || \
    yum install -y rsyslog avahi logrotate firewalld

step "2/5 Configuring rsyslog to receive PixelCast logs"
install -Dm644 "$SCRIPT_DIR/10-pixelcast-remote.conf" \
    /etc/rsyslog.d/10-pixelcast-remote.conf
systemctl enable --now rsyslog
systemctl restart rsyslog

step "3/5 Opening firewall for port 514 (tcp/udp)"
if systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --add-port=514/tcp --add-port=514/udp
    firewall-cmd --reload
else
    echo "firewalld not active — skipping (open port 514 tcp/udp manually if needed)"
fi

step "4/5 Advertising this host via mDNS (_pixelcast-log._tcp)"
install -Dm644 "$SCRIPT_DIR/pixelcast-log.service" \
    /etc/avahi/services/pixelcast-log.service
systemctl enable --now avahi-daemon
systemctl restart avahi-daemon

step "5/5 Installing log rotation policy"
install -Dm644 "$SCRIPT_DIR/pixelcast-remote-logrotate.conf" \
    /etc/logrotate.d/pixelcast-remote

echo -e "\n✓ Log server ready. Logs will appear under /var/log/remote/<hostname>/*.log"
echo "  PixelCast devices on this network will auto-discover this host within ~5 minutes."
