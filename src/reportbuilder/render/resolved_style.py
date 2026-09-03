"""One place that answers "what does this template say?" — and only one.

Ground, ink, and the title's font/size/colour were each being decided in three
or four places that did not agree:

  * the background was read by `_mpl.chart_background` for charts and again by
    the compositor for text;
  * the foreground by `house_style.furniture_colors`, `_mpl.chart_furniture`
    and `slide_chrome._furniture_px`;
  * the title's font and size by the master's inheritance chain in one renderer
    and by the harvested profile in the other — which is how the same slide came
    out Bebas Neue 30pt in the deck and Arial 14pt in the preview;
  * whether a stated colour was legible, by a threshold invented on the spot,
    which let black through on a 37474F ground.

Every one of those is a question with a single right answer for a given
template. They live here now; the renderers ask rather than decide, and the
chart on a slide agrees with the text beside it because both read the same
function.

Palettes are NOT re-implemented here — `house_style.series_colors` and
`_mpl.template_palette` already are the single source for those. `palette()`
below just names where they live so the next reader does not go looking.
"""
from __future__ import annotations

from dataclasses import dataclass

from reportbuilder.render.house_style import (
    _DARK_LUMINANCE_THRESHOLD,
    _relative_luminance,
    CREAM,
    furniture_colors,
)

# The title size to fall back on when a template states none anywhere. Kept here
# rather than in a renderer so the deck and the preview cannot pick differently.
DEFAULT_TITLE_PT = 18.0


def ground(style) -> str:
    """The slide background this template states, as "#RRGGBB".

    THE definition. `_mpl.chart_background` (charts) and the compositor (text)
    both resolve here, so a chart can never sit on a different ground than the
    text beside it thinks it does.
    """
    bg = (getattr(style, "background", "") or "").strip()
    if not bg:
        return CREAM if CREAM.startswith("#") else f"#{CREAM}"
    return bg if bg.startswith("#") else f"#{bg}"


def furniture(style) -> tuple[str, str, str]:
    """(ink, muted, grid) for this template's ground — house_style's own rule."""
    return furniture_colors(ground(style))


def ink(style) -> str:
    """The foreground this template's ground calls for."""
    return furniture(style)[0]


def is_dark(colour_hex: str) -> bool:
    """The renderer's ONE definition of dark, shared by every colour decision."""
    c = colour_hex if colour_hex.startswith("#") else f"#{colour_hex}"
    return _relative_luminance(c) < _DARK_LUMINANCE_THRESHOLD


def legible_on(colour_hex: str, ground_hex: str) -> bool:
    """Is *colour* readable on *ground*?

    Dark text belongs on a light ground and light text on a dark one — the
    renderer's own threshold, not a difference. A difference cutoff let black
    through on 37474F: it scores 0.267 away and is still invisible, which is
    exactly the headline that disappeared into a customer's own background.
    """
    try:
        return is_dark(colour_hex) != is_dark(ground_hex)
    except Exception:  # noqa: BLE001 — a colour must never fail a render
        return True


@dataclass(frozen=True)
class TitleStyle:
    """How this template draws a slide headline."""

    font: str = ""
    size_pt: float = 0.0
    colour: str = ""
    bold: bool | None = None
    caps: bool = False


def title_colour(stated: str, style) -> str:
    """The colour to draw a headline in: the template's, where it is legible on
    the template's own ground; otherwise the ground's own ink.

    A harvested colour is read off ONE slide of a customer's deck, and a deck
    has light and dark slides both — so the template can genuinely contradict
    itself. Both values here are the template's; this picks the one it did not
    contradict, and invents nothing.
    """
    g = ground(style)
    if stated and legible_on(stated, g):
        return stated if stated.startswith("#") else f"#{stated}"
    return ink(style)


