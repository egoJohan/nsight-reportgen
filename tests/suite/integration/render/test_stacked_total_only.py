"""Integration: a single-question distribution (no classifying_var) charted as a
stacked bar renders as ONE 100%-stacked 'Total' bar (the "just total" case).

Drives the real product path: compute() -> _stacked_layout -> image builder.
"""
from __future__ import annotations

import io

import pandas as pd
import pytest
from PIL import Image

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.render.house_style import INK
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


# ---------------------------------------------------------------------------
# The row-summary column on the total-only bar (defect: shows in a battery but not
# in a single stacked bar).
# ---------------------------------------------------------------------------

def _scale_model_and_data():
    """One 1..5 rating variable, n=100: 10/10/20/30/30 -> top2 = 60 %."""
    v = Variable(name="q", label="Erisan on monipuolinen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    model = QuestionModel(variables={"q": v}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text="Erisan on monipuolinen")
    df = pd.DataFrame({"q": [1.0] * 10 + [2.0] * 10 + [3.0] * 20 + [4.0] * 30 + [5.0] * 30})
    return model, q, df


def _ink_pixels_in_right_strip(blob: bytes, frac: float = 0.12) -> int:
    """INK-coloured pixels in the rightmost `frac` of the PNG — where the row-summary
    column is drawn."""
    img = Image.open(io.BytesIO(blob)).convert("RGB")
    w, h = img.size
    strip = img.crop((int(w * (1 - frac)), 0, w, h))
    r, g, b = (int(INK.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return sum(1 for px in strip.getdata()
               if abs(px[0] - r) <= 8 and abs(px[1] - g) <= 8 and abs(px[2] - b) <= 8)


def test_total_only_stacked_bar_carries_one_row_summary_value():
    model, q, df = _scale_model_and_data()
    spec_kw = dict(classifying_var=None, row_summary_fn="top2_sum")
    series = compute(q, make_spec("stacked_horizontal_bar", **spec_kw), df, model)

    bars, _stack, _data = _stacked_layout(series)
    assert series.row_summaries == (60.0,)
    assert len(series.row_summaries) == len(bars), "one summary value per rendered bar"


def test_total_only_stacked_bar_draws_the_summary_column():
    model, q, df = _scale_model_and_data()

    def render(**spec_kw) -> bytes:
        series = compute(q, make_spec("stacked_horizontal_bar", classifying_var=None,
                                      **spec_kw), df, model)
        _prs, slide, slot, ctx = make_ctx("stacked_horizontal_bar", series,
                                          classifying_var=None, **spec_kw)
        IMAGE_BUILDERS["stacked_horizontal_bar"](ctx)
        return assert_single_picture(slide, slot).image.blob

    off = _ink_pixels_in_right_strip(render())
    on = _ink_pixels_in_right_strip(render(row_summary_fn="top2_sum",
                                           row_summary_label="Top 2"))
    assert on > off, "the summary header + value are drawn to the right of the bar"
