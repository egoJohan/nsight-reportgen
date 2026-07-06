"""The cross-tab percentage DIRECTION (percent_base) for a classified single chart.

A chart with base variable B (question_ref) classified by C has two meaningful
percentage directions:

  - "classifier"  → each classifier segment is a sub-population; B is distributed
                    within it (each segment column sums to 100%). LEGACY DEFAULT.
  - "question"    → each B category is a sub-population; C is distributed within it
                    (each base-category row sums to 100%). The customer's "% of men
                    in each segment" direction.
  - "total"       → every cell over the grand total.
  - "auto"        → resolve deterministically from variable roles (see resolve_*).
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
from reportbuilder.model.report import (
    ChartSpec, NumberFormat, SortSpec, ElementToggles,
)
from reportbuilder.stats import engine


def _spec(**kw):
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                classifying_var="g", number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def _model_qg():
    q = Variable(name="q", label="Q", measurement="categorical",
                 value_labels=(ValueLabel(1.0, "A"), ValueLabel(2.0, "B")),
                 missing_values=frozenset())
    g = Variable(name="g", label="G", measurement="categorical",
                 value_labels=(ValueLabel(1.0, "X"), ValueLabel(2.0, "Y")),
                 missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "g": g}, questions=[])
    question = Question(qid="q", kind="single", variables=("q",), text="Q")
    return model, question


# Asymmetric cell counts so the two directions give DIFFERENT numbers:
#   (A,X)=6 (A,Y)=2 (B,X)=2 (B,Y)=2  → base(A)=8 base(B)=4 base(X)=8 base(Y)=4
def _df():
    return pd.DataFrame({
        "q": [1] * 8 + [2] * 4,
        "g": [1] * 6 + [2] * 2 + [1] * 2 + [2] * 2,
    })


def test_percent_base_question_normalizes_within_each_base_category():
    model, q = _model_qg()
    r = engine.compute(q, _spec(percent_base="question"), _df(), model)
    # Row A distributes the classifier: X = 6/8, Y = 2/8  → sums to 100%.
    assert r.cell("A", "X").pct == 75.0
    assert r.cell("A", "Y").pct == 25.0
    assert (r.cell("A", "X").pct + r.cell("A", "Y").pct) == 100.0
    # Row B: X = 2/4, Y = 2/4.
    assert r.cell("B", "X").pct == 50.0
    assert r.cell("B", "Y").pct == 50.0
