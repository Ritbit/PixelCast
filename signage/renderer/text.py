"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/renderer/text.py                                        ║
║ Version:     1.0.0                                                           ║
║ Author:      Bas                                                             ║
║ Description: Multi-line text renderer with inline styling, scrolling (left, ║
║              right, up, down), word wrapping, custom fonts, and pixel-perfect║
║              LED rendering. Supports scroll strips with auto-duration.       ║
║                                                                              ║
║ Important:   Inline codes: §Crrggbb; (color), §Fname; (font), §Snn; (size),║
║              §R (reset). Pixel rendering for fonts ≤16px eliminates bleed.  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import time
import re
import logging
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .base import BaseRenderer
from .utils import load_background, parse_color

log = logging.getLogger('renderer.text')

INLINE_RE        = re.compile(r'§(C[0-9a-fA-F]{6}|F[^;]+|S\d+|R);?')


def _sanitize(text: str) -> str:
    """Remove ASCII control chars below 0x20, but keep \n and \t."""
    return ''.join(
        ch for ch in text
        if ord(ch) >= 32 or ch in ('\n', '\t')
    )
DEFAULT_FONT     = 'FreeSans.ttf'
DEFAULT_FONT_SMALL = 'DejaVuSans.ttf'   # better hinting at small sizes
LED_THRESHOLD    = 16    # px — use pixel rendering at or below this size

FONT_SEARCH = [
    '/opt/PixelCast/led-signage/fonts/',
    '/usr/share/fonts/truetype/freefont/',
    '/usr/share/fonts/truetype/dejavu/',
    '/usr/share/fonts/truetype/',
]


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

def _find_font(name, size):
    import os
    if not name: name = DEFAULT_FONT
    if os.path.isabs(name) and os.path.exists(name):
        return ImageFont.truetype(name, size)
    for d in FONT_SEARCH:
        for p in [os.path.join(d, name), os.path.join(d, name + '.ttf')]:
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    try:    return ImageFont.load_default(size=size)
    except TypeError: return ImageFont.load_default()


def _tw(text, font):
    try:    bb = font.getbbox(text); return max(0, bb[2] - bb[0])
    except: return font.getsize(text)[0]

def _th(text, font):
    try:    bb = font.getbbox(text); return max(1, bb[3] - bb[1])
    except: return font.getsize(text)[1]


# ---------------------------------------------------------------------------
# LED pixel text — no anti-aliasing
# ---------------------------------------------------------------------------

def _pixel_text(canvas, text, font, xy, fill):
    """Render text with hard pixel edges (no grey anti-aliasing).
    Uses a 32/255 threshold — low enough to catch light stroke pixels
    but high enough to exclude sub-pixel noise.
    """
    tmp = Image.new('L', canvas.size, 0)
    ImageDraw.Draw(tmp).text(xy, text, font=font, fill=255, stroke_width=0)
    # Threshold at 32 — captures faint strokes without noise
    tmp   = tmp.point(lambda p: 255 if p > 32 else 0).convert('L')
    color = Image.new('RGB', canvas.size, fill)
    canvas.paste(color, mask=tmp)


def _use_pixel(size, pixel_font):
    return pixel_font or size <= LED_THRESHOLD


# ---------------------------------------------------------------------------
# Styled segments
# ---------------------------------------------------------------------------

class Seg:
    __slots__ = ('text','color','font','size','pixel')
    def __init__(self, text, color, font, size, pixel):
        self.text  = text
        self.color = color
        self.font  = font
        self.size  = size
        self.pixel = pixel


def _parse_styled(raw, base_color, base_font, base_size, pixel_font):
    segs = []
    c, f, s, p, pos = base_color, base_font, base_size, pixel_font, 0
    for m in INLINE_RE.finditer(raw):
        chunk = raw[pos:m.start()]
        if chunk: segs.append(Seg(chunk, c, f, s, p))
        code = m.group(1)
        if   code.startswith('C'):
            hx=code[1:]; c=(int(hx[:2],16),int(hx[2:4],16),int(hx[4:],16))
        elif code.startswith('F'):
            try: f = _find_font(code[1:], s)
            except: pass
        elif code.startswith('S'):
            s = int(code[1:]); p = _use_pixel(s, pixel_font)
            try: f = _find_font(DEFAULT_FONT, s)
            except: pass
        elif code == 'R':
            c, f, s, p = base_color, base_font, base_size, pixel_font
        pos = m.end()
    tail = raw[pos:]
    if tail: segs.append(Seg(tail, c, f, s, p))
    return segs or [Seg(raw, base_color, base_font, base_size, pixel_font)]


