"""A combo's gridlines and its tick labels are on ONE lattice.

The combo drew gridlines on a fixed 20/40/60/80/100 ladder while its tick
LABELS came from matplotlib's autoscale. On a question topping out at 31 % that
is a single gridline — at 20 — among ticks at every 5, and an axis that ends at
30 with a 31 % bar standing above it.

Every other value axis in the deck goes through `_mpl._value_axis`, which is
also where the "biggest bar is small" fix lives (a chart under ~12 % steps the
ladder down instead of printing "0" and nothing else). The combo never called
it, so it never got that fix either — the same defect, on the one builder the
repair was not applied to.
"""
from __future__ import annotations

import pandas as pd
import pytest
from pptx import Presentation
from pptx.util import Inches

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.render.base import RenderContext, Slot, StyleSpec
from reportbuilder.stats.engine import compute
import reportbuilder.render.image.combo as C

#: Counts giving 3/3/7/11/23/31/22 % — the study that showed the defect.
_COUNTS = [31, 31, 71, 112, 234, 316, 224]
_LEVELS = ["1- Ei lainkaan ylpeä", "2", "3", "4", "5", "6", "7- Erittäin ylpeä"]


def _axis(counts=_COUNTS) -> dict:
    var = Variable(name="q", label="Kuinka ylpeä olet omasta työstäsi?",
                   measurement="nominal", missing_values=[],
                   value_labels=[ValueLabel(value=float(i + 1), label=l)
                                 for i, l in enumerate(_LEVELS[:len(counts)])])
    rows = [{"q": float(i + 1)} for i, n in enumerate(counts) for _ in range(n)]
    model = QuestionModel(
        variables={"q": var},
        questions=[Question(qid="q", text=var.label, kind="single", variables=("q",))])
    spec = ChartSpec(question_ref="q", chart_type="combo", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles())
    series = compute(model.question("q"), spec, pd.DataFrame(rows), model)
    prs = Presentation()
    ctx = RenderContext(slide=prs.slides.add_slide(prs.slide_layouts[6]),
                        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                                  width=Inches(11.6), height=Inches(4.0), name="s1"),
                        style=StyleSpec(), spec=spec, series=series,
                        fmt=spec.number_format)
    found: dict = {}
    original = C.render_png

    def _spy(fig):
        ax = fig.axes[0]
        lo, hi = ax.get_ylim()
        found["ylim"] = (lo, hi)
        found["ticks"] = [float(t) for t in ax.get_yticks() if lo <= t <= hi]
        # An axhline spans the axes in axes-coords and carries one y value.
        found["gridlines"] = sorted(
            {round(float(ln.get_ydata()[0]), 6) for ln in ax.lines
             if len(set(ln.get_ydata())) == 1 and lo <= ln.get_ydata()[0] <= hi})
        found["bar_top"] = max(p.get_height() for p in ax.patches)
        return original(fig)

    C.render_png = _spy
    try:
        C.build_image_combo(ctx)
    finally:
        C.render_png = original
    return found


def test_the_axis_reaches_above_the_tallest_bar():
    got = _axis()
    assert got["ylim"][1] >= got["bar_top"], got


def test_every_gridline_sits_on_a_tick():
    got = _axis()
    stray = [g for g in got["gridlines"]
             if not any(abs(g - t) < 1e-6 for t in got["ticks"])]
    assert stray == [], f"gridlines off the tick lattice: {stray} vs {got['ticks']}"


def test_every_tick_above_zero_carries_a_gridline():
    """One line at 20 among ticks every 5 is what the reader actually saw."""
    got = _axis()
    missing = [t for t in got["ticks"] if t > 0
               and not any(abs(g - t) < 1e-6 for g in got["gridlines"])]
    assert missing == [], f"ticks with no gridline: {missing}"


def test_a_low_range_chart_still_gets_a_usable_ladder():
    """`_value_axis`'s own small-range fix, which the combo never inherited."""
    got = _axis(counts=[10, 12, 14, 16, 18, 20, 910])
    assert len([t for t in got["ticks"] if t > 0]) >= 2, got["ticks"]
