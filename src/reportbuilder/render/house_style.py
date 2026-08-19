"""nSight house palette, typography, and shared visual constants (REQ-C-24/25/27a).

Provides the centralised colour ramp and font-registration helper used by all
image-mode chart builders.  Import from here — never hard-code hex values in
individual builders.
"""
from __future__ import annotations

import contextlib as _contextlib
import threading as _threading

import matplotlib as _mpl
from matplotlib import font_manager as _fm
from matplotlib.colors import to_rgb
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
BLUE = "#35618E"        # categorical accent (muted, cream-friendly)
BLUE_LT = "#86A9CE"
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

# The chart font is a SETTING, deliberately separate from the template's font.
# A brand display face can be wide, and chart text is mostly long category
# labels — letting an admin pick a narrower face buys legible labels that would
# otherwise be truncated or rotated. Empty means the house default.
_DEFAULT_CHART_FONT = "Liberation Sans"
_configured_family = ""
_applied_family = ""


def _addfont_dir(directory) -> None:
    """Let matplotlib see fonts installed after it was first imported.

    Fonts an admin uploads land on disk while the process is running.
    fontconfig picks them up on the next fc-cache, but matplotlib's own list is
    built once, so without this a freshly installed font is selectable in the
    UI and silently ignored by every chart.
    """
    try:
        for path in sorted(directory.glob("*")):
            if path.suffix.lower() in (".ttf", ".otf"):
                with _contextlib.suppress(Exception):
                    _fm.fontManager.addfont(str(path))
    except (OSError, AttributeError):
        pass


def available_chart_fonts() -> list[str]:
    """Families matplotlib can actually draw with, for the settings picker."""
    register_fonts()
    return sorted({f.name for f in _fm.fontManager.ttflist})


def use_chart_font(family: str) -> str:
    """Choose the family for chart text. Returns the one actually applied.

    A configured font that matplotlib cannot find falls back to the house
    default rather than to matplotlib's own DejaVu, so an unavailable setting
    degrades to a deliberate choice instead of an accidental one.
    """
    global _configured_family, _applied_family
    wanted = (family or "").strip()
    if wanted == _configured_family and _applied_family:
        # Already active. Called on EVERY render and preview, so the unchanged
        # case must cost nothing: re-registering meant rescanning the font
        # directory and rebuilding matplotlib's 244-family list per chart,
        # which is what made previews slow.
        return _applied_family
    with _FONTS_LOCK:
        _configured_family = wanted
    _applied_family = ""      # a real change: re-apply on the next figure
    register_fonts()
    return _applied_family


def current_chart_font() -> str:
    """The family charts are drawing with right now."""
    register_fonts()
    return _applied_family


