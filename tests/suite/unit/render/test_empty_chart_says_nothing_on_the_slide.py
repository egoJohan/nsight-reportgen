"""A slide with nothing to chart draws a blank space, not a message.

"No data to show" was printed in the middle of the chart area, in English, on a
deck handed to a Finnish-speaking client. It is the same class of mistake as the
omission clause removed from the footer the same day: what a slide could not
show is a warning to its AUTHOR, raised in the editor on the warning button and
the slide-item icon, not a line on the client's slide.

So the placeholder stays — the slot keeps its one picture, and the builder still
cannot crash — but it says nothing. The author is told instead, over the
`X-Chart-Empty` preview header. (Johan, 2026-09-16)
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import pytest

from reportbuilder.render.image import _mpl
from suite._helpers import make_ctx, assert_single_picture
from suite.integration.render._series import empty_series

pytestmark = pytest.mark.unit


def _figure_texts(ctx, **kw) -> list[str]:
    """Every string the placeholder figure draws."""
    seen: list[str] = []
    original = _mpl.render_png

    def spy(fig, *a, **k):
        seen.extend(t.get_text() for ax in fig.axes for t in ax.texts)
        return original(fig, *a, **k)

    _mpl.render_png = spy
    try:
        _mpl.render_empty_chart(ctx, **kw)
    finally:
        _mpl.render_png = original
    return [t for t in seen if t.strip()]


def test_the_placeholder_carries_no_message():
    _prs, _slide, _slot, ctx = make_ctx("vertical_bar", empty_series())
    assert _figure_texts(ctx) == []


def test_the_slot_still_gets_its_picture():
    """The count of pictures per slot is checked by the deck; a placeholder that
    stopped drawing would fail that check as surely as a crash."""
    _prs, slide, slot, ctx = make_ctx("vertical_bar", empty_series())
    _mpl.render_empty_chart(ctx)
    assert_single_picture(slide, slot)
