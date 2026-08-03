"""The right-hand row-summary column on a SINGLE-question stacked bar.

A rating battery rendered as a stacked bar gets the summary column (one value per
statement bar). The same question asked as ONE variable renders as a single
100%-stacked 'Total' bar — that bar is a row too, so a configured row summary must
appear there as well, with or without a classifying variable.
(defect: "row summary works in a battery but not in a single stacked bar")
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup():
    """One 1..5 rating variable, n=100: 10/10/20/30/30 -> top2 = 60 %, mean = 3.6."""
    v = Variable(name="q", label="Erisan on monipuolinen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    clf = Variable(name="polku", label="Polku", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Polku 1"), ValueLabel(2.0, "Polku 2")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": v, "polku": clf}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text="Erisan on monipuolinen")
    codes = [1.0] * 10 + [2.0] * 10 + [3.0] * 20 + [4.0] * 30 + [5.0] * 30
    df = pd.DataFrame({"q": codes, "polku": [1.0, 2.0] * 50})
    return model, q, df


def _spec(**kw):
    base = dict(question_ref="q", chart_type="stacked_horizontal_bar", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def test_total_only_stacked_bar_gets_a_row_summary():
    model, q, df = _setup()
    r = engine.compute(q, _spec(row_summary_fn="top2_sum"), df, model)
    assert r.segments == ("Total",)
    assert r.row_summaries == (60.0,), "the single 'Total' bar is a row too"


def test_total_only_stacked_bar_row_summary_mean():
    model, q, df = _setup()
    r = engine.compute(q, _spec(row_summary_fn="mean"), df, model)
    assert r.row_summaries == (3.6,)


def test_total_only_stacked_bar_without_row_summary_stays_off():
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert r.row_summaries is None


def test_classified_stacked_bar_still_gets_one_value_per_bar():
    model, q, df = _setup()
    r = engine.compute(q, _spec(classifying_var="polku", row_summary_fn="top2_sum"),
                       df, model)
    assert list(r.segments) == ["Polku 1", "Polku 2", "Total"]
    # One value per bar, the "Total" reference bar included, each keyed to its bar.
    assert r.row_summary_keys == r.segments
    assert r.row_summaries is not None and len(r.row_summaries) == len(r.segments)


def _setup_with_a_tiny_group():
    """As _setup, but the classifier has a THIRD group with a near-empty base — the
    renderer drops such a group (MIN_SEGMENT_BASE), so the summary values must not be
    read positionally against the bars that survive."""
    model, q, df = _setup()
    clf = model.variables["polku"]
    model.variables["polku"] = replace(
        clf, value_labels=clf.value_labels + (ValueLabel(3.0, "Muuten"),))
    # 4 respondents in "Muuten", all at the top of the scale -> its top2 is 100 %.
    df.loc[df.index[:4], "polku"] = 3.0
    df.loc[df.index[:4], "q"] = 5.0
    return model, q, df


def test_row_summaries_are_keyed_to_their_bar():
    model, q, df = _setup_with_a_tiny_group()
    r = engine.compute(q, _spec(classifying_var="polku", row_summary_fn="top2_sum"),
                       df, model)
    keyed = dict(zip(r.row_summary_keys, r.row_summaries))
    assert keyed["Muuten"] == 100.0
    # The Total row is a bar too, and carries the overall top 2 — not a neighbour's.
    top2 = (r.cell("4", "Total").pct or 0.0) + (r.cell("5", "Total").pct or 0.0)
    assert keyed["Total"] == round(top2, 0)


def test_dropped_tiny_group_does_not_shift_the_total_bars_summary():
    from reportbuilder.render.image._mpl import MIN_SEGMENT_BASE
    from reportbuilder.render.image.bars import _stacked_layout, _row_summary_by_bar

    model, q, df = _setup_with_a_tiny_group()
    r = engine.compute(q, _spec(classifying_var="polku", row_summary_fn="top2_sum"),
                       df, model)
    assert r.base_n["Muuten"] < MIN_SEGMENT_BASE, "the tiny group is renderer-dropped"

    bars, _stack, _data = _stacked_layout(r)
    assert "Muuten" not in bars
    by_bar = _row_summary_by_bar(r, bars)
    top2 = (r.cell("4", "Total").pct or 0.0) + (r.cell("5", "Total").pct or 0.0)
    assert by_bar[bars.index("Total")] == round(top2, 0), "Total keeps its OWN value"
    assert len(by_bar) == len(bars)
