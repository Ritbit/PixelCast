"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Output Backend Abstraction                                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/outputs.py                                              ║
║ Description: Pluggable output backends. Select via output_type in            ║
║              panel.json: "gpio" (default) or "colorlight".                  ║
║                                                                              ║
║  gpio        → hZeller rpi-rgb-led-matrix via GPIO HAT                      ║
║  colorlight  → ColorLight 5A-75B receiver card via UDP Ethernet             ║
╚══════════════════════════════════════════════════════════════════════════════╝

ColorLight 5A-75B protocol notes
─────────────────────────────────
All card configuration is sent from the daemon — no Windows software needed.
Network setup: assign static IPs to both the Pi and the card on the same
subnet (e.g. 192.168.0.x/24).  Connect directly or via a dedicated switch.

On first startup with output_type=colorlight the daemon sends a configuration
sequence to the card, then streams frames continuously.

--- Configuration packets (sent once on startup / via UI button) ---

Screen-parameters packet (command 0x05):
  Byte 0    : 0x02  – protocol marker
  Byte 1    : 0x05  – screen config command
  Byte 2-3  : display width,  big-endian uint16
  Byte 4-5  : display height, big-endian uint16
  Byte 6    : scan lines (rows // 2 for 1/32 scan, e.g. 32 for 64-row panels)
  Byte 7    : colour depth (24 = RGB888)
  Byte 8-9  : 0x00 0x00  (reserved)

Port-mapping packet (command 0x0B, one per HUB75 output port used):
  Byte 0    : 0x02
  Byte 1    : 0x0B  – port mapping command
  Byte 2    : port index  (0-based)
  Byte 3-4  : x offset,   big-endian uint16
  Byte 5-6  : y offset,   big-endian uint16
  Byte 7-8  : port width, big-endian uint16
  Byte 9-10 : port height, big-endian uint16

--- Frame-data packets (sent each frame, one per display row) ---

  Byte 0    : 0x02  – frame-data marker
  Byte 1    : 0x06  – row-data command
  Byte 2-3  : row index, big-endian uint16
  Byte 4-5  : 0x00 0x00  (reserved)
  Byte 6…   : RGB888 pixel data for that row  (width × 3 bytes)

--- Brightness packet ---

  Byte 0    : 0x02
  Byte 1    : 0x08  – brightness command
  Byte 2    : R gain  (0-255)
  Byte 3    : G gain  (0-255)
  Byte 4    : B gain  (0-255)
  Byte 5    : 0x00

Default card IP : 192.168.0.20  (configurable in settings)
Default UDP port: 7000

Relevant panel.json keys (ColorLight-specific):
  colorlight_ip       : card IP          (default 192.168.0.20)
  colorlight_port     : UDP port         (default 7000)
  colorlight_scan_lines: scan lines       (default rows//2, e.g. 32)
  colorlight_ports    : HUB75 ports used (default 2)
"""

import logging
import socket
import struct
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

        # Snapshot threads before init so we can pin the new C++ refresh
        # thread to the isolated CPU core after construction.
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

    def send_frame(self, image: Image.Image) -> None:
        self._matrix.SetImage(image.convert('RGB'))

    def set_brightness(self, pct: int) -> None:
        self._matrix.brightness = max(1, min(100, pct))

    def close(self) -> None:
        self._matrix.Clear()


# ──────────────────────────────────────────────────────────────────────────────
# ColorLight 5A-75B backend
# ──────────────────────────────────────────────────────────────────────────────

class ColorLightOutput(BaseOutput):
    """Sends configuration and frames to a ColorLight 5A-75B receiver card over UDP."""

    DEFAULT_IP   = '192.168.0.20'
    DEFAULT_PORT = 7000

    def __init__(self, cfg: dict):
        self.width  = cfg['display_width']
        self.height = cfg['display_height']
        self.ip     = cfg.get('colorlight_ip',         self.DEFAULT_IP)
        self.port   = cfg.get('colorlight_port',       self.DEFAULT_PORT)
        self._scan_lines = cfg.get('colorlight_scan_lines',
                                   cfg.get('rows', 64) // 2)
        self._num_ports  = cfg.get('colorlight_ports', 2)
        self._brightness = max(1, min(100, cfg.get('brightness', 80)))

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._row_bytes = self.width * 3

        log.info(f"ColorLightOutput: {self.width}×{self.height} "
                 f"scan_lines={self._scan_lines} ports={self._num_ports} "
                 f"→ {self.ip}:{self.port}")
        self.configure()

    # ── configuration ─────────────────────────────────────────────────────────

    def configure(self) -> None:
        """Send display configuration to the card (screen params + port mapping).

        Safe to call multiple times — the card applies settings immediately.
        Called automatically on startup; also available via the web UI button.
        """
        dest = (self.ip, self.port)

        # Screen-parameters packet — tells the card the total display size and
        # scan configuration.
        screen_pkt = struct.pack('>BB HH BBBB',
            0x02, 0x05,
            self.width, self.height,
            self._scan_lines, 24, 0x00, 0x00)
        self._sock.sendto(screen_pkt, dest)
        log.info(f"ColorLight: sent screen config "
                 f"{self.width}×{self.height} scan={self._scan_lines}")

        # Port-mapping packets — one per HUB75 output port used.
        # Each port drives a horizontal strip: full width, height/num_ports tall.
        # For a 256×128 display with 2 ports:
        #   Port 0 → x=0, y=0,  w=256, h=64   (top 2 panels)
        #   Port 1 → x=0, y=64, w=256, h=64   (bottom 2 panels)
        port_h = self.height // self._num_ports
        for i in range(self._num_ports):
            port_pkt = struct.pack('>BB B HH HH',
                0x02, 0x0B,
                i,
                0, i * port_h,
                self.width, port_h)
            self._sock.sendto(port_pkt, dest)
            log.info(f"ColorLight: port {i} → "
                     f"x=0 y={i*port_h} {self.width}×{port_h}")

        self._send_brightness(self._brightness)

    # ── protocol helpers ──────────────────────────────────────────────────────

    def _send_brightness(self, pct: int) -> None:
        gain = int(pct / 100 * 255)
        pkt  = bytes([0x02, 0x08, gain, gain, gain, 0x00])
        self._sock.sendto(pkt, (self.ip, self.port))

    def _row_packet(self, row: int, row_data: bytes) -> bytes:
        return struct.pack('>BBHH', 0x02, 0x06, row, 0) + row_data

    # ── BaseOutput API ────────────────────────────────────────────────────────

    def send_frame(self, image: Image.Image) -> None:
        raw  = image.convert('RGB').tobytes()
        rb   = self._row_bytes
        send = self._sock.sendto
        dest = (self.ip, self.port)
        for row in range(self.height):
            send(self._row_packet(row, raw[row * rb : (row + 1) * rb]), dest)

    def set_brightness(self, pct: int) -> None:
        self._brightness = max(1, min(100, pct))
        self._send_brightness(self._brightness)

    def close(self) -> None:
        self.clear()
        self._sock.close()


# ──────────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────────

def create_output(cfg: dict) -> BaseOutput:
    """
    Return the appropriate output backend based on cfg['output_type'].

    output_type values:
        'gpio'        – GPIO HAT via rpi-rgb-led-matrix  (default)
        'colorlight'  – ColorLight 5A-75B receiver card via UDP
    """
    output_type = cfg.get('output_type', 'gpio')

    if output_type == 'colorlight':
        log.info("Output backend: ColorLight 5A-75B (UDP Ethernet)")
        return ColorLightOutput(cfg)

    if output_type == 'gpio':
        try:
            log.info("Output backend: GPIO HAT (rpi-rgb-led-matrix)")
            return GPIOOutput(cfg)
        except ImportError:
            log.warning("rgbmatrix not available — falling back to StubOutput")
            return StubOutput(cfg['display_width'], cfg['display_height'])

    log.error(f"Unknown output_type '{output_type}' — falling back to StubOutput")
    return StubOutput(cfg['display_width'], cfg['display_height'])
