#!/bin/bash
# Quick deployment script for PixelCast LED Signage
# Usage: ./deploy.sh [server_ip]

set -e

SERVER="${1:-192.168.2.173}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== PixelCast Deployment ==="
echo "Server: root@$SERVER"
echo "Project: $PROJECT_DIR"
echo ""

# Package
echo "[1/4] Packaging application..."
cd "$PROJECT_DIR"
tar -czf led-signage.tar.gz \
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
cd /opt/PixelCast
tar -xzf /root/led-signage.tar.gz
echo "✓ Files extracted"
EOF

# Update Nginx
echo "[4/5] Updating Nginx configuration..."
ssh root@$SERVER << 'EOF'
sudo cp /opt/PixelCast/led-signage/deployment/nginx/pixelcast.conf /etc/nginx/sites-available/led-signage
sudo nginx -t && sudo systemctl reload nginx
echo "✓ Nginx reloaded"
EOF

# Restart
echo "[5/5] Restarting service..."
ssh root@$SERVER 'sudo systemctl restart led-signage'
echo "✓ Service restarted"

echo ""
echo "=== Deployment Complete ==="
echo "Check status: ssh root@$SERVER 'sudo systemctl status led-signage'"
echo "View logs:    ssh root@$SERVER 'journalctl -u led-signage -f'"
echo ""
