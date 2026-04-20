# PixelCast Deployment Checklist - Security Updates

**Version**: 1.0.0 (Post Phase-1 Security Fixes)  
**Date**: April 20, 2026

---

## ⚠️ BREAKING CHANGES

This update includes **breaking changes** that require configuration updates before deployment.

### Critical: Secret Key Required

The system will **refuse to start** without a configured secret key.

---

## 📋 Pre-Deployment Checklist

### 1. Generate Secret Key

```bash
# Generate a secure 64-character hex string
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Save this value securely - you'll need it for the next step.

### 2. Update Systemd Service

Edit `/etc/systemd/system/led-signage.service`:

```ini
[Service]
# Add this line with your generated secret
Environment="SIGNAGE_SECRET=your-64-char-hex-string-here"

# Existing configuration...
WorkingDirectory=/opt/PixelCast/led-signage
ExecStart=/usr/bin/python3 /opt/PixelCast/led-signage/daemon.py
```

### 3. Backup Current Users File

```bash
# Backup existing users (if any)
sudo cp /opt/PixelCast/led-signage/config/users.json /opt/PixelCast/led-signage/config/users.json.backup
```

### 4. Review Nginx Configuration

If using nginx, verify the updated configuration:

```bash
# Check the new config
cat /opt/PixelCast/led-signage/deployment/nginx/pixelcast.conf

# Update if needed
sudo cp /opt/PixelCast/led-signage/deployment/nginx/pixelcast.conf /etc/nginx/sites-available/led-signage
sudo nginx -t
```

---

## 🚀 Deployment Steps

### Step 1: Stop the Service

```bash
sudo systemctl stop led-signage
```

### Step 2: Pull/Deploy New Code

```bash
cd /opt/PixelCast/led-signage
git pull
# OR
# Extract from tarball, etc.
```

### Step 3: Update Systemd Service

```bash
# Edit the service file
sudo nano /etc/systemd/system/led-signage.service

# Add the Environment line with your SIGNAGE_SECRET
# Save and exit

# Reload systemd
sudo systemctl daemon-reload
```

### Step 4: Start the Service

```bash
sudo systemctl start led-signage
```

### Step 5: Check Status

```bash
# Verify it started successfully
sudo systemctl status led-signage

# Check logs for any errors
sudo journalctl -u led-signage -n 50
```

**Expected**: Service should start successfully. If it fails with "SIGNAGE_SECRET must be set", verify Step 3.

---

## 🔐 Post-Deployment: First-Run Setup

### If Users File Exists

Existing users will continue to work. However:

1. **Change all passwords** via Settings → Users
2. **Review user roles** and adjust as needed
3. **Generate new API key** if compromised

### If No Users File (Fresh Install)

1. Navigate to `http://your-pi-ip:5000`
2. You'll see the login page
3. **Create first admin account**:
   - Click "First time? Create an admin account"
   - Choose a strong username and password
   - This will be your admin account

---

## ✅ Verification Tests

### Test 1: Secret Key Enforcement

```bash
# Temporarily remove the secret key
sudo systemctl stop led-signage
sudo nano /etc/systemd/system/led-signage.service
# Comment out the Environment line
sudo systemctl daemon-reload
sudo systemctl start led-signage

# Check logs - should see error about SIGNAGE_SECRET
sudo journalctl -u led-signage -n 20

# Restore the secret key
sudo nano /etc/systemd/system/led-signage.service
# Uncomment the Environment line
sudo systemctl daemon-reload
sudo systemctl start led-signage
```

**Expected**: Service refuses to start without secret key.

### Test 2: Role-Based Access Control

1. Log in as admin
2. Create a "viewer" user via Settings → Users
3. Log out and log in as viewer
4. Try to delete a playlist item
5. **Expected**: Should see "Access denied" or similar

### Test 3: CSRF Protection

1. Open browser developer tools
2. Go to Playlist → Edit Item
3. Inspect the form
4. **Expected**: Should see `<input type="hidden" name="csrf_token" value="...">`

