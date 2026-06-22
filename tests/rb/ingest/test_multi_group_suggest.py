"""Tests for suggest_multi_groups heuristic (TDD — Task 2.4, REQ-M-02, R2)."""
from __future__ import annotations

import pytest

from reportbuilder.ingest.multi_group import suggest_multi_groups
from reportbuilder.model.question import QuestionModel, Question, Variable, ValueLabel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _binary_var(name: str) -> Variable:
    return Variable(
        name=name,
        label=f"Brand {name}",
        measurement="categorical",
        value_labels=(ValueLabel(0.0, "Unchecked"), ValueLabel(1.0, "Checked")),
        missing_values=frozenset(),
    )


def _scale_var(name: str) -> Variable:
    return Variable(
        name=name,
        label=f"Scale {name}",
        measurement="scale",
        value_labels=(),
        missing_values=frozenset(),
    )


def _model(vars_: list[Variable]) -> QuestionModel:
    return QuestionModel(
        variables={v.name: v for v in vars_},
        questions=[],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_binary_grid_grouped_scale_excluded():
    """var18O45/46/47 (all binary) share prefix var18; age (scale) is excluded."""
    vars_ = [
        _binary_var("var18O45"),
        _binary_var("var18O46"),
        _binary_var("var18O47"),
        _scale_var("age"),
    ]
    model = _model(vars_)
    result = suggest_multi_groups(model)
    assert result == [("var18O45", "var18O46", "var18O47")]


def test_non_binary_and_singleton_not_grouped():
    """Non-binary categorical q1 (labels 1/2) and singleton binary var99O1 -> []."""
    non_binary = Variable(
        name="q1",
        label="Q1",
        measurement="categorical",
        value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
        missing_values=frozenset(),
    )
    singleton_binary = _binary_var("var99O1")
    model = _model([non_binary, singleton_binary])
    result = suggest_multi_groups(model)
    assert result == []
