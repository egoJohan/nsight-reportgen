"""Unit tests for reportbuilder.model.question (the QuestionModel layer).

Deterministic; no network/soffice. Asserts the REAL behavior of the frozen
dataclasses and QuestionModel lookups / missing-value labeling.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from reportbuilder.model.question import (
    Question,
    QuestionModel,
    ValueLabel,
    Variable,
)
from reportbuilder.testing.fixtures import tiny_question_model


# ---- construction ----------------------------------------------------------

def test_value_label_fields():
    vl = ValueLabel(1.0, "Yes")
    assert vl.value == 1.0
    assert vl.label == "Yes"


def test_variable_fields():
    var = Variable(
        name="q1",
        label="Satisfaction",
        measurement="categorical",
        value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
        missing_values=frozenset({9.0}),
    )
    assert var.name == "q1"
    assert var.label == "Satisfaction"
    assert var.measurement == "categorical"
    assert var.value_labels == (ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No"))
    assert var.missing_values == frozenset({9.0})


def test_question_fields():
    q = Question(qid="q1", kind="single", variables=("q1",), text="Satisfaction")
    assert q.qid == "q1"
    assert q.kind == "single"
    assert q.variables == ("q1",)
    assert q.text == "Satisfaction"


def test_scale_measurement_accepted():
    var = Variable("age", "Age", "scale", (), frozenset())
    assert var.measurement == "scale"


def test_multi_kind_and_multiple_variables_accepted():
    q = Question("grp", "multi", ("a", "b", "c"), "Grid")
    assert q.kind == "multi"
    assert q.variables == ("a", "b", "c")


# ---- frozen semantics ------------------------------------------------------

def test_value_label_is_frozen():
    vl = ValueLabel(1.0, "Yes")
    with pytest.raises(FrozenInstanceError):
        vl.label = "No"  # type: ignore[misc]


def test_variable_is_frozen():
    var = Variable("q1", "Satisfaction", "categorical", (), frozenset())
    with pytest.raises(FrozenInstanceError):
        var.name = "q2"  # type: ignore[misc]


def test_question_is_frozen():
    q = Question("q1", "single", ("q1",), "Satisfaction")
    with pytest.raises(FrozenInstanceError):
        q.qid = "q2"  # type: ignore[misc]


# ---- QuestionModel.question / variable -------------------------------------

def test_question_returns_matching_question():
    model = tiny_question_model()
    q = model.question("q1")
    assert isinstance(q, Question)
    assert q.qid == "q1"
    assert q.text == "Satisfaction"


def test_question_returns_second_question():
    model = tiny_question_model()
    assert model.question("age").qid == "age"


def test_question_unknown_qid_raises_keyerror():
    model = tiny_question_model()
    with pytest.raises(KeyError):
        model.question("nope")


def test_variable_returns_matching_variable():
    model = tiny_question_model()
    var = model.variable("q1")
    assert isinstance(var, Variable)
    assert var.name == "q1"
    assert var.label == "Satisfaction"


def test_variable_unknown_name_raises_keyerror():
    model = tiny_question_model()
    with pytest.raises(KeyError):
        model.variable("nope")


# ---- QuestionModel mutability (NOT frozen) ---------------------------------

def test_question_model_is_mutable_can_append_question():
    model = tiny_question_model()
    before = len(model.questions)
    model.questions.append(Question("new", "single", ("q1",), "New"))
    assert len(model.questions) == before + 1
    assert model.question("new").qid == "new"


def test_question_model_field_reassignment_allowed():
    model = tiny_question_model()
    model.questions = []  # not frozen -> allowed
    assert model.questions == []


# ---- missing_value_labels --------------------------------------------------

def _model_with_missing(missing, value_labels=()):
    var = Variable("x", "X", "categorical", tuple(value_labels), frozenset(missing))
    return QuestionModel(
        variables={"x": var},
        questions=[Question("x", "single", ("x",), "X")],
    )


def test_missing_value_labels_empty_when_none():
    model = _model_with_missing(set())
    assert model.missing_value_labels("x") == []


def test_missing_value_labels_uses_label_map():
    model = _model_with_missing({9.0}, [ValueLabel(9.0, "Don't know")])
    assert model.missing_value_labels("x") == [(9.0, "Don't know")]


def test_missing_value_labels_sorted_ascending_by_code():
    model = _model_with_missing(
        {9.0, 8.0, 7.0},
        [ValueLabel(9.0, "Nine"), ValueLabel(8.0, "Eight"), ValueLabel(7.0, "Seven")],
    )
    result = model.missing_value_labels("x")
    codes = [code for code, _ in result]
    assert codes == [7.0, 8.0, 9.0]
    assert result == [(7.0, "Seven"), (8.0, "Eight"), (9.0, "Nine")]


def test_missing_value_labels_fallback_integer_string():
    """No label entry -> fallback is the int-valued code as a bare string."""
    model = _model_with_missing({99.0})
    assert model.missing_value_labels("x") == [(99.0, "99")]


def test_missing_value_labels_fallback_float_string():
    """Non-integer code falls back to its float string, not an int string."""
    model = _model_with_missing({8.5})
    assert model.missing_value_labels("x") == [(8.5, "8.5")]


def test_missing_value_labels_mixed_labeled_and_fallback():
    model = _model_with_missing({9.0, 8.5}, [ValueLabel(9.0, "DK")])
    assert model.missing_value_labels("x") == [(8.5, "8.5"), (9.0, "DK")]


def test_missing_value_labels_uses_primary_variable_only():
    """Only the FIRST variable of the question is consulted."""
    primary = Variable("p", "P", "categorical", (), frozenset({1.0}))
    other = Variable("o", "O", "categorical", (), frozenset({2.0}))
    model = QuestionModel(
        variables={"p": primary, "o": other},
        questions=[Question("grp", "multi", ("p", "o"), "Grid")],
    )
    # code 2.0 from the second variable must not appear
    assert model.missing_value_labels("grp") == [(1.0, "1")]


def test_missing_value_labels_unknown_qid_raises_keyerror():
    model = tiny_question_model()
    with pytest.raises(KeyError):
        model.missing_value_labels("nope")


def test_tiny_model_no_missing_values():
    model = tiny_question_model()
    assert model.missing_value_labels("q1") == []
    assert model.missing_value_labels("age") == []
