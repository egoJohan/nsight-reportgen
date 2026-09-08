"""A code the chart cannot draw must not sit in the denominator.

Reported as a stacked horizontal bar that did not stack to 100 %: the bars came
to 25–37 %. The study was an ALL-COUNTRIES export, where one variable carries
each country's own code block — Finland 1–5, and blocks at 16–20 and 26–30 for
the others — and only Finland's codes had value labels in that file.

The engine drew the five labelled categories and counted EVERY non-missing code
in the base, so two thirds of the respondents were in the denominator of a
category none of them could be in. 1027 labelled answers over a base of 3066 is
the 33 % the Total bar showed.

The same class of bug was fixed for the CLASSIFYING variable in af318a3, which
drops present-but-unlabelled sentinel codes (a bare 99) from the segments. It
was never applied to the variable being reported. `_classifier_keep` and
`_valid_mask` now say the same thing: when a variable carries value labels, a
code without one is not an answer. (Johan, 2026-09-08)
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats.base_rules import single_base
from reportbuilder.stats.engine import compute

#: Finland's five, labelled — as in the customer's file.
_FI = {1.0: "Suuressa kaupungissa", 2.0: "Keskisuuressa", 3.0: "Pienessä",
       4.0: "Maaseudulla", 5.0: "Ulkomailla"}
#: Two other countries' blocks, present in the data and labelled nowhere.
_FOREIGN = [16.0, 17.0, 18.0, 26.0, 27.0]


def _model(*, labelled=True):
    var = Variable(
        name="AsuinpaikanKoko", label="Minkä kokoisessa kaupungissa asut?",
        measurement="nominal", missing_values=[],
        value_labels=[ValueLabel(value=c, label=l) for c, l in _FI.items()]
        if labelled else [])
    sektori = Variable(name="Sektori", label="Sektori", measurement="nominal",
                       missing_values=[],
                       value_labels=[ValueLabel(value=1.0, label="yksityinen"),
                                     ValueLabel(value=2.0, label="julkinen")])
    rows = []
    for i in range(300):                       # 300 Finnish answers, codes 1..5
        rows.append({"AsuinpaikanKoko": float(i % 5 + 1), "Sektori": float(i % 2 + 1)})
    for i in range(600):                       # 600 foreign answers, unlabelled
        rows.append({"AsuinpaikanKoko": _FOREIGN[i % 5], "Sektori": float(i % 2 + 1)})
    model = QuestionModel(
        variables={"AsuinpaikanKoko": var, "Sektori": sektori},
        questions=[Question(qid="koko", text=var.label, kind="single",
                            variables=("AsuinpaikanKoko",)),
                   Question(qid="sektori", text="Sektori", kind="single",
                            variables=("Sektori",))])
    return model, pd.DataFrame(rows), var


def _spec(**over) -> ChartSpec:
    base = dict(question_ref="koko", chart_type="stacked_horizontal_bar",
                statistic="pct", classifying_var="Sektori",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s1", elements=ElementToggles(),
                percent_base="classifier")
    base.update(over)
    return ChartSpec(**base)


def _bar_sums(spec) -> dict[str, float]:
    model, df, _var = _model()
    sr = compute(model.question("koko"), spec, df, model)
    return {seg: round(sum((sr.cell(c, seg).pct or 0.0) for c in sr.categories), 1)
            for seg in sr.segments}, sr


def test_the_base_counts_only_answers_the_chart_can_draw():
    """The caller names the codes it draws; the base counts those respondents.

    Unbounded is still every non-missing code — that is what a variable with no
    labels wants, since `code_labels` draws all of them."""
    _model_, df, var = _model()
    assert single_base(df, var, drawn_codes=set(_FI)) == 300
    assert single_base(df, var) == 900, "unbounded should still count everything"


def test_every_bar_of_a_stacked_chart_reaches_one_hundred():
    sums, _sr = _bar_sums(_spec())
    for seg, total in sums.items():
        assert total == pytest.approx(100.0, abs=1.0), f"{seg} stacks to {total} %"


def test_the_slides_n_counts_the_same_respondents():
    _sums, sr = _bar_sums(_spec())
    assert sr.base_n["Total"] == 300


def test_a_variable_with_no_labels_at_all_is_untouched():
    """`code_labels` charts the raw codes there, so every code IS drawn and every
    code belongs in the base. The rule keys on the variable HAVING labels."""
    model, df, var = _model(labelled=False)
    assert single_base(df, var) == 900
