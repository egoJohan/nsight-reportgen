"""Task G.1: open-ended free-text variable detection (measurement="text").

A variable whose data column is mostly non-numeric AND has no usable numeric
value labels is classified as open-ended text and flagged non-chartable.
"""
from __future__ import annotations

import pandas as pd
import pyreadstat
import pytest

from reportbuilder import config
from reportbuilder.ingest.sav_reader import _is_text_variable, read_sav


# ---------------------------------------------------------------------------
# Unit: _is_text_variable
# ---------------------------------------------------------------------------


def test_freetext_column_no_labels_is_text():
    s = pd.Series(["Alzheimer potilas", "Lapsiperheiden kotipalvelu", "", "kotihoito"])
    assert _is_text_variable(s, ()) is True


def test_numeric_coded_column_is_not_text():
    s = pd.Series([1.0, 2.0, 1.0, 3.0])
    assert _is_text_variable(s, ()) is False


def test_column_with_value_labels_is_not_text():
    # Even if dtype is object, the presence of value labels means it is coded.
    s = pd.Series(["Alzheimer potilas", "x"])
    assert _is_text_variable(s, (("dummy",),)) is False


def test_all_null_column_is_not_text():
    s = pd.Series([None, None, float("nan")])
    assert _is_text_variable(s, ()) is False


# ---------------------------------------------------------------------------
# read_sav integration on a synthetic SAV with a free-text column
# ---------------------------------------------------------------------------


def test_read_sav_flags_freetext_variable(tmp_path):
    df = pd.DataFrame({
        "q1": [1.0, 2.0, 1.0, 3.0],
        "other": ["Alzheimer potilas", "kotihoito", "", "Lapsiperheiden kotipalvelu"],
    })
    path = tmp_path / "synthetic.sav"
    pyreadstat.write_sav(
        df, str(path),
        column_labels={"q1": "Satisfaction", "other": "Muut hoivapalvelut, mitkä?"},
        variable_value_labels={"q1": {1: "Poor", 2: "Good", 3: "Excellent"}},
    )
    _df, model = read_sav(str(path))
    assert model.variables["other"].measurement == "text"
    assert model.variables["q1"].measurement != "text"


# ---------------------------------------------------------------------------
# Real Attendo SAV: var13O28Othr (free text) vs var9 (coded categorical)
# ---------------------------------------------------------------------------


def test_attendo_freetext_var_is_text():
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo .sav not present")
    _df, model = read_sav(config.ATTENDO_SAV)
    # var13O28Othr "Muut hoivapalvelut, mitkä?" is open-ended free text.
    assert model.variables["var13O28Othr"].measurement == "text"
    # var9 "Miten identifioit itsesi" is coded categorical (Mieheksi/Naiseksi/...).
    assert model.variables["var9"].measurement == "categorical"
