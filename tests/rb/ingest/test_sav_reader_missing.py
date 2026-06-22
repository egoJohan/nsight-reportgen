"""Tests for Task 2.2: read_sav — user-missing codes and Sysmis.

Covers REQ-D-06 (per-question missing-values definition) and
REQ-MV-02 (two kinds of missing: Sysmis and user-defined).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pyreadstat
import pytest

from reportbuilder.ingest.sav_reader import read_sav


@pytest.fixture
def sav_with_missing(tmp_path):
    df = pd.DataFrame({"q1": [1.0, 2.0, 99.0, np.nan]})   # row 2 = user-missing 99; row 3 = Sysmis
    path = tmp_path / "missing.sav"
    pyreadstat.write_sav(
        df, str(path),
        column_labels={"q1": "Satisfaction"},
        variable_value_labels={"q1": {1: "Low", 2: "High", 99: "Don't know"}},
        missing_ranges={"q1": [{"lo": 99, "hi": 99}]},
    )
    return str(path)


def test_user_missing_code_in_missing_values(sav_with_missing):
    """User-defined missing code 99 must appear in missing_values. (REQ-D-06, REQ-MV-02)"""
    _, model = read_sav(sav_with_missing)
    assert model.variable("q1").missing_values == frozenset({99.0})


def test_sysmis_is_nan_in_dataframe(sav_with_missing):
    """Sysmis row stays as NaN in the DataFrame. (REQ-MV-02)"""
    df, _ = read_sav(sav_with_missing)
    assert pd.isna(df["q1"].iloc[3])


def test_user_missing_value_survives_in_frame(sav_with_missing):
    """With user_missing=True the 99 value must remain as-is (not collapsed to NaN)."""
    df, _ = read_sav(sav_with_missing)
    assert df["q1"].iloc[2] == 99.0


def test_missing_values_are_not_nan(sav_with_missing):
    """All codes in missing_values must be non-NaN floats."""
    _, model = read_sav(sav_with_missing)
    for code in model.variable("q1").missing_values:
        assert not pd.isna(code), f"NaN must not appear in missing_values, got {code}"


def test_missing_values_type_is_frozenset(sav_with_missing):
    """missing_values must be a frozenset."""
    _, model = read_sav(sav_with_missing)
    assert isinstance(model.variable("q1").missing_values, frozenset)
