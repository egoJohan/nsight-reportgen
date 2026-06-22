"""Tests for Task 2.3: read_sav — one single Question per variable."""
from __future__ import annotations

import pandas as pd
import pyreadstat
import pytest

from reportbuilder.ingest.sav_reader import read_sav


@pytest.fixture
def synthetic_sav(tmp_path):
    df = pd.DataFrame({"q1": [1.0, 2.0, 3.0], "age": [25.0, 40.0, 55.0]})
    path = tmp_path / "questions.sav"
    pyreadstat.write_sav(
        df, str(path),
        column_labels={"q1": "Satisfaction", "age": "Age"},
        variable_value_labels={"q1": {1: "Low", 2: "Medium", 3: "High"}},
    )
    return str(path)


def test_question_count(synthetic_sav):
    _, model = read_sav(synthetic_sav)
    assert len(model.questions) == 2


def test_q1_question_kind(synthetic_sav):
    _, model = read_sav(synthetic_sav)
    q = next(q for q in model.questions if q.variables == ("q1",))
    assert q.kind == "single"


def test_q1_question_variables(synthetic_sav):
    _, model = read_sav(synthetic_sav)
    q = next(q for q in model.questions if q.variables == ("q1",))
    assert q.variables == ("q1",)


def test_q1_question_text(synthetic_sav):
    _, model = read_sav(synthetic_sav)
    q = next(q for q in model.questions if q.variables == ("q1",))
    assert q.text == "Satisfaction"


def test_q1_question_qid_nonempty(synthetic_sav):
    _, model = read_sav(synthetic_sav)
    q = next(q for q in model.questions if q.variables == ("q1",))
    assert q.qid  # non-empty string


def test_model_question_lookup(synthetic_sav):
    _, model = read_sav(synthetic_sav)
    q = next(q for q in model.questions if q.variables == ("q1",))
    assert model.question(q.qid) is q


def test_model_variable_lookup_via_question(synthetic_sav):
    _, model = read_sav(synthetic_sav)
    q = next(q for q in model.questions if q.variables == ("q1",))
    assert model.variable(q.variables[0]).name == q.variables[0]
