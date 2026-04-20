"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/sysinfo.py                                              ║
║ Version:     1.0.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: System information collector - gathers CPU, memory, temperature,║
║              disk usage, and uptime statistics for monitoring dashboard.     ║
║                                                                              ║
║ Important:   Returns plain dicts suitable for JSON serialization. Reads      ║
║              from /proc filesystem and system commands.                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import time
import subprocess
import logging

log = logging.getLogger('sysinfo')

_start_time = time.time()


def uptime_seconds() -> float:
    """
    Get system uptime since daemon started.
    
    Returns:
        float: Uptime in seconds
    """
    return time.time() - _start_time


def cpu_percent() -> float:
    """
    Read CPU usage percentage from /proc/stat.
    Takes two samples 100ms apart for accurate measurement.
    
    Returns:
        float: CPU usage percentage (0-100)
    """
    try:
        with open('/proc/stat') as f:
            line = f.readline()
        fields = list(map(int, line.split()[1:]))
        idle   = fields[3]
        total  = sum(fields)
        # Call twice with a short gap for accurate reading
        time.sleep(0.1)
        with open('/proc/stat') as f:
            line = f.readline()
        fields2 = list(map(int, line.split()[1:]))
        idle2   = fields2[3]
        total2  = sum(fields2)
        idle_d  = idle2  - idle
        total_d = total2 - total
        if total_d == 0:
            return 0.0
        return round((1 - idle_d / total_d) * 100, 1)
    except Exception:
        return 0.0


def memory_info() -> dict:
    """
    Get memory usage statistics from /proc/meminfo.
    
    Returns:
        dict: Memory stats with keys: total_mb, used_mb, free_mb, percent
    """
    try:
        info = {}
        with open('/proc/meminfo') as f:
            for line in f:
                k, v = line.split(':', 1)
                info[k.strip()] = int(v.split()[0])   # kB
        total   = info.get('MemTotal', 0)
        free    = info.get('MemFree',  0)
        buffers = info.get('Buffers',  0)
        cached  = info.get('Cached',   0)
        used    = total - free - buffers - cached
        return {
            'total_mb': round(total  / 1024, 1),
            'used_mb':  round(used   / 1024, 1),
            'free_mb':  round((free + buffers + cached) / 1024, 1),
            'percent':  round(used / total * 100, 1) if total else 0
        }
    except Exception:
        return {'total_mb': 0, 'used_mb': 0, 'free_mb': 0, 'percent': 0}


def cpu_temp() -> float:
    """
    Get CPU temperature from thermal zone or vcgencmd.
    Tries thermal zones first, falls back to vcgencmd on failure.
    
    Returns:
        float: Temperature in Celsius
    """
    # Try thermal zone (works on all Pi models)
    for zone in range(5):
        path = f'/sys/class/thermal/thermal_zone{zone}/temp'
        try:
            with open(path) as f:
                return round(int(f.read().strip()) / 1000, 1)
        except Exception:
            continue
    # Fallback: vcgencmd
    try:
        r = subprocess.run(['vcgencmd', 'measure_temp'],
                           capture_output=True, text=True, timeout=2)
        t = r.stdout.strip().replace("temp=", "").replace("'C", "")
        return round(float(t), 1)
    except Exception:
        return 0.0


def disk_info(paths: list = None) -> list:
    """
    Get disk usage statistics for specified mount points.
    Auto-discovers USB/external mounts if paths is None.
    
    Args:
        paths (list, optional): List of mount point paths. Defaults to ['/'] + auto-discovered mounts.
    
    Returns:
        list: List of dicts with keys: path, label, total_gb, used_gb, free_gb, percent
    """
    if paths is None:
        paths = ['/']
        # Find USB/external mounts
        try:
            with open('/proc/mounts') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        dev, mnt = parts[0], parts[1]
                        if (mnt.startswith('/media') or
                                mnt.startswith('/mnt')):
                            paths.append(mnt)
        except Exception:
            pass

    results = []
    for path in paths:
        try:
            s      = os.statvfs(path)
            total  = s.f_frsize * s.f_blocks
            free   = s.f_frsize * s.f_bavail
            used   = total - free
            if total == 0:
                continue
            results.append({
                'path':     path,
                'label':    'System' if path == '/' else path,
                'total_gb': round(total / 1e9, 1),
                'used_gb':  round(used  / 1e9, 1),
                'free_gb':  round(free  / 1e9, 1),
                'percent':  round(used / total * 100, 1)
            })
        except Exception:
            pass
    return results


def full_stats() -> dict:
    """
    Collect all system statistics in a single call.
    Convenience function for dashboard/API endpoints.
    
    Returns:
        dict: Complete system stats with keys: uptime_s, cpu, temp, memory, disks, timestamp
    """
    return {
        'uptime_s':  round(uptime_seconds()),
        'cpu':       cpu_percent(),
        'temp':      cpu_temp(),
        'memory':    memory_info(),
        'disks':     disk_info(),
        'timestamp': time.time()
    }
