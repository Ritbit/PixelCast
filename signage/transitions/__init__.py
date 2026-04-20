"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/transitions/__init__.py                                 ║
║ Version:     1.0.0                                                           ║
║ Author:      Bas                                                             ║
║ Description: Transition factory - creates transition effect instances by     ║
║              name. Supports 22 effects including fades, wipes, slides, etc.  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from .effects import (
    FadeTransition, FadeBlackTransition,
    WipeLeftTransition, WipeRightTransition,
    WipeUpTransition, WipeDownTransition,
    SlideLeftTransition, SlideRightTransition,
    SlideUpTransition, SlideDownTransition,
    ZoomInTransition, ZoomOutTransition,
    DissolveTransition, MeltTransition,
    SnowTransition, SpiralTransition,
    DropTransition, BlindsHTransition, BlindsVTransition,
    CheckerboardTransition, PixelateTransition,
)
import random
import logging

log = logging.getLogger('transitions')

REGISTRY = {
    'fade':         FadeTransition,
    'fade_black':   FadeBlackTransition,
    'wipe_left':    WipeLeftTransition,
    'wipe_right':   WipeRightTransition,
    'wipe_up':      WipeUpTransition,
    'wipe_down':    WipeDownTransition,
    'slide_left':   SlideLeftTransition,
    'slide_right':  SlideRightTransition,
    'slide_up':     SlideUpTransition,
    'slide_down':   SlideDownTransition,
    'zoom_in':      ZoomInTransition,
    'zoom_out':     ZoomOutTransition,
    'dissolve':     DissolveTransition,
    'melt':         MeltTransition,
    'snow':         SnowTransition,
    'spiral':       SpiralTransition,
    'drop':         DropTransition,
    'blinds_h':     BlindsHTransition,
    'blinds_v':     BlindsVTransition,
    'checkerboard': CheckerboardTransition,
    'pixelate':     PixelateTransition,
}

RANDOM_POOL = list(REGISTRY.keys())

# Default FPS for transitions — each effect generates STEPS frames
# at this rate, giving duration = STEPS / FPS seconds
TRANSITION_FPS = 30


def get_transition(name: str, duration: float = 1.0):
    """
    Return an instantiated transition by name.
    duration: transition duration in seconds (0.1 – 5.0)
    'random' picks a random effect.
    """
    if name == 'random':
        name = random.choice(RANDOM_POOL)
        log.debug(f"Random transition selected: {name}")

    cls = REGISTRY.get(name)
    if cls is None:
        log.warning(f"Unknown transition '{name}', falling back to fade")
        cls = FadeTransition

    # Calculate steps from duration and FPS
    steps = max(3, int(duration * TRANSITION_FPS))
    return cls(steps=steps)


__all__ = ['get_transition', 'REGISTRY', 'RANDOM_POOL']

