"""The author's "hide values below X %" is obeyed by every chart that prints values.

`number_format.hide_below_pct` decides what is printed AT ALL. The pie and both
stacked builders read it through `label_floor`; the plain bar, the plain column
and the line never did, so on the commonest chart types in the product the
control did nothing — the author typed a cut-off, the slide came back identical,
and there was no way to tell that from a control that had not saved.

Only the AUTHOR's cut-off is applied here, never a default one. A plain bar
prints its number outside the bar where a small value costs nothing, so there is
no floor to impose when nobody asked for one — and a deck written before this
renders exactly as it did.
"""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest
from pptx import Presentation
from pptx.util import Inches

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.render.base import RenderContext, Slot, StyleSpec
from reportbuilder.render.image._mpl import VALUE_GID
from reportbuilder.stats.engine import compute

#: 3 %, 3 %, 7 %, 11 %, 23 %, 31 %, 22 % — the shape that showed it.
_COUNTS = [31, 31, 71, 112, 234, 316, 224]
_LEVELS = ["1- Ei lainkaan", "2", "3", "4", "5", "6", "7- Erittäin"]

BUILDERS = [
    ("vertical_bar", "bars", "build_image_column"),
    ("horizontal_bar", "bars", "build_image_bar"),
    ("line", "line", "build_image_line"),
    ("pie", "pie", "build_image_pie"),
    ("stacked_horizontal_bar", "bars", "build_image_bar_stacked"),
]


def _values(chart_type: str, mod_name: str, builder: str, hide_below):
    import importlib

    var = Variable(name="q", label="Ylpeys", measurement="nominal",
                   missing_values=[],
                   value_labels=[ValueLabel(value=float(i + 1), label=l)
                                 for i, l in enumerate(_LEVELS)])
    rows = [{"q": float(i + 1)} for i, n in enumerate(_COUNTS) for _ in range(n)]
    model = QuestionModel(
        variables={"q": var},
        questions=[Question(qid="q", text=var.label, kind="single", variables=("q",))])
    spec = ChartSpec(question_ref="q", chart_type=chart_type, statistic="pct",
                     classifying_var=None,
                     number_format=NumberFormat(hide_below_pct=hide_below),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles())
    series = compute(model.question("q"), spec, pd.DataFrame(rows), model)
    prs = Presentation()
    ctx = RenderContext(slide=prs.slides.add_slide(prs.slide_layouts[6]),
                        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                                  width=Inches(11.6), height=Inches(4.0), name="s1"),
                        style=StyleSpec(), spec=spec, series=series,
                        fmt=spec.number_format)
    mod = importlib.import_module(f"reportbuilder.render.image.{mod_name}")
    seen: dict = {}
    original = mod.render_png

    def _spy(fig):
        seen["values"] = [t.get_text() for a in fig.axes for t in a.texts
                          if t.get_gid() == VALUE_GID and t.get_visible()]
        return original(fig)

    mod.render_png = _spy
    try:
        getattr(mod, builder)(ctx)
    finally:
        mod.render_png = original
    return seen["values"]


@pytest.mark.parametrize("chart_type,mod,builder", BUILDERS)
def test_without_a_cut_off_the_small_values_are_printed(chart_type, mod, builder):
    """Guards the test below, and pins that no default floor was introduced."""
    got = _values(chart_type, mod, builder, None)
    assert any("3" in v for v in got), got


@pytest.mark.parametrize("chart_type,mod,builder", BUILDERS)
def test_a_cut_off_of_ten_drops_everything_under_ten(chart_type, mod, builder):
    got = _values(chart_type, mod, builder, 10)
    small = [v for v in got if v.strip().rstrip(" %").replace(",", ".")
             and float(v.strip().rstrip("%").replace(",", ".").strip() or 0) < 10]
    assert small == [], f"{chart_type} still printed {small}"


@pytest.mark.parametrize("chart_type,mod,builder", BUILDERS)
def test_a_cut_off_of_zero_prints_every_value(chart_type, mod, builder):
    """0 is a real answer meaning "draw them all", not a falsy "unset"."""
    got = _values(chart_type, mod, builder, 0)
    assert len(got) >= 7, got
