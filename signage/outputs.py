# SPDX-License-Identifier: AGPL-3.0-or-later
#
# PixelCast
# Copyright (C) 2026 Bas van Ritbergen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public
# License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Output Backend Abstraction                                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/outputs.py                                              ║
║ Description: Pluggable output backends. Select via output_type in            ║
║              panel.json: "gpio" (default) or "colorlight".                  ║
║                                                                              ║
║  gpio        → hZeller rpi-rgb-led-matrix via GPIO HAT                      ║
║  colorlight  → ColorLight 5A-75B receiver card via raw Ethernet (L2)        ║
╚══════════════════════════════════════════════════════════════════════════════╝

ColorLight 5A-75B protocol notes
─────────────────────────────────
This is NOT an IP/UDP protocol — the card has no IP address at all. Frames
are raw Ethernet (Layer 2) addressed to the card's fixed, vendor-hardcoded
MAC 11:22:33:44:55:66. Byte layout below matches Falcon Player's shipping
ColorLight output plugin (github.com/FalconChristmas/fpp,
src/channeloutput/ColorLight-5a-75.{h,cpp}), cross-checked against
https://hkubota.wordpress.com/2022/01/31/winter-project-colorlight-5a-75b-protocol/

IMPORTANT — one-time setup still required outside PixelCast: the card's
internal panel geometry (resolution per HUB75 output port, panel size, scan
type) must be provisioned ONCE using ColorLight's own LEDVISION tool
(Windows, or Wine) before this backend will display anything sensible. The
"receiver layout" packets LEDVISION uses for that are not reliably
reverse-engineered (FPP's own source marks most of them "????" and does not
attempt to replicate them), so PixelCast doesn't try either. Once LEDVISION
has configured the card, that layout is stored on the card itself and
survives power cycles / reboots — from then on PixelCast only needs to
stream pixel/brightness/sync frames, same as FPP does.

Every Ethernet frame here has the same 13-byte head:
  Byte 0-5   : destination MAC — always 11:22:33:44:55:66 (fixed by vendor)
  Byte 6-11  : source MAC — the Pi's own interface MAC
  Byte 12    : packet type (see below)
