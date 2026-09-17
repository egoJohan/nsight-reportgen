"""Renaming a one-variable question renames the variable it is.

"Slide 9. The legend says 'tyoelamaindeksi'. Is there any place where we could
correct this to display 'Työelämäindeksi'?"

There was not. A combo's secondary series is named from `sec.label or sec.name`
— the VARIABLE's label — while the material's rename box rewrote `Question.text`
and nothing else. So an author could rename the question, watch it change
everywhere a question is named, and still get the SAV's bare column name in the
one place they were looking at. The same holds for the classifying-variable
name, the battery member labels, and anything else read off the variable.

For a question that is exactly ONE variable, the question and the variable are
the same thing to the person doing the renaming, so the rename applies to both.
A battery is left alone: its members carry the statement wording, and one name
for the group would erase all of them. (Johan, 2026-09-17)
"""
from __future__ import annotations

import pytest

from reportbuilder.api.model_loader import _apply_labels
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable

pytestmark = pytest.mark.unit


def _model() -> QuestionModel:
    variables = {
        "tyoelamaindeksi": Variable("tyoelamaindeksi", "tyoelamaindeksi", "scale",
                                    (), frozenset()),
        "b1": Variable("b1", "Työni on merkityksellistä", "ordinal",
                       (ValueLabel(1.0, "Eri"), ValueLabel(5.0, "Samaa")), frozenset()),
        "b2": Variable("b2", "Saan tukea", "ordinal",
                       (ValueLabel(1.0, "Eri"), ValueLabel(5.0, "Samaa")), frozenset()),
    }
    questions = [
        Question(qid="tyoelamaindeksi", kind="single", text="tyoelamaindeksi",
                 variables=("tyoelamaindeksi",)),
        Question(qid="bat", kind="battery", text="Väittämät", variables=("b1", "b2")),
    ]
    return QuestionModel(variables=variables, questions=questions)


def test_the_question_is_renamed_as_before():
    out = _apply_labels(_model(), {"tyoelamaindeksi": "Työelämäindeksi"})
    assert out.question("tyoelamaindeksi").text == "Työelämäindeksi"


def test_the_variable_is_renamed_too():
    """The defect: this stayed "tyoelamaindeksi" and reached the combo legend."""
    out = _apply_labels(_model(), {"tyoelamaindeksi": "Työelämäindeksi"})
    assert out.variable("tyoelamaindeksi").label == "Työelämäindeksi"


def test_a_battery_keeps_its_members_own_wording():
    """One name for a group of statements would erase every statement."""
    out = _apply_labels(_model(), {"bat": "Nykyinen työnantaja"})
    assert out.variable("b1").label == "Työni on merkityksellistä"
    assert out.variable("b2").label == "Saan tukea"
    assert out.question("bat").text == "Nykyinen työnantaja"


def test_nothing_else_about_the_variable_moves():
    out = _apply_labels(_model(), {"tyoelamaindeksi": "Työelämäindeksi"})
    v = out.variable("tyoelamaindeksi")
    assert v.name == "tyoelamaindeksi" and v.measurement == "scale"


def test_no_overrides_is_the_same_model():
    m = _model()
    assert _apply_labels(m, {}) is m
