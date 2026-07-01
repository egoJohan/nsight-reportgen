"""Unit tests for reportbuilder.render.image._mpl — the PURE helpers only
(series decomposition, emptiness, label wrapping, decimals, value formatting).
No PNG is rendered here; matplotlib runs on the Agg backend."""
from __future__ import annotations

import pytest

from reportbuilder.model.report import NumberFormat
from reportbuilder.render.image import _mpl

from suite.unit.render import _builders as B


# ---- series_values ---------------------------------------------------------

def test_series_values_single_segment():
    s = B.build_series(("A", "B"), pct={"A": 10.0, "B": 20.0})
    cats, segs, data = _mpl.series_values(s)
    assert cats == ["A", "B"]
    assert segs == ["Total"]
    assert data == {"Total": [10.0, 20.0]}


def test_series_values_multi_segment_per_segment_lists():
    s = B.build_series(("A", "B"), segs=("G1", "G2"),
                       pct={"A": 10.0, "B": 20.0})
    cats, segs, data = _mpl.series_values(s)
    assert cats == ["A", "B"]
    assert segs == ["G1", "G2"]
    assert data == {"G1": [10.0, 20.0], "G2": [10.0, 20.0]}


def test_series_values_none_becomes_zero():
    s = B.build_series(("A", "B"), pct={"A": 10.0})   # B has no pct -> None -> 0.0
    _, _, data = _mpl.series_values(s)
    assert data["Total"] == [10.0, 0.0]


# ---- series_is_empty -------------------------------------------------------

def test_series_is_empty_no_categories():
    assert _mpl.series_is_empty(B.empty_series()) is True


def test_series_is_empty_all_zero():
    s = B.build_series(("A", "B"), pct={"A": 0.0, "B": 0.0})
    assert _mpl.series_is_empty(s) is True


def test_series_is_empty_all_none():
    s = B.build_series(("A", "B"))     # no pct set -> all None
    assert _mpl.series_is_empty(s) is True


def test_series_is_empty_false_when_a_value_present():
    s = B.build_series(("A", "B"), pct={"A": 0.0, "B": 5.0})
    assert _mpl.series_is_empty(s) is False


# ---- wrap_label / force_break_token ---------------------------------------

def test_wrap_label_short_text_unchanged():
    assert _mpl.wrap_label("short", 10) == "short"


def test_wrap_label_wraps_on_word_boundaries():
    out = _mpl.wrap_label("the quick brown fox jumps over", 10)
    assert "\n" in out
    assert all(len(line) <= 10 for line in out.split("\n"))
    # no words lost.
    assert out.replace("\n", " ").split() == "the quick brown fox jumps over".split()


def test_wrap_label_force_breaks_a_long_token():
    out = _mpl.wrap_label("x" * 25, 10)
    lines = out.split("\n")
    assert lines == ["xxxxxxxxxx", "xxxxxxxxxx", "xxxxx"]
    assert all(len(line) <= 10 for line in lines)


def test_force_break_token_short_unchanged():
    assert _mpl.force_break_token("abc", 10) == ["abc"]


def test_force_break_token_splits_into_chunks():
    assert _mpl.force_break_token("abcdefghij", 4) == ["abcd", "efgh", "ij"]


def test_wrap_label_capped_truncates_with_ellipsis():
    out = _mpl.wrap_label_capped("the quick brown fox jumps over the lazy dog", 8, 2)
    lines = out.split("\n")
    assert len(lines) == 2
    assert lines[-1].endswith("…")


def test_wrap_label_capped_no_ellipsis_when_it_fits():
    out = _mpl.wrap_label_capped("two words", 10, 3)
    assert "…" not in out


# ---- auto_decimals ---------------------------------------------------------

def test_auto_decimals_count_always_zero():
    assert _mpl.auto_decimals([3.0, 2.7], "count") == 0


def test_auto_decimals_pct_all_large_zero():
    assert _mpl.auto_decimals([60.0, 40.0], "pct") == 0


def test_auto_decimals_pct_small_values_one():
    assert _mpl.auto_decimals([5.4, 3.2], "pct") == 1


def test_auto_decimals_pct_trivial_fraction_zero():
    assert _mpl.auto_decimals([50.0, 30.0, 20.0], "pct") == 0


def test_auto_decimals_pct_all_large_zero_even_with_nontrivial_fraction():
    # When every value is >= 10 the `all_large` branch returns 0 up front,
    # regardless of fractional part or adjacent spread.
    assert _mpl.auto_decimals([50.2, 50.7], "pct") == 0


def test_auto_decimals_pct_small_value_with_tight_spread_one():
    # A value < 10 (not all_large) with a non-trivial fraction -> one decimal.
    assert _mpl.auto_decimals([8.2, 8.9], "pct") == 1


def test_auto_decimals_mean_wide_integer_range_zero():
    assert _mpl.auto_decimals([1.0, 8.0], "mean") == 0


def test_auto_decimals_mean_likert_one():
    assert _mpl.auto_decimals([3.2, 3.5], "mean") == 1


def test_auto_decimals_empty_mean_defaults_one():
    assert _mpl.auto_decimals([], "mean") == 1


def test_auto_decimals_empty_pct_defaults_zero():
    assert _mpl.auto_decimals([], "pct") == 0


# ---- format_value ----------------------------------------------------------

def test_format_value_pct_with_sign():
    assert _mpl.format_value(60.0, "pct", NumberFormat(), all_values=[60.0, 40.0]) == "60 %"


def test_format_value_pct_without_sign():
    fmt = NumberFormat(show_pct_sign=False)
    assert _mpl.format_value(60.0, "pct", fmt, all_values=[60.0, 40.0]) == "60"


def test_format_value_pct_small_gets_one_decimal():
    assert _mpl.format_value(5.4, "pct", NumberFormat(), all_values=[5.4, 3.2]) == "5.4 %"


def test_format_value_mean_uses_decimals():
    out = _mpl.format_value(3.25, "mean", NumberFormat(), all_values=[3.25, 3.5])
    assert out == "3.2"      # Likert-style -> 1 decimal


def test_format_value_count_is_integer():
    assert _mpl.format_value(3.0, "count", NumberFormat()) == "3"


def test_format_value_manual_mode_honours_pct_decimals():
    fmt = NumberFormat(mode="manual", pct_decimals=2)
    assert _mpl.format_value(60.0, "pct", fmt) == "60.00 %"


def test_format_value_manual_mode_honours_mean_decimals():
    fmt = NumberFormat(mode="manual", mean_decimals=3)
    assert _mpl.format_value(3.25, "mean", fmt) == "3.250"


def test_format_value_no_fmt_defaults_to_auto_pct_sign():
    assert _mpl.format_value(60.0, "pct", None, all_values=[60.0, 40.0]) == "60 %"
