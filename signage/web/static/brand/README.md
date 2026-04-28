# PixelCast Brand Assets

This directory contains the PixelCast branding assets (logos, icons, favicons) that are served as static files.

## Files

- `pixelcast-favicon-16.svg` - 16x16 favicon
- `pixelcast-favicon-32.svg` - 32x32 favicon
- `pixelcast-icon-48.svg` - 48x48 icon (used in navbar)
- `pixelcast-icon-96.svg` - 96x96 icon
- `pixelcast-icon-512.svg` - 512x512 icon (Apple touch icon)
- `pixelcast-logo-adaptive.svg` - Adaptive logo (used on login page)
- `pixelcast-logo-light-background.svg` - Logo for light backgrounds

## Usage

These files are served via Flask's static file handler at `/static/brand/`.

In templates, reference them using:
```jinja2
{{ url_for('static', filename='brand/pixelcast-icon-48.svg') }}
```

## Deployment

These files are part of the application bundle and will be deployed with the code.
