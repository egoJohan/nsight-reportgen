"""Turning "Data labels" off takes the numbers off the chart — on every type.

`elements.data_labels` was read by the native OOXML path and by the image
SCATTER builder, and by nothing else. In image mode — which is what a preview
and a rendered deck both use — unticking it changed nothing at all on a bar,
column, line, pie, doughnut, radar, funnel, combo or stacked chart: the author
clicked the control, the picture came back identical, and the only way to read
that is "the editor is broken".

The repair is one pass rather than nine: every value a builder prints already
carries `VALUE_GID` (the shrink and declash passes rely on it), and every
builder goes through `new_figure*` and `render_png`. So the figure remembers
the spec it was built for and `render_png` honours the toggle for all of them,
including any builder written later.
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

_CATS = ["Amazon", "Walmart", "Delta", "Salesforce", "Aramco"]
_COUNTS = [310, 220, 180, 160, 130]

#: Radar is absent on purpose: it prints no values at all (the reader takes
#: magnitude off the rings), so there is nothing for the toggle to remove.
BUILDERS = [
    ("vertical_bar", "bars", "build_image_column"),
    ("horizontal_bar", "bars", "build_image_bar"),
    ("stacked_horizontal_bar", "bars", "build_image_bar_stacked"),
    ("stacked_vertical_bar", "bars", "build_image_column_stacked"),
    ("line", "line", "build_image_line"),
    ("pie", "pie", "build_image_pie"),
    ("doughnut", "pie", "build_image_doughnut"),
    ("funnel", "funnel", "build_image_funnel"),
    ("combo", "combo", "build_image_combo"),
]


def _run(chart_type: str, mod_name: str, builder: str, *, data_labels: bool):
    import importlib

    var = Variable(name="q", label="Mitä yrityksiä tunnet?", measurement="nominal",
                   missing_values=[],
                   value_labels=[ValueLabel(value=float(i + 1), label=c)
                                 for i, c in enumerate(_CATS)])
    rows = [{"q": float(i + 1)} for i, n in enumerate(_COUNTS) for _ in range(n)]
    model = QuestionModel(
        variables={"q": var},
        questions=[Question(qid="q", text=var.label, kind="single", variables=("q",))])
    spec = ChartSpec(question_ref="q", chart_type=chart_type, statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles(data_labels=data_labels))
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
        # What the builder ASKED to print, before render_png rasterises and
        # clears the figure. The toggle is honoured inside render_png, so this
        # is read first and the PIXELS are what prove the toggle worked.
        seen["asked"] = [t.get_text() for a in fig.axes for t in a.texts
                         if t.get_gid() == VALUE_GID and t.get_visible()]
        path = original(fig)
        # Read here: place_picture deletes the file once python-pptx has it.
        seen["png"] = pathlib.Path(path).read_bytes()
        return path

    mod.render_png = _spy
    try:
        getattr(mod, builder)(ctx)
    finally:
        mod.render_png = original
    return seen


@pytest.mark.parametrize("chart_type,mod,builder", BUILDERS)
def test_this_chart_type_prints_values_at_all(chart_type, mod, builder):
    """Guards the two tests below: a chart printing nothing proves nothing."""
    got = _run(chart_type, mod, builder, data_labels=True)
    assert got["asked"], f"{chart_type} printed no values with the toggle ON"


@pytest.mark.parametrize("chart_type,mod,builder", BUILDERS)
def test_turning_the_numbers_off_changes_the_picture(chart_type, mod, builder):
    """The author's own test: they untick it and the slide has to change."""
    on = _run(chart_type, mod, builder, data_labels=True)
    off = _run(chart_type, mod, builder, data_labels=False)
    assert on["png"] != off["png"], f"{chart_type}: identical image, toggle does nothing"


def test_the_pass_hides_every_value_it_is_given():
    """The rule itself, directly: a figure carrying values and a spec that
    says not to print them comes back with none of them visible."""
    from matplotlib.figure import Figure

    from reportbuilder.render.image._mpl import hide_values_when_off

    fig = Figure()
    ax = fig.subplots()
    kept = ax.text(0.1, 0.1, "a name")
    hidden = [ax.text(0.5, 0.5, "31 %", gid=VALUE_GID),
              ax.annotate("2 %", xy=(0.2, 0.2), xytext=(0.3, 0.3), gid=VALUE_GID)]

    spec = ChartSpec(question_ref="q", chart_type="pie", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles(data_labels=False))
    hide_values_when_off(fig, spec)
    assert [t.get_visible() for t in hidden] == [False, False]
    assert kept.get_visible(), "a name is not a value and must be left alone"


def test_the_pass_leaves_a_chart_alone_when_the_toggle_is_on():
    from matplotlib.figure import Figure

    from reportbuilder.render.image._mpl import hide_values_when_off

    fig = Figure()
    ax = fig.subplots()
    value = ax.text(0.5, 0.5, "31 %", gid=VALUE_GID)
    spec = ChartSpec(question_ref="q", chart_type="pie", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles(data_labels=True))
    hide_values_when_off(fig, spec)
    assert value.get_visible()