def register_fonts() -> None:
    """Make the configured chart font active for matplotlib.

    Idempotent and thread-safe — chart rendering runs on a threadpool, so the
    shared fontManager / rcParams mutation is guarded by a lock. Re-applies
    only when the wanted family differs from the applied one, so the common
    case stays a single comparison. REQ-C-25 (consistent typography).
    """
    global _FONTS_REGISTERED, _applied_family
    wanted = _configured_family or _DEFAULT_CHART_FONT
    if _FONTS_REGISTERED and _applied_family == wanted:
        return
    with _FONTS_LOCK:
        if _FONTS_REGISTERED and _applied_family == wanted:
            return
        if not _FONTS_REGISTERED:
            for fp in _LIBERATION_PATHS:
                with _contextlib.suppress(Exception):
                    _fm.fontManager.addfont(fp)
        # Uploaded fonts are re-scanned on every change: the family being asked
        # for may have arrived since the last figure was drawn.
        from reportbuilder.render.fonts import FONT_DIR
        _addfont_dir(FONT_DIR)

        avail = {f.name for f in _fm.fontManager.ttflist}
        for candidate in (wanted, _DEFAULT_CHART_FONT, "DejaVu Sans"):
            if candidate in avail:
                _mpl.rcParams["font.family"] = candidate
                _applied_family = candidate
                break
        else:
            _applied_family = _mpl.rcParams["font.family"]
        _FONTS_REGISTERED = True


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def ramp_from(accent: str, steps: int = 4) -> list[str]:
    """A light→dark ramp built from one colour, by blending it toward white.

    The house teal ramp IS this shape — #13615E at 80/60/35/0% toward white is
    #CFE3E2/#9CC6C4/#5E9C9A/#13615E to within a couple of levels — so a template
    that states its accent gets ramps in ITS colour by the same construction,
    and the house teal remains what a template without one produces.

    Needed because a template whose design lives on its SLIDES does not state
    its brand in its theme: `attendo_agent_deck.pptx` is cream and teal on every
    slide while its theme is stock Office blue.
    """
    accent = (accent or "").lstrip("#")
    if len(accent) != 6:
        return list(_TEAL_RAMP)
    try:
        r, g, b = (int(accent[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return list(_TEAL_RAMP)
    mixes = [0.80, 0.60, 0.35, 0.0][-steps:] if steps <= 4 else \
        [0.80 - i * (0.80 / (steps - 1)) for i in range(steps)]
    out = []
    for m in mixes:
        out.append("#%02X%02X%02X" % tuple(
            round(c + (255 - c) * m) for c in (r, g, b)))
    return out


def scale_colors(n: int, accent: str = "") -> list[str]:
    """*n* colours forming a MONOTONIC light→dark teal gradient.

    For ORDERED scale segments — the Likert/rating levels of a stacked bar
    (disagree→agree). Unlike series_colors (a categorical palette that cycles
    after 4), this interpolates so a 5- or 7-point scale reads as a clean
    gradient with no repeated colour."""
    ramp = ramp_from(accent) if accent else _TEAL_RAMP
    if n <= 1:
        return [ramp[-1]]
    lo = tuple(int(ramp[0].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    hi = tuple(int(ramp[-1].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    out: list[str] = []
    for i in range(n):
        t = i / (n - 1)
        r, g, b = (round(lo[k] + (hi[k] - lo[k]) * t) for k in range(3))
        out.append(f"#{r:02X}{g:02X}{b:02X}")
    return out


# After the teal ramp, add whole HUE FAMILIES — each its own light→dark gradient,
# same approach as the teal ramp — so many-category charts (pie / clustered bars /
# line / radar) stay legible instead of repeating teal shades. Order per house
# direction: teal, then blue, then red (2026-07-10).
_BLUE_RAMP: list[str] = ["#C4D6E8", "#86A9CE", "#5580AC", "#35618E"]
_RED_RAMP: list[str] = ["#F0CBC6", "#E08C82", "#C55A4C", "#B23A2E"]
# Full categorical palette: teal family, then blue family, then red family.
_CATEGORICAL: list[str] = _TEAL_RAMP + _BLUE_RAMP + _RED_RAMP


def contrast_ink(color) -> str:
    """Label colour for text placed ON a coloured fill: white on dark fills, INK on
    light — so a percentage stays legible on any slice/segment/bar, including the
    darkest teal/blue/red. Accepts a hex string or an (r,g,b[,a]) tuple. (REQ-C-27a)"""
    r, g, b = to_rgb(color)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#FFFFFF" if lum < 0.55 else INK


def series_colors(n: int, palette: list[str] | None = None,
                  accent: str = "") -> list[str]:
    """Return *n* distinct hex colour strings for CATEGORICAL series (REQ-C-27a).

    *palette* is the template's own accent colours when one is in play, so a
    deck built on Attendo's template gets Attendo's navy and green rather than
    nSight teal. accent1-6 is what PowerPoint's own charts use for series, so
    taking them in order matches what the client sees elsewhere in their deck.
    Without a palette the house ramps below apply unchanged.

    Single series → darkest TEAL (most prominent).
    2–4 series → spread across the teal ramp, darkest last (= current wave).
    5+ series → teal ramp, then a blue gradient, then a red gradient (each family a
    light→dark ramp) so no colour repeats (was: cycled the 4-colour ramp → duplicate
    colours for different labels).
    """
    if palette:
        if n <= len(palette):
            return list(palette[:n])
        # More series than the template declares: repeat the accents rather than
        # mixing in house colours, which would look like a rendering error on a
        # branded deck.
        return [palette[i % len(palette)] for i in range(n)]
    ramp = ramp_from(accent) if accent else _TEAL_RAMP
    if n == 1:
        return [ramp[-1]]
    if n <= len(ramp):
        # evenly spaced; always include darkest at the end
        indices = [round(i * (len(ramp) - 1) / (n - 1)) for i in range(n)]
        return [ramp[idx] for idx in indices]
    categorical = ramp + _BLUE_RAMP + _RED_RAMP
    if n <= len(categorical):
        return categorical[:n]
    # Beyond the palette (11+ categories — rare): interpolate extra shades of the
    # lead colour so the tail never exactly repeats an earlier colour.
    out = list(categorical)
    for i in range(len(categorical), n):
        out.append(scale_colors(n, accent)[i])
    return out[:n]
