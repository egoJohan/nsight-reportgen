"""A coded string column (few short values, each repeated many times) is a
CATEGORICAL, not an open-ended answer. The repetition ratio is the discriminator:
`Elamantilanne_muu` in the SuomalainenTyo material has only 5 distinct values and
is still a genuine open-end. (spec 2026-08-02 §1.1)"""
from __future__ import annotations

import pandas as pd

from reportbuilder.ingest.sav_reader import _is_text_variable


def _series(values):
    return pd.Series(values, dtype=object)


def test_two_coded_values_repeated_is_categorical():
    s = _series(["Pakkausilme 1", "Pakkausilme 2"] * 256)   # d=2, ratio=256
    assert _is_text_variable(s, ()) is False


def test_low_distinct_but_unrepeated_is_still_text():
    """Elamantilanne_muu: 5 distinct, 5 answers, ratio 1.0 — an open-end."""
    s = _series(["Olen eläkkeellä ja teen satunnaisia keikkoja",
                 "Opiskelen ja käyn töissä", "Yrittäjä", "Vanhempainvapaalla",
                 "Työtön, etsin töitä"])
    assert _is_text_variable(s, ()) is True


def test_twelve_distinct_low_ratio_is_still_text():
    """Rooli_muu: 12 distinct, 20 answers, ratio 1.7 — an open-end."""
    s = _series([f"vastaus {i}" for i in range(12)] + [f"vastaus {i}" for i in range(8)])
    assert _is_text_variable(s, ()) is True


def test_long_concept_label_is_still_categorical():
    """34 characters — must not be rejected. A maxlen of 30 would have."""
    s = _series(["Pakkausilme 1 – uusi punainen ilme",
                 "Pakkausilme 2 – vanha sininen ilme"] * 200)
    assert _is_text_variable(s, ()) is False


def test_boilerplate_paragraphs_stay_text():
    """The maxlen guard: two very long repeated blocks are not categories."""
    s = _series(["A" * 400, "B" * 400] * 200)
    assert _is_text_variable(s, ()) is True


def test_high_cardinality_open_end_is_text():
    s = _series([f"vapaa vastaus numero {i}" for i in range(300)])
    assert _is_text_variable(s, ()) is True


def test_blank_values_do_not_count_as_a_category():
    """Blank strings are not answers; they must not become a category or inflate
    the distinct count."""
    s = _series(["Pakkausilme 1", "Pakkausilme 2", "", "   "] * 100)
    assert _is_text_variable(s, ()) is False


def test_value_labelled_variable_is_never_text():
    s = _series([1.0, 2.0] * 50)
    assert _is_text_variable(s, (("x",),)) is False


def test_all_blank_series_stays_text():
    """A column nobody answered has no categories to offer. Leaving it `text`
    keeps it non-chartable, which is safer than a categorical with no values —
    so this rule deliberately does NOT rescue it."""
    assert _is_text_variable(_series(["", "  "]), ()) is True
