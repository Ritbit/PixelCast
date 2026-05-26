#!/bin/bash
# Quick deployment script for PixelCast LED Signage
# Usage: ./deploy.sh [server_ip]

set -e

SERVER="${1:-172.17.124.195}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== PixelCast Deployment ==="
echo "Server: root@$SERVER"
echo "Project: $PROJECT_DIR"
echo ""

# Package
echo "[1/4] Packaging application..."
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

# Upload
echo "[2/4] Uploading to server..."
scp led-signage.tar.gz root@$SERVER:/root/
echo "✓ Upload complete"

# Deploy
echo "[3/5] Deploying on server..."
ssh root@$SERVER << 'EOF'
mkdir -p /opt/PixelCast/led-signage
cd /opt/PixelCast/led-signage
tar -xzf /root/led-signage.tar.gz
rm -f /root/led-signage.tar.gz
# Clean up any stray top-level files from previous bad deploys
rm -f /opt/PixelCast/daemon.py /opt/PixelCast/requirements.txt
rm -rf /opt/PixelCast/signage /opt/PixelCast/deployment /opt/PixelCast/docs
echo "✓ Files extracted to /opt/PixelCast/led-signage/"
EOF

# Update Nginx
echo "[4/5] Updating Nginx configuration..."
ssh root@$SERVER << 'EOF'
if [ -f /opt/PixelCast/led-signage/deployment/nginx/pixelcast.conf ]; then
  cp /opt/PixelCast/led-signage/deployment/nginx/pixelcast.conf /etc/nginx/sites-available/PixelCast
  ln -sf /etc/nginx/sites-available/PixelCast /etc/nginx/sites-enabled/PixelCast
  rm -f /etc/nginx/sites-enabled/led-signage /etc/nginx/sites-enabled/default
  nginx -t && systemctl reload nginx
  echo "✓ Nginx reloaded (site: PixelCast)"
else
  echo "⚠ Nginx config not found — skipping"
fi
EOF

# Restart
echo "[5/5] Restarting service..."
ssh root@$SERVER 'systemctl restart PixelCast'
echo "✓ Service restarted"

echo ""
echo "=== Deployment Complete ==="
echo "Check status: ssh root@$SERVER 'systemctl status PixelCast'"
echo "View logs:    ssh root@$SERVER 'journalctl -u PixelCast -f'"
echo ""
