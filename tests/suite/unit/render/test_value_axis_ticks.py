"""A percentage axis has gridlines, whatever the size of the biggest bar.

25 departments, none above 5%: the axis was drawn to 10% — its own floor — and
the gridlines came off a fixed 0/20/40/60/80/100 ladder, of which exactly one
rung fell inside. The chart read "0" and nothing else, so no bar could be
measured against anything.

The ladder stays for the ordinary case, where its five rungs are what a reader
expects. It steps down only when fewer than three of them land on the axis,
which is the range where it had stopped saying anything. (Johan, 2026-09-16)
"""
from __future__ import annotations

import pytest

from reportbuilder.render.image._mpl import _value_axis

pytestmark = pytest.mark.unit


def _ticks(max_val: float) -> list[float]:
    return _value_axis(max_val, "pct")[1]


def test_a_chart_of_small_shares_still_has_gridlines():
    """The defect, exactly: the biggest bar is 5.4%."""
    assert len(_ticks(5.4)) >= 3


def test_the_gridlines_reach_the_top_of_the_axis():
    ax_max, ticks = _value_axis(5.4, "pct")
    assert ticks[0] == 0
    assert ticks[-1] == pytest.approx(ax_max)


def test_a_quarter_scale_chart_gets_a_finer_ladder():
    ax_max, ticks = _value_axis(25.0, "pct")
    assert ticks == [0, 5, 10, 15, 20, 25]
    assert ticks[-1] <= ax_max


def test_the_ordinary_ladder_is_untouched():
    """Most charts have a bar past 40%, and their axis must not change: these
    are the gridlines every existing deck was drawn against."""
    assert _ticks(96.0) == [0, 20, 40, 60, 80, 100]
    assert _ticks(45.0) == [0, 20, 40]


def test_a_count_axis_is_not_affected():
    """Counts and means never used the percentage ladder."""
    top, ticks = _value_axis(600.0, "count")
    assert ticks[-1] == pytest.approx(top) and len(ticks) >= 4
