"""GET /chart-types — the plugin-declared chart catalog + config schema.

The frontend renders the per-chart config form purely from this schema, so the
contract here (which knobs each chart type exposes) is what gates the UI.
"""
from __future__ import annotations

from unittest.mock import Mock

from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app


def _catalog() -> dict:
    client = TestClient(create_app(client=Mock()))
    resp = client.get("/chart-types")
    assert resp.status_code == 200
    return {c["id"]: c for c in resp.json()["chart_types"]}


def _keys(entry: dict) -> list[str]:
    return [f["key"] for f in entry["config"]]


def test_all_registered_types_present():
    cat = _catalog()
    for cid in ("vertical_bar", "horizontal_bar", "pie", "doughnut", "line",
                "radar", "combo", "funnel", "scatter", "wordcloud"):
        assert cid in cat, f"{cid} missing from /chart-types"


def test_multi_series_types_expose_classifying_var():
    cat = _catalog()
    for cid in ("vertical_bar", "horizontal_bar", "stacked_vertical_bar",
                "stacked_horizontal_bar", "line", "radar", "combo"):
        assert "classifying_var" in _keys(cat[cid]), (
            f"{cid} should expose a classifying variable"
        )


def test_single_series_types_hide_classifying_var():
    """The user's ask: pie/doughnut/funnel are single-series, so the classifying
    variable must NOT be part of their config."""
    cat = _catalog()
    for cid in ("pie", "doughnut", "funnel"):
        assert "classifying_var" not in _keys(cat[cid]), (
            f"{cid} is single-series and must not offer a classifying variable"
        )


def test_stacked_requires_classifying_var():
    cat = _catalog()
    for cid in ("stacked_vertical_bar", "stacked_horizontal_bar"):
        fld = next(f for f in cat[cid]["config"] if f["key"] == "classifying_var")
        assert fld.get("required") is True


def test_select_fields_carry_their_options():
    """Options are carried IN the schema (plugin-driven), not hardcoded in the UI."""
    cat = _catalog()
    stat = next(f for f in cat["pie"]["config"] if f["key"] == "statistic")
    assert stat["widget"] == "select"
    values = [o["value"] for o in stat["options"]]
    assert "pct" in values and "mean" in values


def test_scatter_and_wordcloud_are_note_only():
    cat = _catalog()
    assert _keys(cat["scatter"]) == ["note"]
    assert _keys(cat["wordcloud"]) == ["note"]
