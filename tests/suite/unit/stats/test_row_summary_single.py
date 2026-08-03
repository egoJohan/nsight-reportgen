"""The right-hand row-summary column on a SINGLE-question stacked bar.

A rating battery rendered as a stacked bar gets the summary column (one value per
statement bar). The same question asked as ONE variable renders as a single
100%-stacked 'Total' bar — that bar is a row too, so a configured row summary must
appear there as well, with or without a classifying variable.
(defect: "row summary works in a battery but not in a single stacked bar")
"""
from __future__ import annotations

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
    bars = [s for s in r.segments if s != "Total"]
    assert bars == ["Polku 1", "Polku 2"]
    assert r.row_summaries is not None and len(r.row_summaries) == len(bars)
