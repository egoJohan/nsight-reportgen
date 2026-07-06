"""Deterministic 'auto' resolution of the cross-tab percentage direction.

Percentages are of the STRONGER-segmenter variable's categories: a demographic
background (gender/age/region) outranks a derived segment, which outranks a plain
categorical, which outranks a Likert rating (the thing measured). The base variable
wins the denominator only when it strictly outranks the classifier; ties keep the
legacy 'classifier' direction.
"""
from __future__ import annotations

from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
from reportbuilder.model.report import (
    ChartSpec, NumberFormat, SortSpec, ElementToggles,
)
from reportbuilder.stats.percent_base import segmenter_score, resolve_percent_base


def _spec(classifying_var):
    return ChartSpec(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                     classifying_var=classifying_var, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s",
                     elements=ElementToggles())


def _likert():
    return Variable(name="op", label="Työ on tärkeää", measurement="categorical",
                    value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 8)),
                    missing_values=frozenset())


def _gender():
    return Variable(name="sukupuoli", label="Sukupuoli", measurement="categorical",
                    value_labels=(ValueLabel(1.0, "Mies"), ValueLabel(2.0, "Nainen"),
                                  ValueLabel(3.0, "Muu")),
                    missing_values=frozenset())


def _segment():
    return Variable(name="klusteri", label="Klusteri", measurement="categorical",
                    value_labels=tuple(ValueLabel(float(i), f"Segment {i}") for i in range(1, 8)),
                    missing_values=frozenset())


def test_score_likert_is_lowest():
    assert segmenter_score(_likert(), "Työ on tärkeää") == 0


def test_score_demographic_is_highest():
    assert segmenter_score(_gender(), "Sukupuoli") == 3


def test_score_derived_segment_is_middle():
    assert segmenter_score(_segment(), "Klusteri") == 2


def test_gender_base_segment_classifier_resolves_to_question():
    g, s = _gender(), _segment()
    model = QuestionModel(variables={"sukupuoli": g, "klusteri": s}, questions=[])
    q = Question(qid="sukupuoli", kind="single", variables=("sukupuoli",), text="Sukupuoli")
    assert resolve_percent_base(q, _spec("klusteri"), model) == "question"


def test_opinion_base_gender_classifier_resolves_to_classifier():
    op, g = _likert(), _gender()
    model = QuestionModel(variables={"op": op, "sukupuoli": g}, questions=[])
    q = Question(qid="op", kind="single", variables=("op",), text="Työ on tärkeää")
    assert resolve_percent_base(q, _spec("sukupuoli"), model) == "classifier"


def test_tie_keeps_legacy_classifier_direction():
    g = _gender()
    age = Variable(name="ika", label="Ikäryhmä", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "18-29"), ValueLabel(2.0, "30-44")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"sukupuoli": g, "ika": age}, questions=[])
    q = Question(qid="sukupuoli", kind="single", variables=("sukupuoli",), text="Sukupuoli")
    assert resolve_percent_base(q, _spec("ika"), model) == "classifier"


def test_no_classifier_is_classifier():
    op = _likert()
    model = QuestionModel(variables={"op": op}, questions=[])
    q = Question(qid="op", kind="single", variables=("op",), text="Työ on tärkeää")
    assert resolve_percent_base(q, _spec(None), model) == "classifier"
