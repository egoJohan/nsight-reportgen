"""Unit tests for the pure helpers and public reader of ``sav_reader``.

Deterministic: the only I/O is writing/reading a synthetic SAV under ``tmp_path``
(no network, no soffice). Behaviors are asserted against the real product code —
the product is the source of truth.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.ingest.sav_reader import (
    _is_constant_marker,
    _is_metadata,
    _is_text_variable,
    _is_unlabeled_helper,
    _measurement,
    _slug,
    _user_missing,
    read_sav,
    sav_file_label,
)
from reportbuilder.model.question import Variable
from reportbuilder.testing.fixtures import synthetic_sav


# ---- helpers ---------------------------------------------------------------

def _var(name: str, label: str, *, measurement: str = "categorical", value_labels=()) -> Variable:
    return Variable(
        name=name,
        label=label,
        measurement=measurement,
        value_labels=tuple(value_labels),
        missing_values=frozenset(),
    )


# ---- _slug -----------------------------------------------------------------

def test_slug_lowercases():
    assert _slug("VAR") == "var"


def test_slug_replaces_nonalnum_runs_with_single_dash():
    assert _slug("Var 18") == "var-18"


def test_slug_collapses_multiple_separators():
    assert _slug("a!!!b") == "a-b"


def test_slug_strips_leading_and_trailing_dashes():
    assert _slug("__abc__") == "abc"


def test_slug_keeps_internal_alnum():
    assert _slug("ABC_def9") == "abc-def9"


def test_slug_empty_after_strip_falls_back_to_name_lower():
    # All punctuation -> empty after strip -> name.lower() fallback.
    assert _slug("---") == "---"
    assert _slug("!!!") == "!!!"


def test_slug_non_ascii_dropped():
    assert _slug("café!!") == "caf"


# ---- _measurement ----------------------------------------------------------

def test_measurement_scale_lowercase():
    assert _measurement("scale") == "scale"


def test_measurement_scale_case_insensitive():
    assert _measurement("SCALE") == "scale"
    assert _measurement("Scale") == "scale"


def test_measurement_ordinal_is_categorical():
    assert _measurement("ordinal") == "categorical"


def test_measurement_nominal_is_categorical():
    assert _measurement("nominal") == "categorical"


def test_measurement_empty_is_categorical():
    assert _measurement("") == "categorical"


def test_measurement_none_is_categorical():
    assert _measurement(None) == "categorical"


# ---- _is_text_variable -----------------------------------------------------

def test_text_variable_false_when_any_value_labels():
    s = pd.Series(["alpha", "beta", "gamma"])
    assert _is_text_variable(s, ((1.0, "One"),)) is False


def test_text_variable_true_when_majority_non_numeric():
    s = pd.Series(["Alzheimer", "potilas", "vanhus", "1"])
    assert _is_text_variable(s, ()) is True


def test_text_variable_false_when_all_numeric():
    s = pd.Series([1, 2, 3, 4])
    assert _is_text_variable(s, ()) is False


def test_text_variable_false_at_exactly_half_non_numeric():
    # 2 of 4 fail coercion == 0.5, which is NOT > 0.5.
    s = pd.Series(["a", "b", "1", "2"])
    assert _is_text_variable(s, ()) is False


def test_text_variable_true_just_above_half():
    s = pd.Series(["a", "b", "c", "1"])
    assert _is_text_variable(s, ()) is True


def test_text_variable_all_null_is_false():
    s = pd.Series([None, None, None], dtype="object")
    assert _is_text_variable(s, ()) is False


def test_text_variable_ignores_nulls_in_ratio():
    s = pd.Series(["word", "word2", None, None])
    assert _is_text_variable(s, ()) is True


# ---- _user_missing ---------------------------------------------------------

def test_user_missing_none_is_empty():
    assert _user_missing(None) == frozenset()


def test_user_missing_empty_list_is_empty():
    assert _user_missing([]) == frozenset()


def test_user_missing_dict_single_point():
    assert _user_missing([{"lo": 9, "hi": 9}]) == frozenset({9.0})


def test_user_missing_dict_span_inclusive():
    assert _user_missing([{"lo": 8, "hi": 10}]) == frozenset({8.0, 9.0, 10.0})


def test_user_missing_tuple_span_inclusive():
    assert _user_missing([(1, 3)]) == frozenset({1.0, 2.0, 3.0})


def test_user_missing_tuple_single_point():
    assert _user_missing([(7, 7)]) == frozenset({7.0})


def test_user_missing_multiple_ranges_union():
    assert _user_missing([{"lo": 1, "hi": 1}, (4, 5)]) == frozenset({1.0, 4.0, 5.0})


def test_user_missing_returns_floats():
    codes = _user_missing([(9, 9)])
    assert all(isinstance(c, float) for c in codes)


# ---- _is_metadata ----------------------------------------------------------

def test_metadata_known_system_name():
    assert _is_metadata("vrid", "Response ID") is True


def test_metadata_extra_recode_name():
    assert _is_metadata("branch_numeric", "whatever") is True


def test_metadata_url_name_prefix():
    assert _is_metadata("URLregion", "Region from URL") is True


def test_metadata_name_prefix_is_case_insensitive():
    assert _is_metadata("urlProfile", "x") is True


def test_metadata_exact_label_status():
    assert _is_metadata("Q5", "status") is True


def test_metadata_exact_label_email():
    assert _is_metadata("Q5", "email") is True


def test_metadata_exact_label_weight():
    assert _is_metadata("wgt", "weight") is True


def test_metadata_exact_label_pid():
    assert _is_metadata("Q9", "pid") is True


def test_metadata_label_is_case_insensitive_and_stripped():
    assert _is_metadata("Q5", "  STATUS  ") is True


def test_metadata_label_prefix_url_underscore():
    assert _is_metadata("Q5", "URL_utm_source") is True


def test_metadata_label_prefix_hidden_value():
    assert _is_metadata("Q5", "Hidden value 3") is True


def test_metadata_employment_status_is_not_metadata():
    # Exact-label matching stays conservative: substring "status" must not match.
    assert _is_metadata("Q5", "Employment Status") is False


def test_metadata_substring_email_in_label_is_not_metadata():
    assert _is_metadata("Q5", "Please give us your email address") is False


def test_metadata_ordinary_question_is_not_metadata():
    assert _is_metadata("var1", "How satisfied are you overall") is False


# ---- _is_constant_marker ---------------------------------------------------

def test_constant_marker_true_for_unlabeled_constant_column():
    var = _var("TOTAALI", "TOTAALI")
    assert _is_constant_marker("TOTAALI", var, pd.Series([1, 1, 1])) is True


def test_constant_marker_true_for_all_empty_column():
    var = _var("TOTAALI", "TOTAALI")
    assert _is_constant_marker("TOTAALI", var, pd.Series([None, None], dtype="object")) is True


def test_constant_marker_false_when_values_vary():
    var = _var("TOTAALI", "TOTAALI")
    assert _is_constant_marker("TOTAALI", var, pd.Series([1, 2, 3])) is False


def test_constant_marker_false_when_has_value_labels():
    from reportbuilder.model.question import ValueLabel

    var = _var("TOTAALI", "TOTAALI", value_labels=(ValueLabel(1.0, "a"),))
    assert _is_constant_marker("TOTAALI", var, pd.Series([1, 1])) is False


def test_constant_marker_false_when_label_differs_from_name():
    var = _var("TOTAALI", "Total section divider")
    assert _is_constant_marker("TOTAALI", var, pd.Series([1, 1])) is False


def test_constant_marker_false_for_text_measurement():
    var = _var("TOTAALI", "TOTAALI", measurement="text")
    assert _is_constant_marker("TOTAALI", var, pd.Series([1, 1])) is False


# ---- _is_unlabeled_helper --------------------------------------------------

def test_unlabeled_helper_true_when_label_equals_name_and_no_labels():
    var = _var("Inhimilli", "Inhimilli")
    assert _is_unlabeled_helper("Inhimilli", var) is True


def test_unlabeled_helper_true_for_scale_aggregate():
    # Scale recode aggregates (varying data) are still unlabeled helpers.
    var = _var("MahdHyvaAr", "MahdHyvaAr", measurement="scale")
    assert _is_unlabeled_helper("MahdHyvaAr", var) is True


def test_unlabeled_helper_false_when_labeled():
    var = _var("x", "A real human label")
    assert _is_unlabeled_helper("x", var) is False


def test_unlabeled_helper_false_when_has_value_labels():
    from reportbuilder.model.question import ValueLabel

    var = _var("x", "x", value_labels=(ValueLabel(1.0, "a"),))
    assert _is_unlabeled_helper("x", var) is False


def test_unlabeled_helper_false_for_text():
    var = _var("comment_raw", "comment_raw", measurement="text")
    assert _is_unlabeled_helper("comment_raw", var) is False


# ---- sav_file_label --------------------------------------------------------

def test_sav_file_label_missing_path_returns_none_without_raising():
    assert sav_file_label("/no/such/file/here.sav") is None


def test_sav_file_label_synthetic_has_no_study_label(tmp_path):
    # The synthetic fixture writes no file-level label -> None.
    assert sav_file_label(synthetic_sav(tmp_path)) is None


# ---- read_sav (end-to-end on the synthetic SAV) ----------------------------

def test_read_sav_returns_dataframe_and_model(tmp_path):
    df, model = read_sav(synthetic_sav(tmp_path))
    assert isinstance(df, pd.DataFrame)
    assert model.__class__.__name__ == "QuestionModel"


def test_read_sav_has_five_rows(tmp_path):
    df, _ = read_sav(synthetic_sav(tmp_path))
    assert len(df) == 5


def test_read_sav_keeps_all_columns_as_variables(tmp_path):
    df, model = read_sav(synthetic_sav(tmp_path))
    assert set(model.variables) == set(df.columns) == {"q1", "m1", "m2", "age"}


def test_read_sav_q1_is_single_yes_no(tmp_path):
    _, model = read_sav(synthetic_sav(tmp_path))
    q = model.question("q1")
    assert q.kind == "single"
    var = model.variables["q1"]
    assert var.measurement == "categorical"
    assert [(vl.value, vl.label) for vl in var.value_labels] == [(1.0, "Yes"), (2.0, "No")]


def test_read_sav_age_is_scale_with_no_value_labels(tmp_path):
    _, model = read_sav(synthetic_sav(tmp_path))
    age = model.variables["age"]
    assert age.measurement == "scale"
    assert age.value_labels == ()


def test_read_sav_builds_a_question_per_column(tmp_path):
    _, model = read_sav(synthetic_sav(tmp_path))
    # No metadata/helper columns in the synthetic file -> one question each.
    assert {q.qid for q in model.questions} == {"q1", "m1", "m2", "age"}


def test_read_sav_question_text_from_variable_label(tmp_path):
    _, model = read_sav(synthetic_sav(tmp_path))
    assert model.question("q1").text == "Satisfaction"
    assert model.question("age").text == "Age"
