"""Tests for apply_groups (TDD — Task 2.5, REQ-C-06, M-02)."""
from __future__ import annotations

import pytest

from reportbuilder.ingest.multi_group import apply_groups
from reportbuilder.model.question import QuestionModel, Question, Variable, ValueLabel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _binary_var(name: str, label: str) -> Variable:
    return Variable(
        name=name,
        label=label,
        measurement="categorical",
        value_labels=(ValueLabel(0.0, "Unchecked"), ValueLabel(1.0, "Checked")),
        missing_values=frozenset(),
    )


def _scale_var(name: str, label: str) -> Variable:
    return Variable(
        name=name,
        label=label,
        measurement="scale",
        value_labels=(),
        missing_values=frozenset(),
    )


def _single(name: str) -> Question:
    return Question(qid=name.lower(), kind="single", variables=(name,), text=name)


def _model() -> QuestionModel:
    """Two binary vars sharing prefix var18 + a scale var."""
    vars_ = [
        _binary_var("var18O45", "Aided: Attendo"),
        _binary_var("var18O46", "Aided: Esperi"),
        _scale_var("age", "Age"),
    ]
    questions = [_single(v.name) for v in vars_]
    return QuestionModel(
        variables={v.name: v for v in vars_},
        questions=questions,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_apply_groups_creates_multi_question():
    """Grouped vars produce exactly one multi Question with the right members."""
    model = _model()
    result = apply_groups(model, [("var18O45", "var18O46")])

    multi_qs = [q for q in result.questions if q.kind == "multi"]
    assert len(multi_qs) == 1
    assert multi_qs[0].variables == ("var18O45", "var18O46")


def test_apply_groups_ungrouped_stays_single():
    """Ungrouped variable (age) keeps its single Question."""
    model = _model()
    result = apply_groups(model, [("var18O45", "var18O46")])

    single_qs = [q for q in result.questions if q.kind == "single"]
    assert len(single_qs) == 1
    assert single_qs[0].variables == ("age",)


def test_apply_groups_no_duplicate_singles_for_grouped_members():
    """No single Question should exist whose variables intersect the grouped set."""
    model = _model()
    grouped_names = {"var18O45", "var18O46"}
    result = apply_groups(model, [("var18O45", "var18O46")])

    for q in result.questions:
        if q.kind == "single":
            assert not (set(q.variables) & grouped_names), (
                f"Single question {q.qid!r} still references grouped member(s)"
            )


def test_apply_groups_variables_dict_unchanged():
    """The variables dict in the returned model still has all three keys."""
    model = _model()
    result = apply_groups(model, [("var18O45", "var18O46")])

    assert set(result.variables.keys()) == {"var18O45", "var18O46", "age"}


def test_apply_groups_multi_has_nonempty_qid_and_text():
    """The multi Question has a non-empty qid and text derived from the common label stem."""
    model = _model()
    result = apply_groups(model, [("var18O45", "var18O46")])

    multi_q = next(q for q in result.questions if q.kind == "multi")
    assert multi_q.qid, "qid must be non-empty"
    assert multi_q.text, "text must be non-empty"
    # Labels are "Aided: Attendo" and "Aided: Esperi" — common stem is "Aided"
    assert "Aided" in multi_q.text
