"""A chart with ONE category does not label it under the axis.

A mean chart of a scale measure has exactly one "category" — the variable
itself — and its bars are the classifier's groups, named in the legend. The
lone tick label under the axis is therefore the question again, already the
slide's subtitle, printed rotated 30° where an axis title would sit. Reported
as "vaaka-akselille tulee otsikko vaikka määrityksen mukaan ei pitäisi tulla":
the X axis title field was empty, and it was not an axis title at all.

Nothing is lost. Every bar stands over that same tick, so it distinguishes
none of them, and it names what the subtitle already names. Two or more
categories keep their labels — there the tick is the only thing saying which
bar is which. (Johan, 2026-09-08)
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
import reportbuilder.render.image.bars as B

_GROUPS = ["Suuressa", "Keskisuuressa", "Pienessä"]


def _axis_text(*, categories: int, chart_type="vertical_bar",
               statistic: str | None = None, hide_empty=False) -> dict:
    """Render and report what the category axis ended up carrying."""
    measure = Variable(name="TulonlähteidenMuutos", label="TulonlähteidenMuutos",
                       measurement="scale", value_labels=[], missing_values=[])
    opts = Variable(name="mielipide", label="Mielipide", measurement="nominal",
                    missing_values=[],
                    value_labels=[ValueLabel(value=float(i + 1), label=f"Vaihtoehto {i+1}")
                                  for i in range(categories)])
    koko = Variable(name="koko", label="Asuinpaikan koko", measurement="nominal",
                    missing_values=[],
                    value_labels=[ValueLabel(value=float(i + 1), label=g)
                                  for i, g in enumerate(_GROUPS)])
    rows = [{"TulonlähteidenMuutos": 5.0 + (i % 9) * 0.4,
             "mielipide": float(i % max(categories, 1) + 1),
             "koko": float(i % len(_GROUPS) + 1)} for i in range(300)]
    # one category -> the scale measure charted as a mean; several -> a normal question
    qid, stat = ("tlm", "mean") if categories == 1 else ("mielipide", "pct")
    if statistic is not None:
        qid, stat = "mielipide", statistic
    model = QuestionModel(
        variables={"TulonlähteidenMuutos": measure, "mielipide": opts, "koko": koko},
        questions=[Question(qid="tlm", text="TulonlähteidenMuutos", kind="single",
                            variables=("TulonlähteidenMuutos",)),
                   Question(qid="mielipide", text="Mielipide", kind="single",
                            variables=("mielipide",)),
                   Question(qid="koko", text="Asuinpaikan koko", kind="single",
                            variables=("koko",))])
    spec = ChartSpec(question_ref=qid, chart_type=chart_type, statistic=stat,
                     classifying_var="koko", number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles(),
                     show_empty_categories=not hide_empty)
    series = compute(model.question(qid), spec, pd.DataFrame(rows), model)
    prs = Presentation()
    ctx = RenderContext(slide=prs.slides.add_slide(prs.slide_layouts[6]),
                        slot=Slot(slide_index=0, left=Inches(1), top=Inches(1),
                                  width=Inches(8), height=Inches(4.5), name="s1"),
                        style=StyleSpec(), spec=spec, series=series,
                        fmt=spec.number_format)
    caught: dict = {}
    original = B.render_png

    def _spy(fig):
        ax = fig.axes[0]
        caught["n_categories"] = len(series.categories)
        caught["xlabel"] = ax.get_xlabel()
        caught["xticks"] = [t.get_text() for t in ax.get_xticklabels() if t.get_text()]
        caught["yticks"] = [t.get_text() for t in ax.get_yticklabels() if t.get_text()]
        return original(fig)

    B.render_png = _spy
    try:
        (B.build_image_column if chart_type == "vertical_bar"
         else B.build_image_bar)(ctx)
    finally:
        B.render_png = original
    return caught


def test_the_lone_category_is_not_printed_under_the_bars():
    got = _axis_text(categories=1)
    assert got["n_categories"] == 1
    assert got["xlabel"] == "", "an axis TITLE appeared, which is a separate fault"
    assert "TulonlähteidenMuutos" not in got["xticks"], got["xticks"]


def test_several_categories_keep_their_labels():
    """The tick is the only thing saying which bar is which once there are two."""
    got = _axis_text(categories=4)
    assert got["n_categories"] == 4
    assert any("Vaihtoehto" in t for t in got["xticks"]), got["xticks"]


def test_the_horizontal_form_behaves_the_same_way():
    got = _axis_text(categories=1, chart_type="horizontal_bar")
    assert "TulonlähteidenMuutos" not in got["yticks"], got["yticks"]


# --- the case the first version of this fix broke ---------------------------
def test_a_distribution_left_with_one_category_keeps_its_name():
    """A question whose other options were empty and hidden still draws ONE bar,
    and that bar's tick is an ANSWER ("Vaihtoehto 1"), not the question. The
    subtitle carries the question, so blanking this would leave a nameless bar.

    The first attempt at this fix keyed on the category count alone and did
    exactly that. The statistic is what tells the two apart.
    """
    got = _axis_text(categories=1, statistic="pct", hide_empty=True)
    assert got["n_categories"] == 1
    assert any("Vaihtoehto" in t for t in got["xticks"]), got["xticks"]


def test_the_renderer_and_the_registry_agree_on_what_a_summary_is():
    """`_SUMMARY_STATISTICS` is written out in the renderer so it needs no
    dependency on the stats registry. This is what keeps the copy honest."""
    import reportbuilder.stats.engine  # noqa: F401 — registers the statistics
    from reportbuilder.stats import registry

    from reportbuilder.render.image.bars import _SUMMARY_STATISTICS

    for name in _SUMMARY_STATISTICS:
        assert registry.statistic(name).family == "summary", name
    for name in ("pct", "count"):
        assert name not in _SUMMARY_STATISTICS
        assert registry.statistic(name).family == "distribution"