def _sw(segs): return sum(_tw(s.text, s.font) for s in segs)
def _sh(segs): return max((_th(s.text, s.font) for s in segs), default=0)


def _draw_segs(canvas, draw, segs, x, y):
    for s in segs:
        if s.pixel:
            _pixel_text(canvas, s.text, s.font, (x, y), s.color)
        else:
            draw.text((x, y), s.text, font=s.font, fill=s.color)
        x += _tw(s.text, s.font)


# ---------------------------------------------------------------------------
# Word wrapping
# ---------------------------------------------------------------------------

def _wrap(segs, max_w):
    """Return list of lines (each a list of Seg)."""
    lines, line, lw = [], [], 0
    for seg in segs:
        words = seg.text.split(' ')
        for wi, word in enumerate(words):
            ww = _tw(word, seg.font)
            sp = _tw(' ', seg.font) if (wi > 0 and line) else 0
            if line and lw + sp + ww > max_w:
                lines.append(line); line = []; lw = 0; sp = 0
            if sp: line.append(Seg(' ', seg.color, seg.font, seg.size, seg.pixel)); lw += sp
            line.append(Seg(word, seg.color, seg.font, seg.size, seg.pixel)); lw += ww
    if line: lines.append(line)
    return lines or [[]]


# ---------------------------------------------------------------------------
# Render a block of wrapped lines onto a PIL image, return numpy
# ---------------------------------------------------------------------------

def _render_block(wrapped_lines, align, canvas_w, bg_img):
    """
    Render all wrapped lines onto a fresh bg_img-sized canvas.
    Returns numpy array (H, W, 3).
    """
    line_h   = max((_sh(wl) for wl in wrapped_lines if wl), default=10)
    total_h  = line_h * len(wrapped_lines) + max(0, len(wrapped_lines)-1)*3
    canvas   = bg_img.copy()
    draw     = ImageDraw.Draw(canvas)
    return canvas, draw, line_h, total_h


# ---------------------------------------------------------------------------
# Pre-built scroll strip
# ---------------------------------------------------------------------------

def _build_h_strip(segs, bg_arr, gap):
    """
    Build a wide numpy strip for left/right scrolling.
    The strip is [text | gap | text | gap | ...] wide enough to wrap.
    """
    text_w = _sw(segs)
    text_h = _sh(segs)
    total_w = text_w + gap
    # Make one repeat unit
    H, W = bg_arr.shape[:2]
    unit = Image.new('RGB', (total_w, H), (0,0,0,))
    # paste background tile into unit
    # (use leftmost W pixels of bg or solid color)
    unit.paste(Image.fromarray(bg_arr), (0, 0))
    # draw text centred vertically
    y = (H - text_h) // 2
    draw = ImageDraw.Draw(unit)
    _draw_segs(unit, draw, segs, 0, y)
    arr = np.array(unit, dtype=np.uint8)
    # Two repeats so we can always slice a full W
    return np.concatenate([arr, arr], axis=1)


def _build_v_strip(wrapped_lines, align, bg_arr, display_w, display_h):
    """
    Build a tall numpy strip for up/down scrolling.
    Content height + display_height padding top and bottom (seamless loop).
    """
    line_h  = max((_sh(wl) for wl in wrapped_lines if wl), default=10)
    content_h = line_h * len(wrapped_lines) + max(0, len(wrapped_lines)-1)*3
    # Total strip: blank screen above + content + blank screen below
    strip_h = display_h + content_h + display_h
    canvas  = Image.new('RGB', (display_w, strip_h), (0,0,0))
    # Tile background into canvas
    bg_tile = Image.fromarray(bg_arr)
    for y_off in range(0, strip_h, display_h):
        canvas.paste(bg_tile, (0, y_off))
    draw = ImageDraw.Draw(canvas)
    y    = display_h   # content starts after one blank screen
    for wl in wrapped_lines:
        lw = _sw(wl)
        if   align == 'right':  x = display_w - lw - 4
        elif align == 'center': x = (display_w - lw) // 2
        else:                   x = 4
        _draw_segs(canvas, draw, wl, x, y)
        y += line_h + 3
    return np.array(canvas, dtype=np.uint8)


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

