"""Sorting by percentage sorts by the summary column the chart is showing.

"Tassa ei toimi sorttaus top 2 perusteella vaikka minulla on valittuna sorttaus
prosentin mukaan ja top 2."

The author adds a Top 2 column to a battery and sets Sort to Percentage, and
nothing moves. Both controls say "Top 2 sum" somewhere, but they are different
fields with different vocabularies — the Sort list stores `topbox_sum`, the Row
summary list stores `top2_sum` — and only the first one sorts. Percentage,
meanwhile, is the Sort default and on a battery it is a silent no-op: the bars
are STATEMENTS, and `sorting.py` orders categories, so there is no per-bar key
for it to use. The chart comes out in file order and says it is sorted by
percentage.

Measured on the customer's own slide (Taffel, "Kuinka todennäköisesti ostaisit
Taffelin tuotteita useammin"): the Top 2 column read 52, 53, 60, 60, 36, 72, 42,
48, 42, 45, 73, 75, 61 — neither up nor down.

So when a chart carries a row-summary column, "Percentage" means THAT
percentage: the one number per row the reader can actually see. A chart with no
summary column is untouched, and an explicit basis still wins over this.
(Johan, 2026-09-14)
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _rating_var(name: str, label: str) -> Variable:
    return Variable(name=name, label=label, measurement="scale",
                    value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                    missing_values=frozenset())


def _battery():
    """Three statements, n=10 each, whose top-2 shares are OUT of file order:
    A 40 %, B 80 %, C 60 %. Sorted descending that is B, C, A."""
    names = {"s1": "Statement A", "s2": "Statement B", "s3": "Statement C"}
    model = QuestionModel(variables={n: _rating_var(n, l) for n, l in names.items()},
                          questions=[])
    q = Question(qid="b", kind="battery", variables=("s1", "s2", "s3"), text="Battery")
    df = pd.DataFrame({
        "s1": [5] * 4 + [1] * 6,      # top2 = 40 %
        "s2": [5] * 8 + [1] * 2,      # top2 = 80 %
        "s3": [5] * 6 + [1] * 4,      # top2 = 60 %
    })
    return model, q, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="b", chart_type="stacked_horizontal_bar", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def test_the_fixture_really_is_out_of_order_to_begin_with():
    """Without this the rest could pass on data that was already sorted."""
    model, q, df = _battery()
    r = engine.compute(q, _spec(row_summary_fn="top2_sum"), df, model)
    assert r.row_summaries == (40.0, 80.0, 60.0), r.row_summaries


def test_percentage_sorts_a_battery_by_its_row_summary():
    model, q, df = _battery()
    r = engine.compute(q, _spec(row_summary_fn="top2_sum",
                                sort=SortSpec(basis="pct", descending=True)), df, model)
    assert r.row_summaries == (80.0, 60.0, 40.0), r.row_summaries
    assert r.segments == ("Statement B", "Statement C", "Statement A"), r.segments


def test_the_direction_control_still_decides_which_end_leads():
    model, q, df = _battery()
    r = engine.compute(q, _spec(row_summary_fn="top2_sum",
                                sort=SortSpec(basis="pct", descending=False)), df, model)
    assert r.row_summaries == (40.0, 60.0, 80.0), r.row_summaries


def test_a_mean_summary_is_sorted_by_the_mean_it_shows():
    """Whatever the column computes is what "percentage" orders by — the reader
    is looking at one number per row and expects the sort to be about it."""
    model, q, df = _battery()
    r = engine.compute(q, _spec(row_summary_fn="mean",
                                sort=SortSpec(basis="pct", descending=True)), df, model)
    assert list(r.row_summaries) == sorted(r.row_summaries, reverse=True), r.row_summaries


def test_a_chart_with_no_summary_column_is_left_exactly_as_it_was():
    """This runs on every battery; one without the column must not move."""
    model, q, df = _battery()
    before = engine.compute(q, _spec(sort=SortSpec(basis="data_order")), df, model)
    after = engine.compute(q, _spec(sort=SortSpec(basis="pct", descending=True)), df, model)
    assert after.segments == before.segments, (before.segments, after.segments)


def test_an_explicit_box_basis_still_wins():
    """`topbox_sum` was always the way to ask for this and keeps working."""
    model, q, df = _battery()
    r = engine.compute(q, _spec(row_summary_fn="top2_sum",
                                sort=SortSpec(basis="topbox_sum", descending=True)),
                       df, model)
    assert r.row_summaries == (80.0, 60.0, 40.0), r.row_summaries
