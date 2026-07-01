"""Curation tests: which SAV columns become question-browser entries.

Covers the three exclusion predicates end-to-end through ``read_sav`` as well as
directly, using a hand-built SAV with metadata, constant-marker, and unlabeled
helper columns alongside real questions. Deterministic (only tmp_path I/O).
"""
from __future__ import annotations

import pandas as pd
import pyreadstat
import pytest

from reportbuilder.ingest.sav_reader import read_sav


def _write_sav(tmp_path, df, *, column_labels, value_labels=None, measures=None):
    path = tmp_path / "curation.sav"
    pyreadstat.write_sav(
        df,
        str(path),
        column_labels=column_labels,
        variable_value_labels=value_labels or {},
        variable_measure=measures or {},
    )
    return str(path)


@pytest.fixture
def curated(tmp_path):
    """A SAV mixing real questions with columns that must be curated out."""
    df = pd.DataFrame({
        "q1": [1.0, 2.0, 1.0, 2.0, 1.0],          # real single question
        "vrid": [10.0, 11.0, 12.0, 13.0, 14.0],   # metadata by NAME
        "wgt": [1.0, 1.1, 0.9, 1.0, 1.2],         # metadata by LABEL "weight"
        "TOTAALI": [1.0, 1.0, 1.0, 1.0, 1.0],     # constant marker (label==name, nunique 1)
        "seg": [0.0, 1.0, 0.0, 1.0, 1.0],         # unlabeled helper (label==name, no vls)
        "emp": [1.0, 2.0, 1.0, 2.0, 1.0],         # real: label "Employment Status" (NOT metadata)
    })
    path = _write_sav(
        tmp_path, df,
        column_labels={
            "q1": "Satisfaction",
            "vrid": "Response ID",
            "wgt": "weight",
            "TOTAALI": "TOTAALI",
            "seg": "seg",
            "emp": "Employment Status",
        },
        value_labels={
            "q1": {1: "Yes", 2: "No"},
            "emp": {1: "Employed", 2: "Unemployed"},
        },
    )
    return read_sav(path)


def _qids(model):
    return {q.qid for q in model.questions}


def test_all_columns_kept_in_variables(curated):
    _, model = curated
    assert set(model.variables) == {"q1", "vrid", "wgt", "TOTAALI", "seg", "emp"}


def test_real_question_kept(curated):
    _, model = curated
    assert "q1" in _qids(model)


def test_metadata_by_name_dropped_from_questions(curated):
    _, model = curated
    assert "vrid" not in _qids(model)


def test_metadata_by_label_weight_dropped(curated):
    _, model = curated
    assert "wgt" not in _qids(model)


def test_constant_marker_dropped(curated):
    _, model = curated
    assert "totaali" not in _qids(model)


def test_unlabeled_helper_dropped(curated):
    _, model = curated
    assert "seg" not in _qids(model)


def test_employment_status_is_not_metadata_and_kept(curated):
    # Label "Employment Status" must NOT match the exact metadata label "status".
    _, model = curated
    assert "emp" in _qids(model)


def test_only_real_questions_remain(curated):
    _, model = curated
    assert _qids(model) == {"q1", "emp"}


def test_dropped_columns_still_addressable_as_variables(curated):
    _, model = curated
    # Curated-out columns remain usable as classifying/secondary variables.
    assert model.variable("vrid").name == "vrid"
    assert model.variable("seg").name == "seg"
