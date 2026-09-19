"""A combo on a multi-response question draws its options, not its first option.

`_combo_two_var` read `question.variables[0]` whatever the question was, so the
moment a secondary variable was chosen, a combo on "Mitä seuraavista
hoivapalveluiden tarjoajista tunnet?" drew ONE brand's dichotomy — "Unchecked
14 %", "Checked 86 %" — instead of the nine brands it drew a second earlier.
(visual QA, 2026-09-19)
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats.engine import compute

_BRANDS = ("Attendo", "Esperi", "Humana")


def _computed():
    checked = (ValueLabel(0.0, "Unchecked"), ValueLabel(1.0, "Checked"))
    variables = {f"b{i}": Variable(f"b{i}", b, "categorical", checked, frozenset())
                 for i, b in enumerate(_BRANDS)}
    variables["score"] = Variable("score", "Luotettava", "scale", (), frozenset())
    question = Question(qid="brands", kind="multi",
                        variables=tuple(f"b{i}" for i in range(len(_BRANDS))),
                        text="Mitä seuraavista tunnet?")
    model = QuestionModel(variables=variables, questions=[question])
    # Everyone knows Attendo; the first 60 know Esperi; the first 20 Humana.
    # The score is 4 for the first 20 respondents and 2 for everyone else.
    df = pd.DataFrame({
        "b0": [1.0] * 100,
        "b1": [1.0] * 60 + [0.0] * 40,
        "b2": [1.0] * 20 + [0.0] * 80,
        "score": [4.0] * 20 + [2.0] * 80,
    })
    spec = ChartSpec(question_ref="brands", chart_type="combo", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles(), options={"combo_secondary": "score"})
    return compute(question, spec, df, model)


def test_the_bars_are_the_options():
    r = _computed()
    assert tuple(r.categories) == _BRANDS
    bars = r.segments[0]
    assert [r.cell(b, bars).pct for b in _BRANDS] == [100.0, 60.0, 20.0]


def test_the_line_is_the_secondary_among_those_who_chose_each_option():
    r = _computed()
    line = r.secondary_segments[0]
    means = [round(r.cell(b, line).pct, 2) for b in _BRANDS]
    # Attendo: everyone (20 x 4 + 80 x 2) / 100; Esperi: the first 60; Humana: the 20 fours.
    assert means == [2.4, round((20 * 4 + 40 * 2) / 60, 2), 4.0]
