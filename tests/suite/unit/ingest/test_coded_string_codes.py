"""A coded string column is converted to CODES + value labels at ingest.

Marking it categorical was not enough: every path that charts a question assumes
numeric codes and value labels, so charting "Pakkausilme 1 tai 2" raised
`could not convert string to float` and the slide showed the
"no data" placeholder. Normalising once at ingest means no consumer needs a string case.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.ingest.sav_reader import _codes_for_coded_string


def test_values_become_codes_with_matching_labels():
    col = pd.Series(["Pakkausilme 2", "Pakkausilme 1", "Pakkausilme 2"])
    codes, labels = _codes_for_coded_string(col)
    assert labels == [(1.0, "Pakkausilme 1"), (2.0, "Pakkausilme 2")]
    assert list(codes) == [2.0, 1.0, 2.0]


def test_codes_follow_natural_order():
    col = pd.Series(["Polku 10", "Polku 2", "Polku 1"])
    _codes, labels = _codes_for_coded_string(col)
    assert [l for _c, l in labels] == ["Polku 1", "Polku 2", "Polku 10"]


def test_blanks_become_missing_not_a_category():
    col = pd.Series(["A", "", "  ", "B", None])
    codes, labels = _codes_for_coded_string(col)
    assert [l for _c, l in labels] == ["A", "B"]
    assert pd.isna(codes.iloc[1]) and pd.isna(codes.iloc[2]) and pd.isna(codes.iloc[4])


def test_the_mapping_is_stable_under_row_order():
    a = pd.Series(["B", "A", "B"])
    b = pd.Series(["A", "B", "A"])
    assert _codes_for_coded_string(a)[1] == _codes_for_coded_string(b)[1]