followed by packet-type-specific data starting at byte 13. (Packet captures
show bytes 12-13 as an "EtherType" field, but the firmware just reads plain
bytes at fixed offsets — there's no real EtherType semantics involved.)

Packet types:
  0x0A  Brightness   — data[0..2]=RGB gain (0-255), data[3]=0xFF
  0x55  Pixel row    — data[0-1]=row (big-endian, global 0..display_height-1),
                        data[2-3]=pixel offset within row, data[4-5]=pixel
                        count in this packet, data[6]=0x08, data[7]=0x88,
                        data[8:]=RGB888 pixel data. Rows wider than 497px
                        are split across multiple packets (Ethernet MTU).
  0x01  Sync/Display — tells the card to swap in the frame just streamed.
                        Sent once per completed frame.
  0x07/0x08 Discover/Reply — best-effort diagnostic handshake to find the
                        card and read back firmware version; not required
                        for normal operation.

Row numbering is global across the whole canvas (0..display_height-1); the
card maps row ranges to physical HUB75 output ports based on the per-output
panel height configured via LEDVISION. For N equally-tall horizontal ports
(colorlight_ports), configure LEDVISION with N outputs of height
(display_height // colorlight_ports) each, stacked top to bottom, to match
this backend's row addressing.

Relevant panel.json keys (ColorLight-specific):
  colorlight_iface       : network interface the card is wired to (default eth0)
  colorlight_ports       : HUB75 ports used — informational, matches the
                            LEDVISION receiver layout (default 2)
  colorlight_color_order : 'RGB' or 'BGR' — panel wiring varies by unit;
                            confirmed 'BGR' on our P2.5 panels via live test
                            (matches hkubota's own "BGR for my panel" note).
                            Default 'BGR'.
"""

import logging
import socket
import struct
import time
from abc import ABC, abstractmethod

import numpy as np
from PIL import Image

log = logging.getLogger('outputs')


# ──────────────────────────────────────────────────────────────────────────────
# Base class
# ──────────────────────────────────────────────────────────────────────────────

class BaseOutput(ABC):
    """Abstract output backend.  All backends must implement these three methods."""

    @abstractmethod
    def send_frame(self, image: Image.Image) -> None:
        """Push a PIL RGB image to the display."""

    @abstractmethod
    def set_brightness(self, pct: int) -> None:
        """Set display brightness 1-100."""

    @abstractmethod
    def close(self) -> None:
        """Release hardware / sockets cleanly."""

    def clear(self) -> None:
        """Blank the display (black frame)."""
        from PIL import Image as _Image
        self.send_frame(_Image.new('RGB', (self.width, self.height), (0, 0, 0)))


# ──────────────────────────────────────────────────────────────────────────────
# Stub (no hardware — development mode)
# ──────────────────────────────────────────────────────────────────────────────

class StubOutput(BaseOutput):
    """Silent no-op backend used when no hardware library is available."""

    def __init__(self, width: int, height: int):
        self.width  = width
        self.height = height
        log.warning("StubOutput active — frames are discarded (no hardware)")

    def send_frame(self, image: Image.Image) -> None:
        pass

    def set_brightness(self, pct: int) -> None:
        pass

    def close(self) -> None:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# GPIO / HAT backend  (hZeller rpi-rgb-led-matrix)
# ──────────────────────────────────────────────────────────────────────────────

class GPIOOutput(BaseOutput):
    """Drives HUB75 panels via a GPIO HAT using the hZeller rgbmatrix library."""

    def __init__(self, cfg: dict):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        import os

        self.width  = cfg['display_width']
        self.height = cfg['display_height']

        options = RGBMatrixOptions()
        options.hardware_mapping         = cfg['gpio_mapping']
        options.rows                     = cfg['rows']
        options.cols                     = cfg['cols']
        options.chain_length             = cfg['chain']
        options.parallel                 = cfg['parallel']
        options.gpio_slowdown            = cfg['slowdown_gpio']
        options.pwm_bits                 = cfg['pwm_bits']
        options.pwm_lsb_nanoseconds      = cfg['pwm_lsb_nanoseconds']
        options.pwm_dither_bits          = cfg['pwm_dither_bits']
        options.brightness               = cfg['brightness']
        options.disable_hardware_pulsing = cfg.get('disable_hardware_pulsing', False)
        options.show_refresh_rate        = cfg.get('show_refresh_rate', False)
        options.drop_privileges          = False

        limit = cfg.get('limit_refresh', 0)
        if limit > 0:
            options.limit_refresh_rate_hz = limit

        scan_mode = cfg.get('scan_mode', 0)
        if scan_mode:
            options.scan_mode = scan_mode

        row_addr = cfg.get('row_addr_type', 0)
        if row_addr:
            options.row_address_type = row_addr

        mux = cfg.get('multiplexing', 0)
        if mux:
            options.multiplexing = mux

        rgb_seq = cfg.get('rgb_sequence', 'RGB')
        if rgb_seq and rgb_seq != 'RGB':
            options.led_rgb_sequence = rgb_seq

        panel_type = cfg.get('panel_type', '')
        if panel_type:
            options.panel_type = panel_type

        pixel_mapper = cfg.get('pixel_mapper', '')
        if pixel_mapper:
            options.pixel_mapper_config = pixel_mapper

        # RGBMatrix() spawns the native GPIO refresh thread — capture the
        # thread-id set before/after construction so we can pin only the
        # newly-created thread to the isolated CPU core (isolcpus=3).
        tids_before = self._thread_ids()
        self._matrix = RGBMatrix(options=options)
        self._pin_new_threads(tids_before, cpu=3)
        log.info("GPIOOutput: RGBMatrix hardware initialised")

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _thread_ids():
        import os
        try:
            return {int(t) for t in os.listdir(f'/proc/{os.getpid()}/task')}
        except OSError:
            return set()

    @staticmethod
    def _pin_new_threads(tids_before: set, cpu: int = 3):
        import os
        new_tids = GPIOOutput._thread_ids() - tids_before
        for tid in new_tids:
            try:
                os.sched_setaffinity(tid, {cpu})
                log.info(f"GPIOOutput: refresh thread {tid} pinned to CPU core {cpu}")
            except (OSError, AttributeError) as e:
                log.debug(f"GPIOOutput: could not pin thread {tid}: {e}")

    # ── BaseOutput API ────────────────────────────────────────────────────────

    def create_canvas(self):
        """Return a FrameCanvas for double-buffered / SwapOnVSync output."""
        return self._matrix.CreateFrameCanvas()

    def swap_canvas(self, canvas):
        """Swap canvas to display; returns the new writable back canvas."""
        return self._matrix.SwapOnVSync(canvas)

    def send_frame(self, image: Image.Image) -> None:
        self._matrix.SetImage(image)   # caller guarantees RGB mode

    def set_brightness(self, pct: int) -> None:
        self._matrix.brightness = max(1, min(100, pct))

    def close(self) -> None:
        self._matrix.Clear()


# ──────────────────────────────────────────────────────────────────────────────
# ColorLight 5A-75B backend
# ──────────────────────────────────────────────────────────────────────────────

class ColorLightOutput(BaseOutput):
    """Streams frames to a ColorLight 5A-75B receiver card over raw Ethernet.

    See the module docstring for the full protocol description. This is a
    Layer-2 protocol (no IP/UDP) addressed to a fixed vendor MAC — requires
    root (for AF_PACKET raw sockets) and Linux. The card's panel/port layout
    must already be provisioned via LEDVISION; this backend only streams.
    """

    DEST_MAC = bytes.fromhex('112233445566')
    FALLBACK_SRC_MAC = bytes.fromhex('222233445566')

    TYPE_SYNC             = 0x01
    SYNC_SIZE             = 112
    TYPE_DISCOVER         = 0x07
    DISC_SIZE             = 284
    TYPE_DISCOVER_REPLY   = 0x08
    TYPE_BRIGHTNESS       = 0x0A
    BRIG_SIZE             = 77
    TYPE_PIXEL            = 0x55
    MAX_PIXELS_PER_PACKET = 497
    MAX_BYTES_PER_PACKET  = MAX_PIXELS_PER_PACKET * 3

    SIOCGIFHWADDR = 0x8927

    def __init__(self, cfg: dict):
        self.width  = cfg['display_width']
        self.height = cfg['display_height']
        self.iface  = cfg.get('colorlight_iface', 'eth0')
        self._num_ports  = cfg.get('colorlight_ports', 2)
        self._brightness = max(1, min(100, cfg.get('brightness', 80)))
        color_order = cfg.get('colorlight_color_order', 'BGR').upper()
        self._pil_rawmode = 'BGR' if color_order == 'BGR' else 'RGB'

        self._sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
        self._sock.bind((self.iface, 0))
        self._src_mac = self._get_iface_mac(self.iface)

        port_h = self.height // self._num_ports
        log.info(f"ColorLightOutput: {self.width}x{self.height} "
                 f"({self._num_ports} ports x {port_h}px tall) raw-Ethernet "
                 f"on {self.iface} -> {self.DEST_MAC.hex(':')} "
                 f"(card must already be provisioned via LEDVISION)")
        self._send_brightness(self._brightness)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get_iface_mac(self, iface: str) -> bytes:
        """Read the Pi's own interface MAC to use as the frame source address."""
        try:
            import fcntl
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                info = fcntl.ioctl(s.fileno(), self.SIOCGIFHWADDR,
                                    struct.pack('256s', iface[:15].encode()))
            finally:
                s.close()
            return info[18:24]
        except (OSError, ImportError) as e:
            log.warning(f"ColorLightOutput: could not read MAC of {iface}, "
                        f"using fallback source MAC ({e})")
            return self.FALLBACK_SRC_MAC

    def _build(self, packet_type: int, data: bytes, min_size: int = 0) -> bytes:
        """dst(6) + src(6) + type(1) + data — see module docstring for layout."""
        frame = bytearray(13 + len(data))
        frame[0:6]  = self.DEST_MAC
        frame[6:12] = self._src_mac
        frame[12]   = packet_type
        frame[13:]  = data
        if len(frame) < min_size:
            frame.extend(b'\x00' * (min_size - len(frame)))
        return bytes(frame)

    def _send_brightness(self, pct: int) -> None:
        gain = int(round(pct / 100 * 255))
        data = bytes([gain, gain, gain, 0xFF])
        self._sock.send(self._build(self.TYPE_BRIGHTNESS, data, self.BRIG_SIZE))

    def _send_sync(self) -> None:
        """Display/sync frame — tells the card to swap in the frame just streamed."""
        data = bytearray(28)
        data[0] = 0x07
        b = int(round(self._brightness / 100 * 255))
        data[22], data[23] = b, 0x05
        data[25], data[26], data[27] = b, b, b
        self._sock.send(self._build(self.TYPE_SYNC, bytes(data), self.SYNC_SIZE))

    def discover(self, timeout: float = 1.0):
        """Broadcast a discovery frame and wait for the card's reply.

        Diagnostic only — not required for normal operation. Field offsets
        come from community reverse-engineering and may not be exact on
        every firmware version. Returns a dict on success, None on timeout.
        """
        req = self._build(self.TYPE_DISCOVER, bytes(self.DISC_SIZE - 13), self.DISC_SIZE)
        self._sock.settimeout(timeout)
        try:
            self._sock.send(req)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                frame = self._sock.recv(2048)
                if len(frame) >= 17 and frame[12] == self.TYPE_DISCOVER_REPLY:
                    return {
                        'model_byte':     frame[13],
                        'firmware_major': frame[15],
                        'firmware_minor': frame[16],
                    }
        except socket.timeout:
            pass
        finally:
            self._sock.settimeout(None)
        return None

    # ── BaseOutput API ────────────────────────────────────────────────────────

    def send_frame(self, image: Image.Image) -> None:
        # Panel wiring determines byte order on the wire — confirmed BGR on
        # our hardware via live test (see colorlight_color_order above).
        raw = image.convert('RGB').tobytes('raw', self._pil_rawmode)
        row_bytes = self.width * 3
        send, build, max_bytes = self._sock.send, self._build, self.MAX_BYTES_PER_PACKET

        for row in range(self.height):
            row_data = raw[row * row_bytes: (row + 1) * row_bytes]
            offset = 0
            while offset < row_bytes:
                chunk = row_data[offset: offset + max_bytes]
                pixel_offset    = offset // 3
                pixels_in_chunk = len(chunk) // 3
                header = bytes([
                    (row >> 8) & 0xFF, row & 0xFF,
                    (pixel_offset >> 8) & 0xFF, pixel_offset & 0xFF,
                    (pixels_in_chunk >> 8) & 0xFF, pixels_in_chunk & 0xFF,
                    0x08, 0x88,
                ])
                send(build(self.TYPE_PIXEL, header + chunk))
                offset += len(chunk)

        self._send_sync()

    def set_brightness(self, pct: int) -> None:
        self._brightness = max(1, min(100, pct))
        self._send_brightness(self._brightness)

    def close(self) -> None:
        try:
            self.clear()
        except OSError:
            pass
        self._sock.close()


# ──────────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────────

def create_output(cfg: dict) -> BaseOutput:
    """
    Return the appropriate output backend based on cfg['output_type'].

    output_type values:
        'gpio'        – GPIO HAT via rpi-rgb-led-matrix  (default)
        'colorlight'  – ColorLight 5A-75B receiver card via raw Ethernet
    """
    output_type = cfg.get('output_type', 'gpio')

    if output_type == 'colorlight':
        try:
            log.info("Output backend: ColorLight 5A-75B (raw Ethernet)")
            return ColorLightOutput(cfg)
        except (OSError, AttributeError) as e:
            # AF_PACKET raw sockets are Linux-only and need root — falls
            # back cleanly on dev machines / missing permissions.
            log.warning(f"ColorLight raw socket unavailable ({e}) — "
                        f"falling back to StubOutput")
            return StubOutput(cfg['display_width'], cfg['display_height'])

    if output_type == 'gpio':
        try:
            log.info("Output backend: GPIO HAT (rpi-rgb-led-matrix)")
            return GPIOOutput(cfg)
        except ImportError:
            log.warning("rgbmatrix not available — falling back to StubOutput")
            return StubOutput(cfg['display_width'], cfg['display_height'])

    log.error(f"Unknown output_type '{output_type}' — falling back to StubOutput")
    return StubOutput(cfg['display_width'], cfg['display_height'])
