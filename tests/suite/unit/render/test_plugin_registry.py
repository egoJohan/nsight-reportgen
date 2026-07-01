"""Unit tests for reportbuilder.render.plugins — registry, plugin() lookup,
register() idempotency, and the registry-driven suggest_chart_type()."""
from __future__ import annotations

import pytest

from reportbuilder.render import plugins as plugins_mod
from reportbuilder.render.plugins import (
    CHART_PLUGINS, ChartPlugin, plugin, register, suggest_chart_type,
)

from suite.unit.render import _builders as B


EXPECTED_IDS = [
    "vertical_bar", "horizontal_bar", "stacked_vertical_bar",
    "stacked_horizontal_bar", "line", "pie", "doughnut", "radar",
    "scatter", "funnel", "combo", "wordcloud",
]


# ---- Registry population ---------------------------------------------------

def test_all_twelve_ids_registered():
    assert set(EXPECTED_IDS) <= set(CHART_PLUGINS)
    assert len(CHART_PLUGINS) == 12


def test_registration_order_is_canonical():
    # dict preserves insertion (import) order; used for deterministic tie-breaks.
    assert list(CHART_PLUGINS) == EXPECTED_IDS


@pytest.mark.parametrize("cid", EXPECTED_IDS)
def test_plugin_dataclass_fields(cid):
    p = plugin(cid)
    assert isinstance(p, ChartPlugin)
    assert p.id == cid
    assert isinstance(p.label, str) and p.label
    assert callable(p.suitability)
    assert p.suggest is None or callable(p.suggest)
    assert isinstance(p.requires, tuple)
    assert isinstance(p.config_schema, tuple)


def test_scatter_declares_requires():
    assert plugin("scatter").requires == ("scatter_xy",)


# ---- plugin() lookup -------------------------------------------------------

def test_plugin_unknown_raises_keyerror_listing_known_types():
    with pytest.raises(KeyError) as ei:
        plugin("nope")
    msg = str(ei.value)
    assert "nope" in msg
    assert "Known types" in msg
    # the error enumerates the registered ids (sorted).
    assert "vertical_bar" in msg and "wordcloud" in msg


# ---- register() idempotency ------------------------------------------------

def test_register_is_idempotent_by_id():
    before = len(CHART_PLUGINS)
    existing = plugin("vertical_bar")
    register(existing)                 # re-register the same id
    assert len(CHART_PLUGINS) == before
    assert plugin("vertical_bar") is existing


def test_register_replaces_same_id_without_duplicating():
    before_ids = list(CHART_PLUGINS)
    original = plugin("vertical_bar")
    try:
        replacement = ChartPlugin(
            id="vertical_bar", label="Replaced", image_build=None,
            native_build=None, suitability=lambda q, s: 0.1, suggest=None,
        )
        register(replacement)
        assert list(CHART_PLUGINS) == before_ids     # no new key
        assert plugin("vertical_bar").label == "Replaced"
    finally:
        register(original)                            # restore for other tests
    assert plugin("vertical_bar") is original


# ---- suggest_chart_type ----------------------------------------------------

def test_suggest_single_series_partition_is_pie():
    # nominal parts-of-whole, few short slices -> pie is the natural default.
    assert suggest_chart_type(B.q("single"), B.few_short_series()) == "pie"


def test_suggest_many_long_single_question_is_horizontal_bar():
    assert suggest_chart_type(B.q("single"), B.many_long_series()) == "horizontal_bar"


def test_suggest_temporal_series_is_line():
    assert suggest_chart_type(B.q("single"), B.temporal_series()) == "line"


def test_suggest_battery_is_stacked_horizontal_bar():
    assert suggest_chart_type(B.q("battery"), B.partition_series()) == "stacked_horizontal_bar"


def test_suggest_multi_question_is_horizontal_bar_not_pie():
    result = suggest_chart_type(B.q("multi"), B.many_long_series())
    assert result == "horizontal_bar"
    assert result != "pie"


def test_suggest_empty_series_falls_back_to_vertical_bar():
    assert suggest_chart_type(B.q("single"), B.empty_series()) == "vertical_bar"


def test_suggest_swallows_exceptions_and_falls_back():
    # A plugin whose suggest raises must not break the picker.
    boom = ChartPlugin(id="_boom", label="Boom", image_build=None,
                       native_build=None, suitability=lambda q, s: None,
                       suggest=lambda q, s: (_ for _ in ()).throw(ValueError("x")))
    register(boom)
    try:
        # a shape nothing else suggests for -> fallback, not a crash.
        out = suggest_chart_type(B.q("single"),
                                 B.build_series(("Only",), pct=100.0, count=100.0))
        assert out in CHART_PLUGINS
    finally:
        del CHART_PLUGINS["_boom"]


def test_suggest_ignores_none_scores():
    # scatter/wordcloud/etc. return None from suggest and must be skipped.
    assert plugins_mod.plugin("scatter").suggest is None
    # a bare single category, nominal partition still returns a registered type.
    out = suggest_chart_type(B.q("single"),
                             B.build_series(("Yes", "No"), pct={"Yes": 50.0, "No": 50.0},
                                            count={"Yes": 50.0, "No": 50.0}))
    assert out in CHART_PLUGINS
