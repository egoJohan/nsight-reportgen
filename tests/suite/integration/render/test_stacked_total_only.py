"""Integration: a single-question distribution (no classifying_var) charted as a
stacked bar renders as ONE 100%-stacked 'Total' bar (the "just total" case).

Drives the real product path: compute() -> _stacked_layout -> image builder.
"""
from __future__ import annotations

import pytest

from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.render.image.bars import _stacked_layout
from reportbuilder.stats.engine import compute
from reportbuilder.testing.fixtures import tiny_model_and_data

from suite._helpers import assert_single_picture, make_ctx, make_spec


@pytest.mark.parametrize("chart_type", ["stacked_vertical_bar", "stacked_horizontal_bar"])
def test_total_only_stacked_series_is_single_bar(chart_type):
    model, data = tiny_model_and_data()  # q1 = Yes/No (60/40)
    q = model.question("q1")
    spec = make_spec(chart_type, classifying_var=None)
    series = compute(q, spec, data, model)

    assert series.segments == ("Total",), "no classifier => single Total segment"
    bars, stack, _ = _stacked_layout(series)
    assert list(bars) == ["Total"], "total-only stacked bar is a single 'Total' bar"
    assert len(stack) >= 2, "stack members are the answer categories"


@pytest.mark.parametrize("chart_type", ["stacked_vertical_bar", "stacked_horizontal_bar"])
def test_total_only_stacked_renders_one_picture(chart_type):
    model, data = tiny_model_and_data()
    q = model.question("q1")
    spec = make_spec(chart_type, classifying_var=None)
    series = compute(q, spec, data, model)

    _prs, slide, slot, ctx = make_ctx(chart_type, series, classifying_var=None)
    IMAGE_BUILDERS[chart_type](ctx)
    assert_single_picture(slide, slot)
