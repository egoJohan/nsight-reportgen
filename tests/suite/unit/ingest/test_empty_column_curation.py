"""A column nobody answered is not a question.

The Erisan material carries var319 ("m") and var320 ("p") with 0 answers out of
511. Marking them non-chartable was not enough: they still occupied a row in
Select that could not be used for anything — and once one was in a report it
could not be unticked either.
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.ingest.sav_reader import _is_empty_column


def test_all_null_column_is_empty():
    assert _is_empty_column(pd.Series([None, None, None])) is True


def test_all_blank_strings_column_is_empty():
    """var319/var320 hold "" rather than nulls."""
    assert _is_empty_column(pd.Series(["", "   ", ""])) is True


def test_a_column_with_one_answer_is_not_empty():
    assert _is_empty_column(pd.Series(["", None, "x"])) is False


def test_a_numeric_column_with_zeros_is_not_empty():
    """0 is an answer, not a blank."""
    assert _is_empty_column(pd.Series([0.0, 0.0])) is False


def test_the_erisan_empty_columns_are_not_questions():
    import pathlib

    import pytest

    from reportbuilder.ingest.sav_reader import read_sav

    path = pathlib.Path("work/demo-store/materials/mat-erisan.sav")
    if not path.exists():
        pytest.skip("mat-erisan not available locally")
    df, model = read_sav(str(path))
    qids = {q.qid for q in model.questions}
    assert "var319" not in qids and "var320" not in qids
    # still present as VARIABLES — curation drops them from the question list only
    assert "var319" in model.variables and "var320" in model.variables
