#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# PixelCast — Copyright (C) 2026 Bas van Ritbergen
#
# mount-usb.sh — Find and mount the first USB storage device to /media/usb.
# Called by PixelCast.service as ExecStartPre (failure is non-fatal).
#
# Detection order:
#   1. Any partition on a USB-transport block device (TRAN=usb)
#   2. Any /dev/sd* partition (excludes mmcblk SD-card paths)

USB_MOUNT="/media/usb"
mkdir -p "$USB_MOUNT"

# Already mounted?
if mountpoint -q "$USB_MOUNT"; then
    echo "[usb-mount] Already mounted at $USB_MOUNT"
    exit 0
fi

# 1. Prefer partitions explicitly on a USB transport
USB_DEV=$(lsblk -rno NAME,TRAN,TYPE 2>/dev/null | awk '
    $2=="usb" && $3=="part" { print "/dev/"$1; exit }
')

# 2. Fall back to whole-disk USB devices (no partition table)
if [ -z "$USB_DEV" ]; then
    USB_DEV=$(lsblk -rno NAME,TRAN,TYPE 2>/dev/null | awk '
        $2=="usb" && $3=="disk" { print "/dev/"$1; exit }
    ')
fi

# 3. Last resort: any /dev/sd* partition (not SD card)
if [ -z "$USB_DEV" ]; then
    USB_DEV=$(lsblk -rno NAME,TYPE 2>/dev/null | \
        awk '$2=="part" { print "/dev/"$1 }' | \
        grep -v mmcblk | head -1)
fi

if [ -z "$USB_DEV" ]; then
    echo "[usb-mount] No USB storage device found — running without USB"
    exit 1
fi

echo "[usb-mount] Mounting $USB_DEV at $USB_MOUNT …"

# Try vfat (FAT32) with full permissions, then any auto-detected fs
mount -t vfat -o uid=0,gid=0,umask=000,rw "$USB_DEV" "$USB_MOUNT" 2>/dev/null \
    || mount -o rw "$USB_DEV" "$USB_MOUNT" 2>/dev/null

if mountpoint -q "$USB_MOUNT"; then
    echo "[usb-mount] Mounted $USB_DEV at $USB_MOUNT"
    exit 0
else
    echo "[usb-mount] Failed to mount $USB_DEV"
    exit 1
fi
