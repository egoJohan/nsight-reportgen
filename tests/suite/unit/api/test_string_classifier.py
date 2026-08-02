"""A label-less string categorical is a legitimate classifying variable; a
generic TRUE/FALSE flag is not. (spec 2026-08-02 §1.2)"""
from __future__ import annotations

import pandas as pd

from reportbuilder.api import routes_questions as R
from reportbuilder.ingest.sav_reader import string_categories
from reportbuilder.model.question import ValueLabel, Variable


def _var(name, label, measurement="categorical"):
    return Variable(name=name, label=label, measurement=measurement,
                    value_labels=(), missing_values=frozenset())


def test_string_categories_are_natural_sorted():
    s = pd.Series(["Polku 10", "Polku 2", "Polku 1", "Polku 2"])
    assert string_categories(s) == ("Polku 1", "Polku 2", "Polku 10")


def test_string_categories_mixing_leading_digits_and_words():
    """A value starting with a digit next to one starting with a letter must not
    compare an int against a str — that raised TypeError on real data."""
    s = pd.Series(["1 - Ei lainkaan", "Ei osaa sanoa", "5 - Erittäin", "Muu"])
    assert string_categories(s) == ("1 - Ei lainkaan", "5 - Erittäin",
                                    "Ei osaa sanoa", "Muu")


def test_string_categories_handle_pure_numbers_and_words_together():
    s = pd.Series(["10", "9", "abc", "2"])
    assert string_categories(s) == ("2", "9", "10", "abc")


def test_string_categories_ignore_blanks_and_are_stable_under_shuffling():
    a = pd.Series(["Pakkausilme 2", "", "Pakkausilme 1", "   "])
    b = pd.Series(["Pakkausilme 1", "   ", "Pakkausilme 2", ""])
    assert string_categories(a) == string_categories(b) == ("Pakkausilme 1", "Pakkausilme 2")


def test_coded_string_column_is_segmentable():
    v = _var("var214", "Pakkausilme 1 tai 2")
    df = pd.DataFrame({"var214": ["Pakkausilme 1", "Pakkausilme 2"] * 100})
    assert R._segmentable(v, df) is True


def test_generic_true_false_flag_is_not_offered():
    v = _var("var131", "URL_Villas")
    df = pd.DataFrame({"var131": ["TRUE", "FALSE"] * 100})
    assert R._has_real_category_labels(v, df) is False


def test_named_segment_recode_is_offered():
    v = _var("var18", "URL_profiili")
    df = pd.DataFrame({"var18": ["enemmistoomistajat", "prosenttiomistajat",
                                 "vierailijat"] * 100})
    assert R._segmentable(v, df) is True
    assert R._has_real_category_labels(v, df) is True


def test_eleven_distinct_values_are_chartable_but_not_classifiable():
    """The 12/10 asymmetry: chartability and classifier eligibility differ, exactly
    as they already do for a value-labelled categorical."""
    v = _var("v", "Eleven")
    df = pd.DataFrame({"v": [f"cat {i}" for i in range(11)] * 20})
    assert R._segmentable(v, df) is False


def test_string_categorical_without_a_dataframe_is_not_offered():
    """No data, no categories — must not crash or guess."""
    v = _var("var214", "Pakkausilme 1 tai 2")
    assert R._segmentable(v, None) is False


def test_value_labelled_variable_is_unaffected_by_the_df_argument():
    v = Variable(name="clf", label="C", measurement="categorical",
                 value_labels=(ValueLabel(1.0, "A"), ValueLabel(2.0, "B")),
                 missing_values=frozenset())
    assert R._segmentable(v) is True
    assert R._segmentable(v, pd.DataFrame({"clf": [1.0, 2.0]})) is True


def test_category_labels_for_a_string_categorical_are_its_values():
    from reportbuilder.model.question import Question, QuestionModel

    v = _var("var214", "Pakkausilme 1 tai 2")
    model = QuestionModel(variables={"var214": v}, questions=[])
    q = Question(qid="var214", kind="single", variables=("var214",),
                 text="Pakkausilme 1 tai 2")
    df = pd.DataFrame({"var214": ["Pakkausilme 2", "Pakkausilme 1"] * 50})
    assert R._category_labels(model, q, df) == ["Pakkausilme 1", "Pakkausilme 2"]
