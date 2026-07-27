# PixelCast Vision

PixelCast is a hardware-agnostic framebuffer rendering platform for LED signage and video walls.

Core philosophy:

Render once.
Display anywhere.

PixelCast must never depend on:

- HUB75 specifics
- Colorlight specifics
- Novastar specifics
- FPGA specifics

PixelCast renders pixels.

Receivers display pixels.

---

# Objectives

- Video playback
- Signage content
- Dynamic widgets
- Multi-screen walls
- Hardware independence
- Open architecture

---

# Architecture Principle

Hardware is replaceable.

The renderer is not.

---

# Long-Term Goal

The exact same scene should render to:

- Colorlight wall
- Novastar wall
- SDL preview
- HDMI display
- Linux framebuffer
- MP4 export

without modifying the scene or renderer.

---

# Non-Goals

PixelCast is not:

- an LED driver
- a scan engine
- a HUB75 timing implementation
- a panel mapper

Those belong inside receivers.

---

# Guiding Rule

PixelCast renders pixels.

Receivers display pixels.
