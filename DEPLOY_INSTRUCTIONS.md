# PixelCast Deployment Guide

## Overview

PixelCast uses a clean separation between code and data:

```
/opt/PixelCast/
├── led-signage/     # Application code (replaced on updates)
├── config/          # Configuration (persistent)
└── media/           # Media files (persistent)
```

Updates only replace the `led-signage/` directory, preserving your config and media.

## Quick Deployment (Recommended)

Use the automated deployment script:

```bash
cd /Users/bas/Documents/Code/RitBit-led-signage
./deploy.sh
```

This will:
1. Package the application code
2. Upload to server
3. Extract to `/opt/PixelCast/led-signage`
4. Update Nginx configuration
5. Restart the service

## Manual Deployment

If you prefer manual deployment:

### From Local Machine

```bash
# 1. Package the application
cd /Users/bas/Documents/Code/RitBit-led-signage
tar -czf led-signage.tar.gz \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.git' \
  --exclude='config/*' \
  --exclude='media/*' \
  signage/ daemon.py requirements.txt deployment/

# 2. Copy to server
scp led-signage.tar.gz root@192.168.2.173:/root/

# 3. SSH to server
ssh root@192.168.2.173
```

### On the Server

```bash
# 4. Stop the service
sudo systemctl stop led-signage

# 5. Backup current installation (optional but recommended)
cd /opt/PixelCast/led-signage
tar -czf ../led-signage-backup-$(date +%Y%m%d-%H%M%S).tar.gz .

# 6. Extract new code
cd /opt/PixelCast
tar -xzf /root/led-signage.tar.gz

# 7. Update Nginx configuration
sudo cp /opt/PixelCast/led-signage/deployment/nginx/pixelcast.conf /etc/nginx/sites-available/led-signage
sudo nginx -t && sudo systemctl reload nginx

# 8. Update systemd service (if changed)
sudo cp /opt/PixelCast/led-signage/deployment/systemd/led-signage.service /etc/systemd/system/led-signage.service
sudo systemctl daemon-reload

# 9. Restart the service
sudo systemctl start led-signage

# 10. Check status
sudo systemctl status led-signage
journalctl -u led-signage -f
```

## What Gets Deployed

**Application Code** (replaced on each deployment):
- `signage/` - Python package with all modules
  - `signage/web/static/brand/` - Brand assets (logos, favicons)
  - `signage/web/templates/` - HTML templates
  - `signage/renderer/` - Content renderers
- `daemon.py` - Main daemon script
- `requirements.txt` - Python dependencies
- `deployment/` - Deployment configs (Nginx, systemd)

**Persistent Data** (never touched by deployments):
- `/opt/PixelCast/config/` - Configuration files
  - `panel.json` - Hardware configuration
  - `playlist.json` - Content playlist
  - `schedule.json` - Scheduling rules
  - `users.json` - User credentials & API keys
- `/opt/PixelCast/media/` - Media files
  - User-uploaded videos and images
  - Transcoded videos (`*.matrix.mp4`)
  - Thumbnails (`.thumbs/`)

## Directory Structure

```
/opt/PixelCast/
├── led-signage/              # Code (replaceable)
│   ├── signage/
│   ├── daemon.py
│   └── deployment/
├── config/                   # Config (persistent)
│   ├── panel.json
│   ├── playlist.json
│   ├── schedule.json
│   └── users.json
└── media/                    # Media (persistent)
    ├── *.mp4
    ├── *.jpg
    └── .thumbs/
```

## Verification

After deployment, verify everything works:

```bash
# Check service status
sudo systemctl status led-signage

# Check logs
journalctl -u led-signage -f

# Test web interface
curl -I http://localhost/

# Test static files
curl -I http://localhost/static/brand/pixelcast-icon-48.svg

# Test API (if you have an API key)
curl -H "Authorization: Bearer YOUR_API_KEY" http://localhost/api/v1/status
```

## Troubleshooting

### Service won't start
```bash
# Check logs for errors
journalctl -u led-signage -n 50

# Verify paths
ls -la /opt/PixelCast/led-signage/
ls -la /opt/PixelCast/config/
ls -la /opt/PixelCast/media/
```

### Static files not loading (403 errors)
```bash
# Check Nginx config
sudo nginx -t

# Check file permissions
sudo chmod -R 755 /opt/PixelCast/led-signage/signage/web/static/

# Reload Nginx
sudo systemctl reload nginx
```

### Playlist paths broken
If you migrated from an old installation, playlist may have absolute paths. Fix with:
```bash
sudo sed -i 's|/root/led-signage/media/|media/|g' /opt/PixelCast/config/playlist.json
sudo sed -i 's|/opt/PixelCast/led-signage/media/|media/|g' /opt/PixelCast/config/playlist.json
sudo systemctl restart led-signage
```

## Rollback

If a deployment fails, rollback to the previous version:

```bash
# Stop service
sudo systemctl stop led-signage

# Restore from backup
cd /opt/PixelCast
rm -rf led-signage
tar -xzf led-signage-backup-YYYYMMDD-HHMMSS.tar.gz -C led-signage

# Restart service
sudo systemctl start led-signage
```
