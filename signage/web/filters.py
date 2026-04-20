"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/web/filters.py                                          ║
║ Version:     1.0.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Custom Jinja2 template filters - timecode, basename, rgb_hex.   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import os


def register_filters(app):

    @app.template_filter('timecode')
    def timecode_filter(value):
        """Convert a stored start_offset value to display timecode string."""
        if not value and value != 0:
            return ''
        s = str(value).strip()
        # If already looks like a timecode string (contains colon), return as-is
        if ':' in s:
            return s
        # Plain float seconds — convert to timecode display
        try:
            from signage.timecode import seconds_to_timecode
            return seconds_to_timecode(float(s))
        except Exception:
            return s


    @app.template_filter('basename')
    def basename_filter(path):
        return os.path.basename(path) if path else ''

    @app.template_filter('rgb_hex')
    def rgb_hex_filter(color):
        """Convert [r, g, b] list to '#rrggbb' hex string for color inputs."""
        try:
            r, g, b = int(color[0]), int(color[1]), int(color[2])
            return f'#{r:02x}{g:02x}{b:02x}'
        except (TypeError, IndexError, ValueError):
            return '#ffffff'
