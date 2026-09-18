"""The chart starts BELOW the headline and its question, on every template.

Reported CRITICAL: "Kysymysteksti näkyy nyt graafien päällä, graafien sijainti
tulee muuttaa hieman alemmas sivulla" — the question text was drawn behind the
bars, on several different studies.

The rule already existed for templates whose chart area comes from a LAYOUT
placeholder: push the content box below the title as the title actually falls,
because our headline runs longer than the customer's own and the question needs
somewhere to go. `_resolve_slot` never applied it to a template that defines a
NAMED slot — it returned that slot untouched on its first line. Biocodex's
template names a slot starting at 1.90in while its title band runs to 2.13in,
so the chart began inside the header on 87 of 98 slides and the question text
landed underneath it.

One helper, used by both paths, so the two can never disagree again.
"""
from __future__ import annotations

from pptx.util import Inches

from reportbuilder.render.deck import lowered_for_header

_TOP = int(Inches(1.90))          # Biocodex's named slot
_HEIGHT = int(Inches(3.10))


class _Title:
    """The fields `harvested_title_box` / `fit_title_size` read off a profile."""

    def __init__(self, top, height, positioned=True):
        self.top, self.height, self.positioned = top, height, positioned
        self.left, self.width = int(Inches(0.5)), int(Inches(9.0))
        self.size_pt, self.size_locked = 24.0, False
        self.line_spacing, self.font, self.caps = 1.25, "Liberation Sans", False
        self.bold, self.align, self.colour = True, "left", "2B2B2B"


def _profile(top_in, height_in, positioned=True):
    class P:
        title = _Title(int(Inches(top_in)), int(Inches(height_in)), positioned)
    return P()


def test_a_tall_header_pushes_the_chart_down():
    """The reported case: title band to 2.13in over a slot starting at 1.90in."""
    top, height = lowered_for_header(_TOP, _HEIGHT, _profile(0.30, 1.83), "Otsikko")
    assert top > int(Inches(2.13)), "the chart still starts inside the title band"
    # The bottom edge does not move — the customer's margin is kept.
    assert top + height == _TOP + _HEIGHT


def test_room_is_left_between_the_header_and_the_chart():
    """Not flush against the title: the QUESTION goes in that gap."""
    top, _h = lowered_for_header(_TOP, _HEIGHT, _profile(0.30, 1.83), "Otsikko")
    assert top - int(Inches(2.13)) >= int(Inches(0.5))


def test_a_slot_that_already_clears_the_header_is_untouched():
    top, height = lowered_for_header(_TOP, _HEIGHT, _profile(0.30, 0.60), "Otsikko")
    assert (top, height) == (_TOP, _HEIGHT)


def test_an_authored_content_area_is_never_moved():
    """An author dragged that rectangle while watching the result."""
    top, height = lowered_for_header(_TOP, _HEIGHT, _profile(0.30, 1.83), "Otsikko",
                                     content_is_authored=True)
    assert (top, height) == (_TOP, _HEIGHT)


def test_no_profile_leaves_the_slot_alone():
    assert lowered_for_header(_TOP, _HEIGHT, None, "Otsikko") == (_TOP, _HEIGHT)


def test_an_unpositioned_title_leaves_the_slot_alone():
    p = _profile(0.30, 1.83, positioned=False)
    assert lowered_for_header(_TOP, _HEIGHT, p, "Otsikko") == (_TOP, _HEIGHT)


def test_the_chart_keeps_a_usable_height_even_under_a_huge_header():
    _top, height = lowered_for_header(_TOP, _HEIGHT, _profile(0.30, 4.50), "Otsikko")
    assert height >= int(Inches(1.0))
