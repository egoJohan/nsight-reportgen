"""compute() must not relabel separate-mode segments, and the banner guard must
only fire for CROSSED layouts."""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup_banner():
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    p1 = Variable(name="p1", label="Polku 1", measurement="categorical",
                  value_labels=(ValueLabel(0.0, "Ei"), ValueLabel(1.0, "Kyllä")),
                  missing_values=frozenset())
    p2 = Variable(name="p2", label="Polku 2", measurement="categorical",
                  value_labels=(ValueLabel(0.0, "Ei"), ValueLabel(1.0, "Kyllä")),
                  missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Vanhat")),
                   missing_values=frozenset())
    polku = Question(qid="polku", kind="multi", variables=("p1", "p2"), text="Polku")
    question = Question(qid="q", kind="single", variables=("q",), text="Suhtautuminen")
    model = QuestionModel(variables={"q": q, "p1": p1, "p2": p2, "age": age},
                          questions=[polku, question])
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0] * 20,
        "p1": ([1.0] * 40) + ([0.0] * 40),
        "p2": ([0.0] * 40) + ([1.0] * 40),
        "age": [1.0, 2.0] * 40,
    })
    return model, question, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                classifying_var="polku", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles(), options={})
    base.update(kw)
    return ChartSpec(**base)


def test_banner_crossed_with_a_second_variable_still_raises():
    model, question, df = _setup_banner()
    with pytest.raises(ValueError, match="banner"):
        engine.compute(question, _spec(options={"xtab_layout": "auto"}), df, model)


def test_banner_is_allowed_in_separate_mode():
    model, question, df = _setup_banner()
    r = engine.compute(question, _spec(options={"xtab_layout": "separate"}), df, model)
    assert list(r.segments) == [
        "Polku · Polku 1", "Polku · Polku 2",
        "Ikäryhmät · Nuoret", "Ikäryhmät · Vanhat",
    ]


def test_separate_labels_survive_compute_untouched():
    model, question, df = _setup_banner()
    r = engine.compute(question, _spec(options={"xtab_layout": "separate"}), df, model)
    assert all(" · " in s for s in r.segments)
    assert not any("|" in s for s in r.segments), "no combo relabelling ran"
