"""One rule for "can this headline be read on this ground".

The compositor that draws the PREVIEW asks `legible_on`. The builder that draws
the DECK had its own luminance-difference threshold, and the two disagreed:
black harvested from a customer's deck, on the ground the same template states,
passed the builder's rule and failed the compositor's — so the preview showed a
white headline and the exported deck a black one, invisible, on every slide.

Two expressions of one rule is one too many; this keeps them from drifting.
"""
from __future__ import annotations

from reportbuilder.render.image.slide_chrome import title_colour_for
from reportbuilder.render.resolved_style import legible_on


class _Harvested:
    def __init__(self, colour):
        self.colour = colour


class _Style:
    def __init__(self, background, title_colour=""):
        self.background = background
        self.title_colour = title_colour


def _hex(colour) -> str:
    return f"{colour[0]:02X}{colour[1]:02X}{colour[2]:02X}"


def test_black_on_a_dark_ground_is_not_used():
    got = title_colour_for(_Harvested("000000"), _Style("37474F"))
    assert _hex(got) != "000000"
    assert legible_on(_hex(got), "#37474F"), _hex(got)


def test_a_legible_harvest_is_kept():
    got = title_colour_for(_Harvested("FFFFFF"), _Style("37474F"))
    assert _hex(got) == "FFFFFF"


def test_the_two_rules_agree_wherever_they_are_both_asked():
    ground = "#37474F"
    for colour in ("000000", "FFFFFF", "112233", "EEEEEE", "808080"):
        chosen = _hex(title_colour_for(_Harvested(colour), _Style("37474F")))
        if chosen == colour:
            assert legible_on(colour, ground), colour


def test_an_author_s_own_colour_is_never_second_guessed():
    got = title_colour_for(_Harvested("FFFFFF"), _Style("37474F", title_colour="000000"))
    assert _hex(got) == "000000"
