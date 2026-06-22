"""Tests for Task 2.1: read_sav — variables, labels, value labels, measurement.

Covers REQ-C-02 (ingest captures definitions: names, labels, values, value labels),
REQ-D-01 (observation matrix shape preserved through ingest),
REQ-D-02 (numeric values handled uniformly),
REQ-D-04 (variable labels provide question text),
REQ-D-05 (value labels define explanation texts).
"""
from __future__ import annotations

import pandas as pd
import pyreadstat
import pytest

from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.question import QuestionModel, ValueLabel


@pytest.fixture
def synthetic_sav(tmp_path):
    df = pd.DataFrame({"q1": [1.0, 2.0, 1.0, 3.0], "age": [41.0, 52.0, 38.0, 60.0]})
    path = tmp_path / "synthetic.sav"
    pyreadstat.write_sav(
        df, str(path),
        column_labels={"q1": "Overall satisfaction", "age": "Respondent age"},
        variable_value_labels={"q1": {1: "Poor", 2: "Good", 3: "Excellent"}},
        variable_measure={"q1": "ordinal", "age": "scale"},
    )
    return str(path)


def test_returns_dataframe_and_question_model(synthetic_sav):
    result = read_sav(synthetic_sav)
    assert isinstance(result, tuple) and len(result) == 2
    df, model = result
    assert isinstance(df, pd.DataFrame)
    assert isinstance(model, QuestionModel)


def test_dataframe_shape(synthetic_sav):
    """Observation matrix shape (rows = respondents, cols = variables) is preserved. (REQ-D-01, REQ-D-02)"""
    df, _ = read_sav(synthetic_sav)
    assert list(df.columns) == ["q1", "age"]
    assert len(df) == 4


def test_variable_names(synthetic_sav):
    """Variable names are captured by read_sav. (REQ-C-02, REQ-D-03)"""
    _, model = read_sav(synthetic_sav)
    assert set(model.variables) == {"q1", "age"}


def test_variable_label(synthetic_sav):
    """Variable labels (description texts) are captured. (REQ-C-02, REQ-D-04)"""
    _, model = read_sav(synthetic_sav)
    assert model.variable("q1").label == "Overall satisfaction"
    assert model.variable("age").label == "Respondent age"


def test_value_labels_q1(synthetic_sav):
    """Value labels are captured per variable. (REQ-C-02, REQ-D-05)"""
    _, model = read_sav(synthetic_sav)
    assert model.variable("q1").value_labels == (
        ValueLabel(1.0, "Poor"),
        ValueLabel(2.0, "Good"),
        ValueLabel(3.0, "Excellent"),
    )


def test_value_labels_age_empty(synthetic_sav):
    _, model = read_sav(synthetic_sav)
    assert model.variable("age").value_labels == ()


def test_measurement_ordinal_becomes_categorical(synthetic_sav):
    _, model = read_sav(synthetic_sav)
    assert model.variable("q1").measurement == "categorical"


def test_measurement_scale(synthetic_sav):
    _, model = read_sav(synthetic_sav)
    assert model.variable("age").measurement == "scale"


def test_missing_values_empty_frozenset(synthetic_sav):
    _, model = read_sav(synthetic_sav)
    assert model.variable("q1").missing_values == frozenset()
    assert model.variable("age").missing_values == frozenset()


def test_questions_list_populated(synthetic_sav):
    # Task 2.3: questions are now populated — one per variable
    _, model = read_sav(synthetic_sav)
    assert len(model.questions) == 2