### Test 4: Error Handling

1. Cause a 500 error (e.g., corrupt a config file temporarily)
2. **Expected**: Error page should NOT show full traceback (unless debug mode)
3. Check logs: `sudo journalctl -u led-signage -n 20`
4. **Expected**: Full traceback should be in logs

### Test 5: API Security

```bash
# Get your API key
API_KEY=$(sudo cat /opt/PixelCast/led-signage/config/users.json | grep api_key | cut -d'"' -f4)

# Test reboot endpoint (should require admin)
curl -X POST http://localhost:5000/api/v1/system/reboot \
  -H "Authorization: Bearer $API_KEY"

# Expected: Should work with valid API key
# Without key: Should return 401 Unauthorized
```

---

## 🔧 Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u led-signage -n 50 --no-pager

# Common issues:
# 1. SIGNAGE_SECRET not set
#    → Add Environment line to service file
# 2. Syntax error in Python files
#    → Check for typos in edited files
# 3. Missing dependencies
#    → Reinstall: pip3 install --break-system-packages flask flask-login pillow numpy av
```

### Can't Log In

```bash
# Check if users file exists
ls -la /opt/PixelCast/led-signage/config/users.json

# If missing or empty, create first admin via web UI
# If exists but can't log in, check logs:
sudo journalctl -u led-signage | grep -i auth
```

### CSRF Token Errors

```bash
# Verify Flask-WTF is installed
python3 -c "import flask_wtf; print('OK')"

# If missing:
pip3 install --break-system-packages flask-wtf

# Restart service
sudo systemctl restart led-signage
```

### Nginx Issues

```bash
# Test nginx config
sudo nginx -t

# Check nginx logs
sudo tail -f /var/log/nginx/error.log

# Restart nginx
sudo systemctl restart nginx
```

---

## 📊 Rollback Procedure

If issues occur, you can rollback:

### Quick Rollback

```bash
# Stop service
sudo systemctl stop led-signage

# Restore previous code
cd /opt/PixelCast
mv led-signage led-signage-new
mv led-signage-backup led-signage

# Restore users file
cp /opt/PixelCast/led-signage/config/users.json.backup /opt/PixelCast/led-signage/config/users.json

# Remove SIGNAGE_SECRET requirement (old version)
sudo nano /etc/systemd/system/led-signage.service
# Remove the Environment line
sudo systemctl daemon-reload

# Start old version
sudo systemctl start led-signage
```

---

## 📝 Configuration Files Changed

| File | Change | Action Required |
|------|--------|-----------------|
| `signage/web/app.py` | Requires SIGNAGE_SECRET | Set environment variable |
| `signage/web/auth.py` | No default users | Create admin on first run |
| `deployment/nginx/pixelcast.conf` | Static serving commented | Optional: move static files |
| `signage/web/routes.py` | RBAC on mutations | Review user roles |
| Templates (3 files) | CSRF tokens added | None (automatic) |

---

## 🔗 Additional Resources

- **Full Fix List**: See `PHASE1_COMPLETION_SUMMARY.md`
- **Remaining Issues**: See `SECURITY_FIXES_STATUS.md`
- **Deployment Guide**: See `deployment/README.md`
- **Project Structure**: See `STRUCTURE.md`

---

## ✅ Sign-Off Checklist

Before considering deployment complete:

- [ ] SIGNAGE_SECRET environment variable set
- [ ] Service starts successfully
- [ ] Can log in (or create first admin)
- [ ] Viewer role cannot delete items
- [ ] Editor role can delete items
- [ ] API key works for API calls
- [ ] No tracebacks visible on error pages
- [ ] CSRF tokens present in forms
- [ ] Nginx serves pages correctly
- [ ] All tests pass (see Verification Tests above)

---

**Deployment Date**: ________________  
**Deployed By**: ________________  
**Sign-Off**: ________________