class TextRenderer(BaseRenderer):

    def __init__(self, item, width, height):
        super().__init__(item, width, height)
        self._item = item
        self._fps  = int(item.get('fps', 30))
        self._v_center = item.get('v_center', False)

        line_cfgs = item.get('lines') or [
            {'text': item.get('text', 'Hello'),
             'color': [255,255,255], 'font_size': 16, 'align': 'center'}
        ]

        self._bg_cache = load_background(width, height, item)
        self._bg_arr   = np.array(self._bg_cache, dtype=np.uint8)

        # Parse each line config
        self._lines = []
        for cfg in line_cfgs:
            size       = int(cfg.get('font_size', 16))
            fn         = cfg.get('font', DEFAULT_FONT)
            color      = parse_color(cfg.get('color', [255,255,255]))
            pixel_font = bool(cfg.get('pixel_font', False))
            pixel      = _use_pixel(size, pixel_font)
            font       = _find_font(fn, size)
            raw_text   = _sanitize(cfg.get('text', ''))
            base_segs  = _parse_styled(raw_text, color, font, size, pixel)
            scroll     = cfg.get('scroll', False) or False
            do_wrap    = bool(cfg.get('wrap', True))
            align      = cfg.get('align', 'center')
            speed      = float(cfg.get('scroll_speed', 2))
            gap        = int(cfg.get('scroll_gap', 40))
            pos_key    = cfg.get('position') or None
            loop_count = int(cfg.get('loop_count', 0))  # 0 = infinite

            # Wrap: first split on explicit newlines, then word-wrap each segment
            if do_wrap and scroll not in ('left','right'):
                # Split text on \n before word-wrapping
                nl_lines = raw_text.split('\n')
                if len(nl_lines) > 1:
                    wrapped = []
                    for nl in nl_lines:
                        nl = nl.strip()
                        if nl:
                            nl_segs = _parse_styled(nl, color, font, size, pixel)
                            wrapped.extend(_wrap(nl_segs, width))
                        else:
                            # blank line → small spacer (empty seg)
                            wrapped.append([])
                else:
                    wrapped = _wrap(base_segs, width)
            else:
                wrapped = [base_segs]

            line_h    = max((_sh(wl) for wl in wrapped if wl), default=1)
            content_h = line_h * len(wrapped) + max(0, len(wrapped)-1)*3

            entry = dict(
                base_segs=base_segs, wrapped=wrapped,
                align=align, scroll=scroll, speed=speed, gap=gap,
                pos_key=pos_key, size=size, font=font, color=color,
                pixel=pixel, pixel_font=pixel_font,
                line_h=line_h, content_h=content_h,
                loop_count=loop_count,
                offset=0,
                # pre-built strips (set below)
                h_strip=None, v_strip=None,
            )

            # Pre-build scroll strips
            if scroll in ('left','right'):
                entry['h_strip'] = _build_h_strip(base_segs, self._bg_arr, gap)
            elif scroll in ('up','down'):
                entry['v_strip'] = _build_v_strip(
                    wrapped, align, self._bg_arr, width, height)

            self._lines.append(entry)

        # Assign Y positions for auto-stacked lines
        self._assign_y()

    def _assign_y(self):
        stacked = [l for l in self._lines if l['pos_key'] is None]
        if not stacked:
            return
        total_h = sum(l['content_h'] for l in stacked) + (len(stacked)-1)*6
        if self._v_center:
            y = (self.height - total_h) // 2
        else:
            y = max(4, (self.height - total_h) // 4)  # upper-ish default
        for l in stacked:
            l['_auto_y'] = y
            y += l['content_h'] + 6

    def _explicit_y(self, l):
        pk = l['pos_key'] or 'center'
        ch = l['content_h']
        if 'top'    in pk: return 2
        if 'bottom' in pk: return self.height - ch - 2
        return (self.height - ch) // 2

    def _render_static(self):
        canvas = self._bg_cache.copy()
        draw   = ImageDraw.Draw(canvas)
        for l in self._lines:
            if l['scroll'] not in (False, None, '', 'none'):
                continue
            y0 = l.get('_auto_y', 0) if l['pos_key'] is None else self._explicit_y(l)
            y  = y0
            for wl in l['wrapped']:
                lw = _sw(wl)
                al = l['align']
                x  = (self.width - lw) // 2 if al=='center' else \
                     self.width - lw - 4 if al=='right' else 4
                _draw_segs(canvas, draw, wl, x, y)
                y += l['line_h'] + 3
        return np.array(canvas, dtype=np.uint8)

    def first_frame(self):
        frame = self._render_static()
        # For scrolling lines, show their first slice as the first frame
        for l in self._lines:
            if l['scroll'] in ('left','right') and l['h_strip'] is not None:
                # paste first W columns of h_strip into this line's row range
                y0 = l.get('_auto_y', 0) if l['pos_key'] is None else self._explicit_y(l)
                lh = l['line_h']
                y1 = min(y0 + lh, self.height)
                frame[y0:y1, :self.width] = l['h_strip'][y0:y1, :self.width]
            elif l['scroll'] in ('up','down') and l['v_strip'] is not None:
                frame[:self.height, :] = l['v_strip'][:self.height, :]
        return frame

    def frames(self):
        # Yield frames. Respects loop_count per line; sets self._done when done.
        delay = 1.0 / self._fps
        self._done = False

        # One-pass frame counts; per-line loop tracking
        scrolling = [l for l in self._lines
                     if l['scroll'] in ('left','right','up','down')]
        for l in scrolling:
            sc = l['scroll']
            if sc in ('left', 'right'):
                cycle = _sw(l['base_segs']) + l['gap']
            else:
                cycle = l['content_h'] + self.height
            l['_pass_frames']  = max(1, cycle / max(0.01, l['speed']))
            l['_frames_shown'] = 0
            l['_loops_done']   = 0
            l['_loop_count']   = int(l.get('loop_count', 0))  # 0 = infinite

        # Track the static-only frame for when scroll is exhausted
        static_frame = None

        while True:
            # Check if all scrolling lines have hit their loop limit
            all_done = scrolling and all(
                l['_loop_count'] > 0 and l['_loops_done'] >= l['_loop_count']
                for l in scrolling
            )

            if all_done:
                # Hold static background, signal done
                if static_frame is None:
                    static_frame = self._render_static()
                if not self._done:
                    self._done = True
                yield static_frame
                time.sleep(delay)
                continue

            frame = self._render_static()

            for l in self._lines:
                sc = l['scroll']
                # Skip if this line has finished its loops
                if sc in ('left','right','up','down'):
                    if (l['_loop_count'] > 0 and
                            l['_loops_done'] >= l['_loop_count']):
                        continue   # hold at end — don't update offset

                if sc in ('left','right') and l['h_strip'] is not None:
                    strip   = l['h_strip']
                    W       = self.width
                    strip_w = strip.shape[1]
                    ox      = int(l['offset']) % (strip_w // 2)
                    y0 = l.get('_auto_y', 0) if l['pos_key'] is None else self._explicit_y(l)
                    lh = l['line_h']
                    y1 = min(y0 + lh, self.height)
                    sl = strip[y0:y1, ox:ox+W]
                    if sl.shape[1] < W:
                        sl = np.concatenate(
                            [sl, strip[y0:y1, :W-sl.shape[1]]], axis=1)
                    frame[y0:y1, :W] = sl
                    l['offset'] += l['speed'] * (1 if sc=='left' else -1)

                elif sc in ('up','down') and l['v_strip'] is not None:
                    strip     = l['v_strip']
                    H         = self.height
                    strip_h   = strip.shape[0]
                    content_h = l['content_h']
                    cycle     = content_h + H
                    ox        = int(l['offset']) % cycle
                    y_start   = ox if sc == 'up' else max(0, cycle - ox - H)
                    y_start  %= strip_h
                    sl        = strip[y_start:y_start+H, :]
                    if sl.shape[0] < H:
                        sl = np.concatenate(
                            [sl, strip[:H-sl.shape[0], :]], axis=0)
                    frame[:H, :] = sl
                    l['offset'] += l['speed']

                if l in scrolling:
                    l['_frames_shown'] = l.get('_frames_shown', 0) + 1
                    # Completed a full pass?
                    if l['_frames_shown'] >= l['_pass_frames']:
                        l['_frames_shown'] = 0
                        l['_loops_done']  += 1
                        # Signal done after first pass for auto-duration
                        if not self._done and l['_loop_count'] in (0, 1):
                            self._done = True
                        elif (not self._done and l['_loop_count'] > 1 and
                              l['_loops_done'] >= l['_loop_count']):
                            self._done = True

            yield frame
            time.sleep(delay)
