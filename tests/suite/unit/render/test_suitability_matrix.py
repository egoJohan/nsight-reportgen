"""Unit tests for each chart plugin's suitability() hook — parametrized across
all 12 registered types, plus the notable per-type feasibility values."""
from __future__ import annotations

import pytest

from reportbuilder.render.plugins import CHART_PLUGINS, plugin

from suite.unit.render import _builders as B


ALL_IDS = list(CHART_PLUGINS)


# ---- Every plugin's suitability is total (float | None, never raises) ------

@pytest.mark.parametrize("cid", ALL_IDS)
@pytest.mark.parametrize("series_factory", [
    B.few_short_series, B.many_long_series, B.partition_series,
    B.mean_series, B.temporal_series, B.descending_series,
    B.multi_group_series, B.empty_series,
], ids=lambda f: f.__name__)
def test_suitability_returns_float_or_none(cid, series_factory):
    q = B.q("single")
    result = plugin(cid).suitability(q, series_factory())
    assert result is None or isinstance(result, float)


# ---- vertical_bar ----------------------------------------------------------

def test_vertical_bar_high_for_few_short():
    assert plugin("vertical_bar").suitability(B.q(), B.few_short_series()) == 0.80


def test_vertical_bar_low_for_many_long():
    assert plugin("vertical_bar").suitability(B.q(), B.many_long_series()) == 0.35


# ---- horizontal_bar --------------------------------------------------------

def test_horizontal_bar_higher_for_many_long():
    assert plugin("horizontal_bar").suitability(B.q(), B.many_long_series()) == 0.85


def test_horizontal_bar_moderate_for_few_short():
    assert plugin("horizontal_bar").suitability(B.q(), B.few_short_series()) == 0.55


# ---- pie / doughnut (identical precondition) -------------------------------

def test_pie_none_unless_partition():
    assert plugin("pie").suitability(B.q(), B.nonpartition_series()) is None


def test_pie_none_for_mean_statistic():
    assert plugin("pie").suitability(B.q(), B.mean_series()) is None


def test_pie_none_for_multi_series():
    assert plugin("pie").suitability(B.q(), B.multi_group_series()) is None


def test_pie_value_for_small_partition():
    assert plugin("pie").suitability(B.q(), B.few_short_series()) == 0.75


def test_pie_lower_value_for_large_partition():
    cats = tuple(f"c{i}" for i in range(8))
    big = B.build_series(cats, statistic="pct", base=100,
                         pct={c: 12.5 for c in cats}, count={c: 12.5 for c in cats})
    assert plugin("pie").suitability(B.q(), big) == 0.50


def test_doughnut_matches_pie_suitability():
    s = B.few_short_series()
    assert plugin("doughnut").suitability(B.q(), s) == plugin("pie").suitability(B.q(), s)
    assert plugin("doughnut").suitability(B.q(), B.mean_series()) is None


# ---- scatter / wordcloud always None ---------------------------------------

@pytest.mark.parametrize("cid", ["scatter", "wordcloud"])
@pytest.mark.parametrize("series_factory", [
    B.few_short_series, B.many_long_series, B.temporal_series, B.mean_series,
], ids=lambda f: f.__name__)
def test_scatter_wordcloud_always_none(cid, series_factory):
    assert plugin(cid).suitability(B.q(), series_factory()) is None


# ---- funnel reads actual values (descending-ness) --------------------------

def test_funnel_high_for_descending():
    assert plugin("funnel").suitability(B.q(), B.descending_series()) == 0.85


def test_funnel_lower_for_non_descending():
    assert plugin("funnel").suitability(B.q(), B.ascending_series()) == 0.50


def test_funnel_low_for_too_few_categories():
    assert plugin("funnel").suitability(B.q(), B.few_short_series()) == 0.30


def test_funnel_low_for_multi_series():
    assert plugin("funnel").suitability(B.q(), B.multi_group_series()) == 0.30


# ---- line ------------------------------------------------------------------

def test_line_high_for_temporal():
    assert plugin("line").suitability(B.q(), B.temporal_series()) == 0.90


def test_line_none_for_multi_question():
    assert plugin("line").suitability(B.q("multi"), B.temporal_series()) is None


def test_line_moderate_for_three_plus_categories():
    assert plugin("line").suitability(B.q(), B.descending_series()) == 0.60


def test_line_low_for_few_categories():
    assert plugin("line").suitability(B.q(), B.few_short_series()) == 0.35


# ---- radar -----------------------------------------------------------------

def test_radar_high_for_four_plus():
    assert plugin("radar").suitability(B.q(), B.partition_series()) == 0.80


def test_radar_low_for_few():
    assert plugin("radar").suitability(B.q(), B.few_short_series()) == 0.40


# ---- stacked variants ------------------------------------------------------

def test_stacked_vertical_bar_high_for_likert_width():
    assert plugin("stacked_vertical_bar").suitability(B.q(), B.partition_series()) == 0.75


def test_stacked_vertical_bar_low_for_few():
    assert plugin("stacked_vertical_bar").suitability(B.q(), B.few_short_series()) == 0.40


def test_stacked_horizontal_bar_high_for_multi_series():
    assert plugin("stacked_horizontal_bar").suitability(B.q(), B.multi_group_series()) == 0.80


def test_stacked_horizontal_bar_battery_suggests_1_20():
    # the notable suggest fact for the battery grid.
    assert plugin("stacked_horizontal_bar").suggest(B.q("battery"), B.partition_series()) == 1.20


def test_stacked_horizontal_bar_suggest_none_for_non_battery():
    assert plugin("stacked_horizontal_bar").suggest(B.q("single"), B.partition_series()) is None


# ---- combo -----------------------------------------------------------------

def test_combo_higher_for_multi_series():
    assert plugin("combo").suitability(B.q(), B.multi_group_series()) == 0.60


def test_combo_moderate_for_single_series():
    assert plugin("combo").suitability(B.q(), B.few_short_series()) == 0.45
