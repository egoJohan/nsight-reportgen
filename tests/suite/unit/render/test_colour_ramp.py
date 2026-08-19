"""Chart colours for a template that states only one of them.

A client template often gives us a single colour — the bar beside its titles,
the rule under them — and a chart needs four. The house teal ramp is that one
colour blended toward white, so the same construction serves any brand and
reproduces the house ramp when no brand applies.
"""
from __future__ import annotations

from reportbuilder.render.house_style import (
    _TEAL_RAMP, ramp_from, scale_colors, series_colors,
)
from reportbuilder.render.style_spec import states_a_brand


def _rgb(hex6):
    h = hex6.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def test_the_house_ramp_is_this_construction():
    """Within a few levels per channel — i.e. the house ramp was made this way,
    so a template without a brand still gets exactly the house look."""
    for made, house in zip(ramp_from("13615E"), _TEAL_RAMP):
        for a, b in zip(_rgb(made), _rgb(house)):
            assert abs(a - b) <= 12, f"{made} vs {house}"


def test_the_ramp_ends_on_the_accent_itself():
    assert ramp_from("FF5000")[-1] == "#FF5000"
    assert series_colors(1, accent="FF5000") == ["#FF5000"]


def test_a_scale_gradient_follows_the_accent_too():
    """An ordered Likert scale is one hue light→dark; on a client template it
    has to be THEIR hue."""
    colours = scale_colors(5, "FF5000")
    assert colours[-1] == "#FF5000"
    assert len(set(colours)) == 5


def test_no_accent_is_the_house_teal():
    assert series_colors(1) == ["#13615E"]
    assert ramp_from("") == _TEAL_RAMP
    assert ramp_from("not-a-colour") == _TEAL_RAMP


class TestWhatCountsAsABrand:
    def test_untouched_office_accents_are_not_a_brand(self):
        """Both of PowerPoint's own defaults. A file nobody restyled tells us
        nothing, and using its accents paints a client deck Office blue."""
        assert not states_a_brand(["4F81BD", "C0504D", "9BBB59", "8064A2",
                                   "4BACC6", "F79646"])
        assert not states_a_brand(["5B9BD5", "ED7D31", "A5A5A5", "FFC000",
                                   "4472C4", "70AD47"])

    def test_a_real_theme_is(self):
        assert states_a_brand(["122D49", "7EA96C", "3D7098", "A8C4D8",
                               "D9E2EC", "F0F4F8"])

    def test_no_theme_at_all_is_not(self):
        assert not states_a_brand([])
