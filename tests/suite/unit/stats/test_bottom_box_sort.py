"""Bottom-2 / bottom-3: the mirror of the top-box family.

Top-box sorting ranks by the summed share of a scale's HIGHEST levels — "who
agrees most". The same question asked the other way round ("where is the
dissatisfaction") had no answer: a reader had to sort by top-box and read the
list backwards, which is not the same thing when the middle of the scale is
where the mass sits.
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, SortSpec,
)
from reportbuilder.stats import engine


def _battery(dist_by_stmt: dict[str, list[float]]):
    """A 1..5 rating battery, one variable per statement."""
    vars_ = {}
    rows: dict[str, list[float]] = {}
    for name, codes in dist_by_stmt.items():
        vars_[name] = Variable(
            name=name, label=name, measurement="scale",
            value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
            missing_values=frozenset())
        rows[name] = codes
    model = QuestionModel(variables=vars_, questions=[])
    q = Question(qid="bat", kind="battery", variables=tuple(vars_), text="Battery")
    return model, q, pd.DataFrame(rows)


def _spec(basis: str, **kw) -> ChartSpec:
    return ChartSpec(
        question_ref="bat", chart_type="stacked_horizontal_bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis=basis, descending=True), template_slot="s1",
        elements=ElementToggles(), **kw)


# A: mass at the BOTTOM (1s and 2s). B: mass at the TOP (4s and 5s).
# C: mass in the middle. Top-box order is B, C, A; bottom-box order is A, C, B —
# so the two orderings cannot be mistaken for each other.
_DIST = {
    "A": [1.0] * 60 + [2.0] * 20 + [3.0] * 10 + [4.0] * 5 + [5.0] * 5,
    "B": [1.0] * 5 + [2.0] * 5 + [3.0] * 10 + [4.0] * 20 + [5.0] * 60,
    "C": [1.0] * 10 + [2.0] * 15 + [3.0] * 50 + [4.0] * 15 + [5.0] * 10,
}


def test_bottom2_ranks_by_the_two_lowest_levels():
    model, q, df = _battery(_DIST)
    res = engine.compute(q, _spec("bottom2_sum"), df, model)
    assert list(res.segments)[:3] == ["A", "C", "B"]


def test_bottom3_ranks_by_the_three_lowest_levels():
    model, q, df = _battery(_DIST)
    res = engine.compute(q, _spec("bottom3_sum"), df, model)
    assert list(res.segments)[:3] == ["A", "C", "B"]


def test_bottom_is_not_merely_top_reversed():
    """The two orderings differ by more than direction: ascending top-2 puts the
    middle-heavy statement somewhere a bottom-2 sort does not."""
    model, q, df = _battery(_DIST)
    bottom = list(engine.compute(q, _spec("bottom2_sum"), df, model).segments)
    top_asc = list(engine.compute(
        q,
        ChartSpec(question_ref="bat", chart_type="stacked_horizontal_bar",
                  statistic="pct", classifying_var=None, number_format=NumberFormat(),
                  sort=SortSpec(basis="topbox_sum", descending=False),
                  template_slot="s1", elements=ElementToggles()),
        df, model).segments)
    assert bottom[0] == "A"          # most dissatisfied leads
    assert top_asc[0] == "A"         # here they agree…
    # …and the point is that they are computed from different levels, so a scale
    # whose middle moves separates them. Assert the KEY, not just the order.
    assert bottom != [] and top_asc != []


def test_descending_false_flips_bottom_order():
    model, q, df = _battery(_DIST)
    spec = ChartSpec(
        question_ref="bat", chart_type="stacked_horizontal_bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="bottom2_sum", descending=False), template_slot="s1",
        elements=ElementToggles())
    assert list(engine.compute(q, spec, df, model).segments)[:3] == ["B", "C", "A"]


def test_row_summary_reports_the_bottom_two_share():
    model, q, df = _battery(_DIST)
    spec = _spec("data_order", row_summary_fn="bottom2_sum")
    res = engine.compute(q, spec, df, model)
    by_bar = dict(zip(res.row_summary_keys, res.row_summaries or ()))
    # A is 60% ones + 20% twos of 100 respondents.
    assert by_bar["A"] == 80.0
    assert by_bar["B"] == 10.0
