"""Which variables the classifying-variable picker offers, and in what order.

P-C-12 was the customer's own open point: nobody had defined how a variable
comes to appear in that picker. Every reported problem was the same — a variable
that should have been a classifier was not offered, and nothing said why: the
packaging study's *polku* column, Attendo's derived 0/1 segment flags, analyst
recodes whose names look like paradata.

The rule agreed on 2026-08-24 is that the heuristic RANKS rather than decides.
Background variables first, rating items after them, everything else on request —
and whatever an analyst marked for that dataset, always.
"""
from __future__ import annotations

from reportbuilder.api.routes_questions import (
    CLASSIFIER_TIER_BACKGROUND,
    CLASSIFIER_TIER_OTHER,
    CLASSIFIER_TIER_RATING,
    _classifier_tier,
    _why_not_offered,
)
from reportbuilder.model.question import ValueLabel, Variable


def _var(name, labels, measurement="categorical", label=None):
    return Variable(
        name=name, label=label if label is not None else name,
        measurement=measurement,
        value_labels=tuple(ValueLabel(float(i + 1), t) for i, t in enumerate(labels)),
        missing_values=frozenset())


def test_a_background_categorical_is_offered_first():
    v = _var("ikaluokka", ["18–24", "25–34", "35–44", "45+"], label="Ikäryhmä")
    assert _classifier_tier(v) == CLASSIFIER_TIER_BACKGROUND


def test_a_rating_item_is_offered_after_the_background_variables():
    """It used to be excluded outright.

    "Split this by how satisfied they are" is legitimate analysis, and it was
    impossible — rule 4 assumed nobody wanted it, on an assumption nobody had
    checked with the customer. Now it is offered, just not first.
    """
    v = _var("tyytyvaisyys",
             ["1 Täysin eri mieltä", "2", "3", "4", "5 Täysin samaa mieltä"],
             label="Kuinka tyytyväinen olet?")
    assert _classifier_tier(v) == CLASSIFIER_TIER_RATING


def test_a_bracket_categorical_is_background_not_a_rating_item():
    """Leading numbers do not make a scale: "500–999 €" is a segment."""
    v = _var("kulutus", ["0–499 €", "500–999 €", "1000–1999 €"], label="Kulutus")
    assert _classifier_tier(v) == CLASSIFIER_TIER_BACKGROUND


def test_a_high_cardinality_question_is_not_offered_by_default():
    v = _var("suosikki", [f"Brändi {i}" for i in range(20)], label="Suosikkibrändi")
    assert _classifier_tier(v) == CLASSIFIER_TIER_OTHER


def test_a_scale_variable_is_not_offered_by_default():
    v = _var("ika_vuosina", [], measurement="scale", label="Ikä vuosina")
    assert _classifier_tier(v) == CLASSIFIER_TIER_OTHER


def test_it_says_why_a_variable_is_not_offered():
    """Silence was the actual defect.

    An absent variable could not be told apart from one the file never had, so
    every case became a support question.
    """
    many = _var("suosikki", [f"Brändi {i}" for i in range(20)])
    assert "too many categories (20)" in _why_not_offered(many)

    scale = _var("ika_vuosina", [], measurement="scale")
    assert _why_not_offered(scale) == "not a categorical variable"

    # A generic yes/no recode. NOT named "url_flag" — that one is caught by the
    # metadata rule first, and "survey metadata" is the right answer for it.
    flags = _var("recode_a", ["TRUE", "FALSE"])
    assert _why_not_offered(flags) == "categories are flags, not names"

    meta = _var("vrid", ["TRUE", "FALSE"])   # a SmartSurvey system field
    assert _why_not_offered(meta) == "survey metadata"


def test_the_reason_is_empty_for_something_that_IS_offered():
    v = _var("alue", ["Etelä", "Länsi", "Itä", "Pohjoinen"], label="Alue")
    assert _classifier_tier(v) == CLASSIFIER_TIER_BACKGROUND
