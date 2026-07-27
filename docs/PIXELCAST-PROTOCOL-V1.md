# PixelCast Protocol v1

Status: Draft

Purpose:

Define a hardware-independent transport protocol between:

- PixelCast Renderer
- PixelCast Sender
- PixelCast Receivers

The protocol must support:

- single displays
- tiled video walls
- multiple receivers
- synchronized playback
- future receiver implementations

Examples:

- Colorlight
- Novastar
- SDL Simulator
- Linux Framebuffer
- FPGA Receiver
- ESP32 Receiver

---

# 1. Design Goals

Requirements:

- low latency
- deterministic
- resolution agnostic
- transport independent
- receiver agnostic
- simple implementation
- scalable

---

# 2. Terminology

## Canvas

The complete virtual display.

Example:

384x192

---

## Frame

A complete rendered image.

Example:

Frame #1205

---

## Tile

A rectangular subsection of a frame.

Example:

384x192

+-----+-----+-----+
| T0  | T1  | T2  |
+-----+-----+-----+
| T3  | T4  | T5  |
+-----+-----+-----+
| T6  | T7  | T8  |
+-----+-----+-----+

---

## Receiver

A framebuffer endpoint.

Example:

{
  "receiver_id": 0,
  "width": 128,
  "height": 64
}

---

# 3. Transport

Version 1:

UDP

Reasons:

- low latency
- no head-of-line blocking
- multicast capable
- simple implementation

Future:

- multicast
- QUIC
- TCP fallback

---

# 4. Packet Header

```c
struct pixelcast_header {
    uint32_t magic;
    uint16_t version;
    uint16_t flags;

    uint64_t frame_id;

    uint16_t tile_id;
    uint16_t tile_count;

    uint16_t width;
    uint16_t height;

    uint32_t payload_size;
};
```

---

# 5. Magic Number

```c
0x50494358
```

ASCII:

```text
PICX
```

---

# 6. Payload Format

Version 1:

RGB888

Pixel:

```text
R G B
```

3 bytes per pixel

---

# 7. Frame Lifecycle

Renderer:

Frame 1200
Frame 1201
Frame 1202

Every frame:

```text
frame_id++
```

---

# 8. Synchronization

Receivers must never display partial frames.

Process:

Receive Frame
↓
Store Backbuffer
↓
Frame Complete
↓
Swap
↓
Display

Equivalent to:

SwapOnVSync()

---

# 9. Tile Assignment

Example:

[
  {
    "receiver_id": 0,
    "x": 0,
    "y": 0,
    "width": 128,
    "height": 64
  }
]

---

# 10. Receiver Discovery

Version 1:

receivers.json

Future:

- UDP discovery
- mDNS
- service registry

---

# 11. Compression

Version 1:

None

Reason:

Simplicity.

Future:

- LZ4
- ZSTD
- Delta Frames

---

# 12. Network Budget

Example:

384x192 RGB888

Pixels:

73728

Frame Size:

221184 bytes

30 FPS:

6.6 MB/s
53 Mbps

60 FPS:

13.2 MB/s
106 Mbps

Fits comfortably within Gigabit Ethernet.

---

# 13. Future Flags

```c
FLAG_COMPRESSED
FLAG_KEYFRAME
FLAG_DELTA
FLAG_MULTICAST
FLAG_HDR
```

---

# 14. Receiver Contract

PixelCast produces:

- framebuffer
- metadata

Receiver consumes:

- framebuffer
- metadata

The protocol is the only interface between them.
