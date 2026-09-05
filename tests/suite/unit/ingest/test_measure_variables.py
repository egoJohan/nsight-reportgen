"""A continuous measure is a question you can chart the mean of.

Reported: "järjestelmä ei lataa lainkaan sisään scale-määrityksellä olevia
muuttujia joista keskiarvoja luontevasti lasketaan."

The customer's own definition of the class: "when a variable is continuous
scale-type it can take a huge number of values that mean nothing individually,
so it has no value labels; you cannot draw a distribution from it, but it is
excellent for mean charts." That is shape, not naming — so this is decided on
shape and no rule mentions `index_` or `rcd_`.

An unlabelled CATEGORICAL column is a different animal — a 0/1 analyst flag,
whose mean is meaningless — and stays out.
"""
from __future__ import annotations

import pandas as pd
import pyreadstat
import pytest

from reportbuilder.ingest.sav_reader import read_sav


@pytest.fixture
def sav(tmp_path):
    path = tmp_path / "measures.sav"
    df = pd.DataFrame({
        "tyoelamaindeksi": [50.0 + i % 400 * 0.13 for i in range(200)],
        "index_tyojatoimeentulo": [float(i % 7 + 1) for i in range(200)],
        "Ika": [float(20 + i % 55) for i in range(200)],
        "flag_asiakas": [float(i % 2) for i in range(200)],
        "sukupuoli": [float(i % 2 + 1) for i in range(200)],
    })
    pyreadstat.write_sav(
        df, str(path),
        # An index is exported with no label of its own — the column name is all
        # there is. That is exactly what used to exclude it.
        column_labels={"tyoelamaindeksi": None, "index_tyojatoimeentulo": None,
                       "Ika": "Minkä ikäinen olet?", "flag_asiakas": None,
                       "sukupuoli": "Sukupuoli"},
        variable_value_labels={"sukupuoli": {1: "Nainen", 2: "Mies"}},
        variable_measure={"tyoelamaindeksi": "scale", "index_tyojatoimeentulo": "scale",
                          "Ika": "scale", "flag_asiakas": "nominal",
                          "sukupuoli": "nominal"},
    )
    return str(path)


def _qids(model):
    return {v for q in model.questions for v in q.variables}


def test_an_unlabelled_continuous_measure_is_a_question(sav):
    _df, model = read_sav(sav)
    assert "tyoelamaindeksi" in _qids(model)
    assert "index_tyojatoimeentulo" in _qids(model)


def test_a_labelled_one_still_is(sav):
    _df, model = read_sav(sav)
    assert "Ika" in _qids(model)


def test_an_unlabelled_categorical_flag_still_is_not(sav):
    """Its mean is not a finding — it is an analyst's 0/1 working column."""
    _df, model = read_sav(sav)
    assert "flag_asiakas" not in _qids(model)


def test_it_is_still_available_as_a_classifying_variable(sav):
    _df, model = read_sav(sav)
    assert "flag_asiakas" in model.variables
