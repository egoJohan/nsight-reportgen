"""The methodology footer must not claim a separate-layout slide is split by only
the first variable."""
from __future__ import annotations

from reportbuilder.render.elements import add_filter_annotation
from reportbuilder.stats.series import Cell, SeriesResult

from suite._helpers import make_ctx


def _series():
    return SeriesResult(categories=("A",), segments=("Total",),
                        cells={("A", "Total"): Cell(pct=100.0, count=1.0, mean=None)},
                        base_n={"Total": 1}, statistic="pct")


def _texts(slide):
    return [sh.text_frame.text for sh in slide.shapes if sh.has_text_frame]


def test_one_classifier_names_it():
    _prs, slide, _slot, ctx = make_ctx("horizontal_bar", _series(), classifying_var="sex")
    add_filter_annotation(ctx)
    assert "sex" in " ".join(_texts(slide))


def test_separate_layout_names_both():
    _prs, slide, _slot, ctx = make_ctx(
        "horizontal_bar", _series(), classifying_var="sex", classifying_var_2="age",
        options={"xtab_layout": "separate"})
    add_filter_annotation(ctx)
    text = " ".join(_texts(slide))
    assert "sex" in text and "age" in text
