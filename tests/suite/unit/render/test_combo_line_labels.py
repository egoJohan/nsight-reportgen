"""A combo chart labels its line, and the label does not land on a bar's label.

Two series on two scales is the whole point of this chart type, and the line
had no values on it at all — the only way to read it was off the right-hand
axis. Adding them is easy; putting them somewhere legible is the part with a
rule in it, because the line crosses the bars exactly where a reader is trying
to compare the two.
"""
from __future__ import annotations

import pytest

from reportbuilder.render.image.combo import line_label_anchor

pytestmark = pytest.mark.unit

BARS = (0.0, 40.0)      # left axis
LINE = (-10.0, 30.0)    # right axis


def _bar_top_on_line_axis(bar_v: float) -> float:
    return LINE[0] + (bar_v - BARS[0]) / (BARS[1] - BARS[0]) * (LINE[1] - LINE[0])


def test_a_point_well_above_its_bar_is_labelled_above():
    y, above = line_label_anchor(28.0, 5.0, BARS, LINE)
    assert above is True and y == 28.0


def test_a_point_well_below_its_bar_is_labelled_below_the_marker():
    """Nothing above it to avoid — the label hangs under its own point.

    The value used to be -8.0, which is 2 units off the floor of a 40-unit axis
    — close enough that the label was drawn below the axes entirely, and the
    floor added in `test_a_label_never_hangs_below_the_axis` now lifts it. That
    is a different rule about a different problem; 0.0 keeps this test on the
    one it was written for. (2026-09-16)
    """
    y, above = line_label_anchor(0.0, 38.0, BARS, LINE)
    assert above is False and y == 0.0


def test_a_point_just_above_its_bar_is_pushed_under_the_bar_top():
    """The collision this rule exists for: 'below the marker' there is exactly
    where the bar's own label sits."""
    bar_v = 35.0
    top = _bar_top_on_line_axis(bar_v)
    y, above = line_label_anchor(top + 1.0, bar_v, BARS, LINE)
    assert above is False
    assert y < top, "must drop under the bar top, not merely under the marker"


def test_a_point_level_with_its_bar_is_pushed_under_it_too():
    bar_v = 30.0
    top = _bar_top_on_line_axis(bar_v)
    y, above = line_label_anchor(top, bar_v, BARS, LINE)
    assert above is False and y < top


def test_clearance_scales_with_the_axis_not_the_numbers():
    """A line axis in thousands must not get a 0.09-unit clearance — the gap is
    a fraction of the axis, so it stays a visible distance at any scale."""
    bars, line = (0.0, 100.0), (0.0, 40_000.0)
    bar_v = 90.0
    top = line[0] + (bar_v - bars[0]) / (bars[1] - bars[0]) * (line[1] - line[0])
    y, above = line_label_anchor(top, bar_v, bars, line)
    assert above is False
    assert top - y == pytest.approx(40_000.0 * 0.09)


def test_no_bar_means_nothing_to_avoid():
    y, above = line_label_anchor(12.0, None, BARS, LINE)
    assert above is True and y == 12.0


def test_a_label_never_hangs_below_the_axis():
    """Reported on slide 7: "the line label goes on top of the legend".

    Below the axes are the category labels and then the legend, so a label
    anchored near the axis floor and then offset 9pt DOWN lands on them. The
    anchor has to keep a label's worth of room above the floor.
    """
    lo, hi = LINE
    room = (hi - lo) * 0.09
    for v, bar_v in ((-8.0, 38.0), (-9.5, 30.0), (-9.9, 5.0)):
        y, _above = line_label_anchor(v, bar_v, BARS, LINE)
        assert y >= lo + room - 1e-9, (
            f"point {v} anchored at {y}, under the {lo + room} floor — its "
            f"label is drawn below the axes, on the category labels")


def test_the_floor_does_not_lift_a_label_that_has_room():
    """Only the ones that would fall off are moved."""
    y, above = line_label_anchor(28.0, 5.0, BARS, LINE)
    assert above is True and y == 28.0


def test_a_degenerate_bar_axis_does_not_divide_by_zero():
    y, above = line_label_anchor(12.0, 5.0, (7.0, 7.0), LINE)
    assert above is True and y == 12.0
