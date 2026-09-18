"""A layout that states its own background is drawn on THAT ground.

Reported on Alflorex_template.pptx: switching the layout to "Sisältö_tumma2"
turned the slide dark and left the text dark on it. ("only the background
changes to dark. The text color is also dark")

The slide really did go dark — LibreOffice renders the layout's own
`<p:bg>` — but nSight never read it. `template_check` takes the background
from the THEME's lt1 and `style_spec` consulted the profile's only for a
design-on-slides template, so a layout-based one was always described as
light. Everything derived from the ground then came out for a light slide:
ink, muted, grid, and the contrast rule that decides a label's colour.

In this file layout 19 states `srgbClr 31415A` outright while layout 30
inherits `schemeClr bg1` (lt1, FFFFFC) — the same template, two grounds.
"""
from __future__ import annotations

import pathlib

import pytest

from reportbuilder.render.resolved_style import furniture, is_dark
from reportbuilder.render.style_spec import load_style_spec

_TEMPLATE = pathlib.Path("work/verify/tmp/tplcheck/biocodex.pptx")
_DARK_LAYOUT, _LIGHT_LAYOUT = 19, 30


@pytest.fixture
def template():
    if not _TEMPLATE.exists():
        pytest.skip(f"{_TEMPLATE} not available locally")
    return str(_TEMPLATE)


def test_a_dark_layout_reports_its_own_ground(template):
    style = load_style_spec(template, force_layout=_DARK_LAYOUT)
    assert (style.background or "").lstrip("#").upper() == "31415A"


def test_a_light_layout_is_unchanged(template):
    style = load_style_spec(template, force_layout=_LIGHT_LAYOUT)
    assert (style.background or "").lstrip("#").upper() == "FFFFFC"


def test_the_two_layouts_do_not_describe_the_same_ground(template):
    dark = load_style_spec(template, force_layout=_DARK_LAYOUT).background
    light = load_style_spec(template, force_layout=_LIGHT_LAYOUT).background
    assert dark != light


def test_the_ink_flips_on_a_dark_layout(template):
    """The whole point: text has to be legible on the ground it lands on."""
    style = load_style_spec(template, force_layout=_DARK_LAYOUT)
    assert is_dark(style.background), "the ground is not recognised as dark"
    ink, _muted, _grid = furniture(style)
    assert not is_dark(ink), f"dark ink {ink} on a dark ground"


# ── and the colours that layout writes its own text in ──────────────────────
#
# Johan, 2026-09-18: "Correct the coloring." Deriving a legible ink from the
# ground is right when nobody has said — but this template says. Layout 19
# writes its title and content in `schemeClr accent2` (FAEA90) and layout 30 in
# `tx2` (31415A), and we were drawing white and 2B2B2B instead: legible, and
# not theirs.

def test_the_chart_text_takes_the_layouts_own_colour(template):
    dark = load_style_spec(template, force_layout=_DARK_LAYOUT)
    light = load_style_spec(template, force_layout=_LIGHT_LAYOUT)
    assert dark.chart_text_colour == "FAEA90"      # accent2
    assert light.chart_text_colour == "31415A"     # tx2 -> dk2


def test_the_footer_takes_the_layouts_own_colour(template):
    dark = load_style_spec(template, force_layout=_DARK_LAYOUT)
    assert (dark.footer_colour or "").upper() == "FAEA90"


def test_an_accent_scheme_colour_resolves(template):
    """`accent2` has to reach the theme: reading only lt1/dk1/lt2/dk2 left the
    dark layout with no colour at all and fell back to the derived ink."""
    from reportbuilder.render.style_spec import _theme_colours
    from pptx import Presentation

    theme = _theme_colours(Presentation(template))
    assert theme.get("accent2") == "FAEA90"
    assert theme.get("dk2") == "31415A"
