"""What a question is OFFERED as must be a chart it can actually be.

The questions list suggests a default chart type from a cheap synthetic series
(`_quick_series`) rather than computing every question — a material can hold
200+. Where a variable has no value labels that synthetic series invents three
categories, "A", "B", "C", and gives each of them 50 %: a clean nominal
partition of a whole. The pie plugin reads exactly that shape and scores its
top 0.95, so the product's suggested chart for a numeric index was a pie — and
an index whose only value is a mean of 5.7 draws as one filled circle with
"5.7" written on it. Nothing about that picture is readable.

A battery already declared itself measured rather than partitioned. A plain
numeric scale is the same kind of thing and never said so; nor did a variable
with no labels at all, where the categories are this function's own invention.
"""
from __future__ import annotations

import pytest

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.api.routes_questions import _quick_series
from reportbuilder.render.plugins import suggest_chart_type

_ROUND = {"pie", "doughnut"}


def _suggest(var: Variable, kind: str = "single") -> str:
    q = Question(qid="q", text=var.label, kind=kind, variables=("q",))
    model = QuestionModel(variables={"q": var}, questions=[q])
    return suggest_chart_type(q, _quick_series(q, model, None))


def _scale(name="q", label="Työelämäindeksi"):
    return Variable(name=name, label=label, measurement="scale",
                    missing_values=[], value_labels=[])


def test_a_numeric_index_is_not_suggested_as_a_pie():
    assert _suggest(_scale()) not in _ROUND


def test_an_unlabelled_variable_is_not_suggested_as_a_pie():
    """Its categories are a placeholder `_quick_series` invented; nothing is
    known about them, least of all that they partition a whole."""
    var = Variable(name="q", label="NPS", measurement="nominal",
                   missing_values=[], value_labels=[])
    assert _suggest(var) not in _ROUND


def test_a_real_nominal_partition_is_still_a_pie():
    """The control. Four named groups that do add up is what a pie is FOR, and
    that suggestion must not change."""
    var = Variable(name="q", label="Yritys", measurement="nominal",
                   missing_values=[],
                   value_labels=[ValueLabel(value=float(i + 1), label=n)
                                 for i, n in enumerate(
                                     ["Amazon", "Walmart", "Delta", "Salesforce"])])
    assert _suggest(var) in _ROUND


def test_a_labelled_scale_is_not_suggested_as_a_pie():
    """A 1..7 rating stored as a scale reports a mean, whatever its labels."""
    var = Variable(name="q", label="Tyytyväisyys", measurement="scale",
                   missing_values=[],
                   value_labels=[ValueLabel(value=float(i + 1), label=str(i + 1))
                                 for i in range(7)])
    assert _suggest(var) not in _ROUND


# ---------------------------------------------------------------------------
# What is OFFERED, not just what is suggested
# ---------------------------------------------------------------------------

def _compatible(var: Variable, kind: str = "single") -> list[str]:
    from reportbuilder.api.routes_questions import _compatible_chart_types

    q = Question(qid="q", text=var.label, kind=kind, variables=("q",))
    model = QuestionModel(variables={"q": var}, questions=[q])
    return _compatible_chart_types(q, _quick_series(q, model, None))


def test_an_index_is_not_offered_a_radar():
    """A radar of one value draws its rings, one spoke and no polygon at all —
    there is nothing to join up. Työelämäindeksi rendered exactly that: an
    empty web with a label on it."""
    assert "radar" not in _compatible(_scale())


def test_a_profile_is_still_offered_a_radar():
    """The control: four attributes is what a radar is for."""
    var = Variable(name="q", label="Profiili", measurement="nominal",
                   missing_values=[],
                   value_labels=[ValueLabel(value=float(i + 1), label=n)
                                 for i, n in enumerate(["A", "B", "C", "D"])])
    assert "radar" in _compatible(var)


def test_an_index_has_one_category_not_three():
    """`compute()` returns a single category for a scale variable — its own
    label, carrying the mean. The synthetic shape has to agree, or every
    suitability rule is answered about a question that does not exist."""
    q = Question(qid="q", text="Työelämäindeksi", kind="single", variables=("q",))
    model = QuestionModel(variables={"q": _scale()}, questions=[q])
    assert len(_quick_series(q, model, None).categories) == 1


def test_a_battery_still_has_one_category_per_member():
    """Measured too, but genuinely multi-dimensional — and a radar suits it."""
    members = {}
    for i in range(4):
        members[f"v{i}"] = Variable(name=f"v{i}", label=f"Väittämä {i}",
                                    measurement="scale", missing_values=[],
                                    value_labels=[])
    q = Question(qid="b", text="Battery", kind="battery",
                 variables=tuple(members))
    model = QuestionModel(variables=members, questions=[q])
    s = _quick_series(q, model, None)
    assert len(s.categories) == 4
    assert "radar" in _compatible_for(q, s)


def _compatible_for(q, series):
    from reportbuilder.api.routes_questions import _compatible_chart_types
    return _compatible_chart_types(q, series)
