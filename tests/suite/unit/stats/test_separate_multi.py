"""A MULTI question split by two background variables side by side."""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _member(name, label):
    return Variable(name=name, label=label, measurement="categorical",
                    value_labels=(ValueLabel(0.0, "Unchecked"), ValueLabel(1.0, "Checked")),
                    missing_values=frozenset())


def _setup():
    m1, m2 = _member("m1", "Kanava A"), _member("m2", "Kanava B")
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Vanhat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"m1": m1, "m2": m2, "sex": sex, "age": age},
                          questions=[])
    q = Question(qid="mm", kind="multi", variables=("m1", "m2"), text="Kanavat")
    df = pd.DataFrame({
        "m1": [1.0, 0.0] * 40,
        "m2": [1.0, 1.0, 0.0, 0.0] * 20,
        "sex": ([1.0] * 40) + ([2.0] * 40),
        "age": [1.0, 2.0] * 40,
    })
    return model, q, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="mm", chart_type="horizontal_bar", statistic="pct",
                classifying_var="sex", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles(),
                options={"xtab_layout": "separate"})
    base.update(kw)
    return ChartSpec(**base)


def test_multi_segments_are_the_sum_not_the_product():
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert list(r.segments) == [
        "Sukupuoli · Nainen", "Sukupuoli · Mies",
        "Ikäryhmät · Nuoret", "Ikäryhmät · Vanhat",
    ]
    # base_n["Total"] stays multi_base(data, vars_) — the multi question's OWN base
    # (>=1 valid selection across m1/m2), unaffected by the classifier masks; it is
    # NOT the union of the sex/age panel masks. With this fixture's m1/m2 pattern,
    # 20 of the 80 rows (idx % 4 == 3) select neither item, so the base is 60, not
    # every respondent. (deviation from the task-3 brief's literal "== 80": that
    # value doesn't match multi_base's semantics for this fixture — see task-3-report.md)
    assert r.base_n["Total"] == 60


def test_multi_segment_primary_is_the_variable():
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert len(set(r.segment_primary.values())) == 2
