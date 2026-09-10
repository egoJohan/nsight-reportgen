"""When the numbers on a stacked bar collide, they get smaller — and only then.

The percentages on a crowded cross-tab were printed through each other ("2 4%"
on the customer's slide). Moving them is what you would try first, and it is
what failed: two attempts at nudging callouts clear of the in-bar numbers made
it WORSE — six overlapping pairs became fifteen — because a callout pushed
clear overflows the axis and the overflow correction drags the whole run back
onto what it stepped over.

Shrinking cannot do that. It changes type size and never a position, so the
worst case is smaller numbers, and a panel whose numbers already sit clear is
left exactly as it was. That last property is the one worth guarding: this runs
on every stacked bar, and most of them have no collision to fix.

It reduces rather than eliminates — measured on the customer's own data, six
pairs down to four. The rest need the callout's VERTICAL placement rethought,
which is a separate piece of work. (Johan, 2026-09-10)
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import pytest

from reportbuilder.render.image._mpl import _new_agg_figure
from reportbuilder.render.image.bars import _VALUE_GID, shrink_values_until_clear


def _panel(positions):
    """A bare axes carrying value labels at the given (x, y) points."""
    fig = _new_agg_figure(6.0, 3.0)
    ax = fig.subplots()
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 10)
    for x, y in positions:
        ax.text(x, y, "44 %", ha="center", va="center", fontsize=9.0,
                fontweight="bold", gid=_VALUE_GID)
    return fig, ax


def _sizes(ax):
    return [t.get_fontsize() for t in ax.texts if t.get_gid() == _VALUE_GID]


def test_labels_that_do_not_collide_are_left_alone():
    """The guard that matters: this runs on every stacked bar."""
    fig, ax = _panel([(10, 5), (50, 5), (90, 5)])
    before = _sizes(ax)

    assert shrink_values_until_clear(fig, ax) is None
    assert _sizes(ax) == before


def test_labels_printed_on_top_of_each_other_get_smaller():
    fig, ax = _panel([(50, 5), (52, 5)])
    before = _sizes(ax)

    settled = shrink_values_until_clear(fig, ax)

    assert settled is not None
    assert max(_sizes(ax)) < max(before)


def test_it_never_shrinks_past_the_floor():
    """Below this a number is decoration, not a figure anyone reads."""
    from reportbuilder.render.image.bars import _VALUE_MIN_PT

    fig, ax = _panel([(50, 5), (50, 5), (50, 5), (50, 5)])
    shrink_values_until_clear(fig, ax)
    assert min(_sizes(ax)) >= _VALUE_MIN_PT * 0.99


def test_a_single_label_is_never_touched():
    fig, ax = _panel([(50, 5)])
    assert shrink_values_until_clear(fig, ax) is None
    assert _sizes(ax) == [9.0]


def test_it_stops_as_soon_as_they_are_clear():
    """Not shrunk to the floor regardless — one step is often enough, and the
    numbers should stay as large as they can."""
    fig, ax = _panel([(50, 5), (56, 5)])
    from reportbuilder.render.image.bars import _VALUE_MIN_PT

    settled = shrink_values_until_clear(fig, ax)
    # a step or two clears this pair; it must not march on to the floor
    assert settled is not None
    assert _VALUE_MIN_PT < settled < 9.0