# --------------------------------------------------------------------------- #
# The template spec: decided ONCE per template, never per slide.
# --------------------------------------------------------------------------- #
# Type is sized by how tall it RENDERS, not by the number a template happens to
# state. 30pt of Bebas Neue and 30pt of Arial are not the same size on a slide —
# which is why "use the template's 14pt" looked tiny and "use LibreOffice's 28pt"
# looked oversized, on the same file. Every template's title is sized to the same
# cap height, so decks look like each other whatever font they carry.
#
# Start here and tune by looking: these are the numbers the eye judges, so they
# are meant to be adjusted against rendered slides rather than argued about.
# Lowered from 0.20 / 0.15 on 2026-08-23: the headline crowded the slide, and a
# two-line one came down close to the chart. These are the numbers the eye
# judges, so they are meant to be moved against rendered slides rather than
# argued about — and moving them here moves BOTH renderers, because both size
# their type from this one pair.
TARGET_TITLE_CAP_IN = 0.175
TARGET_SUBTITLE_CAP_IN = 0.132

_MEASURE_PX = 200.0        # measure once, big enough that rounding does not matter


def size_for_cap_height(font_family: str, target_in: float) -> float:
    """The point size at which *font_family* has a cap height of *target_in*.

    Measured from the font file itself (the same resolution the renderers use),
    so a condensed display face and a text face come out looking the same size
    rather than sharing a number.
    """
    try:
        from reportbuilder.render.image.fast_preview import _font

        # `_font` sizes in PIXELS. Measure the cap at a large pixel size and
        # reduce it to a RATIO — cap height per unit of font size — which is
        # dimensionless and so the same in points.
        font = _font(font_family, _MEASURE_PX, bold=False, italic=False)
        box = font.getbbox("H")          # ink box of a capital, not the em box
        cap_ratio = ((box[3] - box[1]) or 1) / _MEASURE_PX
        if cap_ratio <= 0:
            return 0.0
        # A point is 1/72", so a target in inches is target*72 points of CAP,
        # and the font must be that divided by its own cap ratio.
        return round(target_in * 72.0 / cap_ratio, 1)
    except Exception:  # noqa: BLE001 — never fail a render over a font metric
        return 0.0


@dataclass(frozen=True)
class TextSpec:
    font: str = ""
    size_pt: float = 0.0
    colour: str = ""


@dataclass(frozen=True)
class TemplateSpec:
    """Everything a slide needs to know about its template, resolved once."""

    background: str = ""
    ink: str = ""
    muted: str = ""
    title: TextSpec = TextSpec()
    subtitle: TextSpec = TextSpec()


def build_spec(style, title_font: str = "", subtitle_font: str = "") -> TemplateSpec:
    """Resolve the whole of a template's type and colour, once.

    `title_font`/`subtitle_font` come from the template's own chain when the
    caller has walked it; otherwise the harvested profile and the theme fill in.
    """
    ink_hex, muted_hex, _grid = furniture(style)
    profile = getattr(style, "profile", None)
    harvested = getattr(profile, "title", None)

    t_font = (title_font or getattr(harvested, "font", "")
              or getattr(style, "heading_font", "") or "")
    s_font = (subtitle_font or getattr(style, "body_font", "")
              or getattr(style, "heading_font", "") or "")

    # Sized by CAP HEIGHT so a headline looks the same size whatever face the
    # template names — which is right until somebody looking at the result says
    # otherwise. An author's own size is not a starting point to normalise.
    t_size = (getattr(style, "title_size_pt", 0.0)
              or size_for_cap_height(t_font, TARGET_TITLE_CAP_IN))
    s_size = (getattr(style, "subtitle_size_pt", 0.0)
              or size_for_cap_height(s_font, TARGET_SUBTITLE_CAP_IN))

    t_colour = (getattr(style, "title_colour", "")
                or title_colour(getattr(harvested, "colour", "") or "", style))
    return TemplateSpec(
        background=ground(style),
        ink=ink_hex,
        muted=muted_hex,
        title=TextSpec(font=t_font, size_pt=t_size, colour=t_colour),
        subtitle=TextSpec(font=s_font, size_pt=s_size, colour=muted_hex),
    )
