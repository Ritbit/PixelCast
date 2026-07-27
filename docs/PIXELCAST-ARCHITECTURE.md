# PixelCast Architecture

Status: Draft

This document describes the internal architecture of PixelCast.

For project goals see:

- PIXELCAST-VISION.md

For transport details see:

- PIXELCAST-PROTOCOL-V1.md

---

# 1. System Overview

PixelCast is a hardware-agnostic rendering platform for LED signage and video walls.

PixelCast renders scenes into framebuffers and distributes those framebuffers to one or more receivers.

PixelCast does not drive display hardware directly.

---

# 2. High-Level Architecture

Media Sources
      │
      ▼
Scene System
      │
      ▼
Layout Engine
      │
      ▼
Renderer
      │
      ▼
Framebuffer
      │
      ▼
Tile Splitter
      │
      ▼
Protocol Layer
      │
      ▼
Receiver Backends
      │
      ▼
Display Hardware

---

# 3. Core Components

## Scene System

Responsibilities:

- scene loading
- scene validation
- layer management
- asset references

Input:

JSON scene files

Output:

resolved scene graph

---

## Layout Engine

Responsibilities:

- coordinate calculations
- scaling
- alignment
- wall layout handling

Input:

scene graph

Output:

renderable layout

---

## Renderer

Responsibilities:

- layer composition
- image rendering
- text rendering
- video rendering
- animation rendering

Output:

RGBA framebuffer

---

## Framebuffer Manager

Responsibilities:

- framebuffer allocation
- double buffering
- frame lifecycle management

Output:

completed frame

---

## Tile Splitter

Responsibilities:

- split frame into receiver regions
- generate tile metadata
- support arbitrary wall layouts

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

## Protocol Layer

Responsibilities:

- packet generation
- synchronization metadata
- receiver communication

Uses:

PixelCast Protocol v1

---

## Receiver Backends

Responsibilities:

- consume PixelCast protocol
- manage hardware-specific output
- implement synchronization

Examples:

- Colorlight
- Novastar
- SDL
- Linux framebuffer
- custom FPGA

---

# 4. Scene Model

Example:

{
  "canvas": {
    "width": 384,
    "height": 192,
    "fps": 30
  },
  "layers": [
    {
      "type": "video",
      "source": "promo.mp4"
    },
    {
      "type": "text",
      "text": "Welcome"
    }
  ]
}

---

# 5. Layer Types

Current:

- video
- image
- text

Planned:

- shapes
- widgets
- MQTT data
- API data
- playlists

---

# 6. Editor Architecture

Editor and runtime remain separate.

Editor:

- WYSIWYG
- drag-and-drop
- scene creation

Runtime:

- scene execution
- rendering
- streaming

Editor output:

JSON only

---

# 7. Display Scaling

Supported:

- single receiver
- multiple receivers
- tiled walls
- multiple walls

The renderer remains unaware of the underlying hardware.

---

# 8. Synchronization

Every frame contains:

- frame_id
- timestamp

Receivers:

Receive
→ Buffer
→ Complete
→ Swap
→ Display

Partial frames must never be displayed.

---

# 9. Future Components

Planned:

- scheduling engine
- playlist manager
- widget framework
- MQTT integration
- REST integrations
- cluster management
- receiver discovery

---

# 10. Development Priorities

1. Renderer stabilization
2. Scene graph implementation
3. Video pipeline
4. Framebuffer management
5. Protocol implementation
6. Reference receiver
7. Colorlight backend
8. Multi-receiver support
9. Editor prototype

---

# Guiding Rule

PixelCast renders pixels.

Receivers display pixels.
