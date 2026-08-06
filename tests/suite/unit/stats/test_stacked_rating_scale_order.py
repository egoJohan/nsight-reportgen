"""A stacked bar of a RATING SCALE must render in scale order, not frequency order,
whether or not it has a classifying variable.

A 100 %-stacked bar of an ordered scale is only readable in scale order — reordering
the stack by segment size breaks the visual adjacency the row-summary column (e.g.
"Top 2") relies on: the reader eyeballs the two summed bands and expects them to sit
next to each other. Previously the code only forced ``data_order`` when the bar had a
classifying variable (bars-are-segments) or the scale was partially labelled
(``scale_entries is not None``); a classifier-less stacked rating scale fell through
to the slide's ``sort`` setting, which defaults to ``pct``.

(defect: customer's mat-erisan var212 legend rendered 4,3,5,2,1 instead of 1..5, so the
Top 2 (4+5) bands were not adjacent and a reader added the two visually-largest bands
(3+4) instead, misreading the summary column.)
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _rating_setup():
    """1..5 rating variable, n=511, modelled on the real mat-erisan var212 distribution:
    1=1.6%, 2=4.1%, 3=34.2%, 4=38.0%, 5=22.1% — level 3 outweighs level 5, so a
    frequency sort and a scale-order sort disagree unmistakably."""
    v = Variable(name="q", label="Miten myönteisesti suhtaudut Erisaniin?",
                 measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    model = QuestionModel(variables={"q": v}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text=v.label)
    codes = [1.0] * 8 + [2.0] * 21 + [3.0] * 175 + [4.0] * 194 + [5.0] * 113
    df = pd.DataFrame({"q": codes})
    return model, q, df


def _categorical_setup():
    """Plain unordered categorical (brand preference), n=100, sized so frequency order
    (C, A, B) differs from data/definition order (A, B, C)."""
    v = Variable(name="q", label="Brand preference", measurement="categorical",
                 value_labels=(ValueLabel(1.0, "A"), ValueLabel(2.0, "B"),
                               ValueLabel(3.0, "C")),
                 missing_values=frozenset())
    model = QuestionModel(variables={"q": v}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text=v.label)
    codes = [1.0] * 20 + [2.0] * 30 + [3.0] * 50
    df = pd.DataFrame({"q": codes})
    return model, q, df


def _spec(**kw):
    base = dict(question_ref="q", chart_type="stacked_horizontal_bar", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="pct", descending=True), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def test_classifierless_stacked_horizontal_bar_on_rating_scale_keeps_scale_order():
    model, q, df = _rating_setup()
    r = engine.compute(q, _spec(chart_type="stacked_horizontal_bar"), df, model)
    assert list(r.categories) == ["1", "2", "3", "4", "5"], (
        "a classifier-less stacked rating scale must render in scale order, not "
        "frequency order, or the row-summary column's summed bands aren't adjacent"
    )


def test_classifierless_stacked_vertical_bar_on_rating_scale_keeps_scale_order():
    model, q, df = _rating_setup()
    r = engine.compute(q, _spec(chart_type="stacked_vertical_bar"), df, model)
    assert list(r.categories) == ["1", "2", "3", "4", "5"]


def test_classifierless_stacked_bar_of_plain_categorical_still_sorts_by_frequency():
    # Guard against over-fixing: a plain categorical has no inherent order, so a
    # stacked bar of one must keep honouring the slide's frequency sort.
    model, q, df = _categorical_setup()
    r = engine.compute(q, _spec(chart_type="stacked_horizontal_bar"), df, model)
    assert list(r.categories) == ["C", "B", "A"], (
        "a non-rating categorical must still sort by frequency (pct), unaffected by "
        "the rating-scale fix"
    )


def test_non_stacked_chart_on_rating_scale_still_sorts_by_frequency():
    # The fix is scoped to STACKED bar types; a plain (non-stacked) chart on the same
    # rating scale must keep sorting by whatever basis the slide asks for.
    model, q, df = _rating_setup()
    r = engine.compute(q, _spec(chart_type="horizontal_bar"), df, model)
    assert list(r.categories) == ["4", "3", "5", "2", "1"]


def test_top2_row_summary_value_is_unchanged_by_the_reordering():
    # The Top 2 sum (levels 4+5) was already computed correctly (it always chooses
    # scale-ascending levels for the summary independent of display sort) — this must
    # stay true once the category ORDER itself also becomes scale order.
    model, q, df = _rating_setup()
    r = engine.compute(
        q, _spec(chart_type="stacked_horizontal_bar", row_summary_fn="top2_sum"),
        df, model)
    assert list(r.categories) == ["1", "2", "3", "4", "5"]
    assert r.row_summaries == (60.0,)
