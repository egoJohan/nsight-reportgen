"""nSight house palette, typography, and shared visual constants (REQ-C-24/25/27a).

Provides the centralised colour ramp and font-registration helper used by all
image-mode chart builders.  Import from here — never hard-code hex values in
individual builders.
"""
from __future__ import annotations

import threading as _threading

import matplotlib as _mpl
from matplotlib import font_manager as _fm
from pptx.dml.color import RGBColor

# ---------------------------------------------------------------------------
# Palette — matplotlib hex strings
# ---------------------------------------------------------------------------
CREAM = "#F7F3EC"
INK = "#2B2B2B"
MUTED = "#6E6A63"
TEAL = "#13615E"
TEAL_LT = "#7DB8A6"
RED = "#B23A2E"
RED_LT = "#E08C82"
GRIDC = "#DAD3C7"        # grid / subdued divider colour

# ---------------------------------------------------------------------------
# pptx RGBColor equivalents (for python-pptx textboxes / fills)
# ---------------------------------------------------------------------------
PX_CREAM = RGBColor(0xF7, 0xF3, 0xEC)
PX_INK = RGBColor(0x2B, 0x2B, 0x2B)
PX_TEAL = RGBColor(0x13, 0x61, 0x5E)
PX_MUTED = RGBColor(0x6E, 0x6A, 0x63)
PX_RED = RGBColor(0xB2, 0x3A, 0x2E)

# ---------------------------------------------------------------------------
# Teal ramp — ordered lightest → darkest (used for multi-series charts)
# ---------------------------------------------------------------------------
_TEAL_RAMP: list[str] = [
    "#CFE3E2",   # wave 1 / palest
    "#9CC6C4",   # wave 2
    "#5E9C9A",   # wave 3
    "#13615E",   # wave 4 / current / strongest
]

# ---------------------------------------------------------------------------
# Font registration (lazy, idempotent)
# ---------------------------------------------------------------------------
_FONTS_REGISTERED = False

_LIBERATION_PATHS = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/opentype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/opentype/liberation/LiberationSans-Bold.ttf",
]


_FONTS_LOCK = _threading.Lock()


def register_fonts() -> None:
    """Register Liberation Sans with matplotlib; fall back to DejaVu Sans if absent.

    Idempotent and thread-safe — chart rendering runs on a threadpool, so the
    check-then-set and the shared fontManager / rcParams mutation are guarded by a
    lock to register exactly once per process. REQ-C-25 (consistent typography).
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    with _FONTS_LOCK:
        if _FONTS_REGISTERED:
            return
        for fp in _LIBERATION_PATHS:
            try:
                _fm.fontManager.addfont(fp)
            except Exception:
                pass
        avail = {f.name for f in _fm.fontManager.ttflist}
        if "Liberation Sans" in avail:
            _mpl.rcParams["font.family"] = "Liberation Sans"
        else:
            _mpl.rcParams["font.family"] = "DejaVu Sans"  # graceful fallback
        _FONTS_REGISTERED = True


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def scale_colors(n: int) -> list[str]:
    """*n* colours forming a MONOTONIC light→dark teal gradient.

    For ORDERED scale segments — the Likert/rating levels of a stacked bar
    (disagree→agree). Unlike series_colors (a categorical palette that cycles
    after 4), this interpolates so a 5- or 7-point scale reads as a clean
    gradient with no repeated colour."""
    if n <= 1:
        return [TEAL]
    lo = (0xCF, 0xE3, 0xE2)  # palest teal
    hi = (0x13, 0x61, 0x5E)  # strongest teal
    out: list[str] = []
    for i in range(n):
        t = i / (n - 1)
        r, g, b = (round(lo[k] + (hi[k] - lo[k]) * t) for k in range(3))
        out.append(f"#{r:02X}{g:02X}{b:02X}")
    return out


def series_colors(n: int) -> list[str]:
    """Return *n* hex colour strings from the teal ramp (REQ-C-27a).

    Single series → darkest TEAL (most prominent).
    Multiple series → spread across the ramp, darkest last (= current wave).
    More than 4 series → cycles the ramp.
    """
    if n == 1:
        return [TEAL]
    ramp = _TEAL_RAMP
    if n <= len(ramp):
        # evenly spaced; always include darkest at the end
        indices = [round(i * (len(ramp) - 1) / (n - 1)) for i in range(n)]
        return [ramp[idx] for idx in indices]
    # More series than ramp slots — cycle
    return [ramp[i % len(ramp)] for i in range(n)]
