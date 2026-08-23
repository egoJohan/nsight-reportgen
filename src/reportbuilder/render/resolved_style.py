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
