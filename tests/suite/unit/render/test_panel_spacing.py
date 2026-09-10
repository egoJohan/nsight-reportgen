"""Side-by-side panels get clear air between them.

"Kaaviot ovat tässä hieman liian lähekkäin. Voisiko kaavioiden välille luoda
enemmän tilaa?" — two panels on one slide, and the right-hand panel's category
labels ("18-24-vuotias") sat almost against the left-hand panel's bars.

The gap was sized as `label width + _LABEL_PAD_IN`, and matplotlib draws a
panel's labels immediately left of its own axes — so the whole gap was filled
by the labels and the only CLEAR space was that 0.12" pad. Wide enough not to
overlap, which is what the arithmetic was solving for, and far too tight to
read as two separate charts.

A minimum separation is now added on top of whatever the labels need, so the
gap is "room for the labels, plus air". (Johan, 2026-09-10)
"""
from __future__ import annotations

import pytest

from reportbuilder.render.image.bars import (
    _LABEL_PAD_IN, _MIN_PANEL_GAP_IN, _side_by_side_layout,
)


def _gap_in(fig_w_in: float, n_panels: int, left_lbl: float, gap_lbl: float) -> float:
    """The inches between one panel's right edge and the next panel's left."""
    _l, _r, wspace, plot_w = _side_by_side_layout(fig_w_in, n_panels, left_lbl, gap_lbl)
    return wspace * plot_w


def test_labelled_panels_get_air_beyond_the_label_block():
    """The reported case: a wide label in the gap ate all of it."""
    gap = _gap_in(13.3, 2, left_lbl=0.9, gap_lbl=0.9)
    clear = gap - 0.9                      # what is left once the labels are in
    assert clear >= _MIN_PANEL_GAP_IN, f"only {clear:.2f}in of clear space"


def test_panels_with_no_labels_in_the_gap_are_still_separated():
    """A shared-y-axis pair draws no label in the gap at all, and used to get
    almost nothing — two plots touching read as one chart."""
    assert _gap_in(13.3, 2, left_lbl=0.9, gap_lbl=0.0) >= _MIN_PANEL_GAP_IN


def test_three_panels_each_get_the_same_air():
    gap = _gap_in(13.3, 3, left_lbl=0.8, gap_lbl=0.8)
    assert gap - 0.8 >= _MIN_PANEL_GAP_IN


def test_a_single_panel_loses_no_width_to_a_gap():
    """There is no neighbour to separate from, so the whole span is the plot.
    (`wspace` is meaningless with one panel — matplotlib's default is returned
    and never used, so the gap has to be read off the width, not off it.)"""
    left, right, _wspace, plot_w = _side_by_side_layout(13.3, 1, 0.9, 0.9)
    assert plot_w == pytest.approx((right - left) * 13.3, abs=0.01)


def test_the_panels_still_get_most_of_the_width():
    """Air between panels must not be bought by squeezing them to nothing."""
    _l, _r, _w, plot_w = _side_by_side_layout(13.3, 2, 0.9, 0.9)
    assert plot_w * 2 > 13.3 * 0.55, f"panels only {plot_w:.2f}in each"


def test_the_gap_grows_with_the_labels_not_instead_of_them():
    """A wider label still gets its room — the minimum is added, not a cap."""
    narrow = _gap_in(13.3, 2, 0.9, 0.4)
    wide = _gap_in(13.3, 2, 0.9, 1.6)
    assert wide > narrow + 1.0


def test_no_layout_changes_its_mind_about_stacking():
    """The gap and the side-by-side DECISION come from the same function, so
    simply adding air would restack panels that were fine. Measured before the
    clamp: three three-panel cases flipped."""
    from reportbuilder.render.image.bars import (
        _LABEL_PAD_IN, _MIN_HGUTTER_PLOT_IN, _RIGHT_MARGIN_IN,
    )

    for fig_w in (9.0, 11.0, 13.3, 16.0):
        for n in (2, 3, 4):
            for lbl in (0.0, 0.4, 0.8, 1.2, 1.8, 2.4):
                span = (1.0 - _RIGHT_MARGIN_IN / fig_w) * fig_w - (lbl + _LABEL_PAD_IN)
                old_plot = (span - (n - 1) * (lbl + _LABEL_PAD_IN)) / n
                _l, _r, wspace, new_plot = _side_by_side_layout(fig_w, n, lbl, lbl)
                assert (old_plot >= _MIN_HGUTTER_PLOT_IN) == \
                    (new_plot >= _MIN_HGUTTER_PLOT_IN), (
                        f"{fig_w}in / {n} panels / {lbl}in label: "
                        f"{old_plot:.2f} -> {new_plot:.2f} crossed the threshold")


def test_a_crowded_layout_keeps_the_old_gap_rather_than_stacking():
    """When the air does not fit, the panels were already at their narrowest."""
    _l, _r, wspace, plot_w = _side_by_side_layout(9.0, 3, 0.4, 0.4)
    gap = wspace * plot_w
    assert gap >= 0.4 + _LABEL_PAD_IN - 0.01, "labels must still have their room"
