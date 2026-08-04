"""A single question split by two background variables SIDE BY SIDE."""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import QuestionModel, Question, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup():
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Keski"),
                                 ValueLabel(3.0, "Vanhat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex, "age": age}, questions=[])
    question = Question(qid="q", kind="single", variables=("q",), text="Suhtautuminen")
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0, 5.0] * 24,
        "sex": ([1.0] * 60) + ([2.0] * 60),
        "age": [1.0, 2.0, 3.0] * 40,
    })
    return model, question, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                classifying_var="sex", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles(),
                options={"xtab_layout": "separate"})
    base.update(kw)
    return ChartSpec(**base)


def test_segments_are_the_sum_of_both_variables_groups():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert list(r.segments) == [
        "Sukupuoli · Nainen", "Sukupuoli · Mies",
        "Ikäryhmät · Nuoret", "Ikäryhmät · Keski", "Ikäryhmät · Vanhat",
    ]


def test_segment_primary_is_the_source_variable():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert r.segment_primary["Sukupuoli · Nainen"] == "Sukupuoli"
    assert r.segment_primary["Ikäryhmät · Vanhat"] == "Ikäryhmät"
    assert len(set(r.segment_primary.values())) == 2, "one panel per VARIABLE"


def test_bases_are_per_group_and_total_survives():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert r.base_n["Sukupuoli · Nainen"] == 60
    assert r.base_n["Ikäryhmät · Nuoret"] == 40
    assert r.base_n["Total"] == 120, "the N footer indexes base_n['Total'] directly"


def test_each_group_sums_to_100_percent():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    for seg in r.segments:
        total = sum((r.cell(c, seg).pct or 0.0) for c in r.categories)
        assert abs(total - 100.0) < 1.5, f"{seg} should be a full distribution"


def test_percent_base_is_forced_to_the_classifier_direction():
    model, question, df = _setup()
    r = engine.compute(question, _spec(percent_base="question"), df, model)
    for seg in r.segments:
        total = sum((r.cell(c, seg).pct or 0.0) for c in r.categories)
        assert abs(total - 100.0) < 1.5


def test_crossed_layout_is_untouched():
    model, question, df = _setup()
    r = engine.compute(question, _spec(options={"xtab_layout": "auto"}), df, model)
    assert len([s for s in r.segments if s != "Total"]) == 6, "2 x 3 combos"
