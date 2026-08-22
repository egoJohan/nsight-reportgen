"""GET /chart-types — the plugin-declared chart catalog + config schema.

The frontend renders the per-chart config form purely from this schema, so the
contract here (which knobs each chart type exposes) is what gates the UI.
"""
from __future__ import annotations

from unittest.mock import Mock


def _catalog(rb_wire) -> dict:
    client = rb_wire(client=Mock())
    resp = client.get("/chart-types")
    assert resp.status_code == 200
    return {c["id"]: c for c in resp.json()["chart_types"]}


def _keys(entry: dict) -> list[str]:
    return [f["key"] for f in entry["config"]]


def test_all_registered_types_present(rb_wire):
    cat = _catalog(rb_wire)
    for cid in ("vertical_bar", "horizontal_bar", "pie", "doughnut", "line",
                "radar", "combo", "funnel", "scatter", "wordcloud"):
        assert cid in cat, f"{cid} missing from /chart-types"


def test_multi_series_types_expose_classifying_var(rb_wire):
    cat = _catalog(rb_wire)
    for cid in ("vertical_bar", "horizontal_bar", "stacked_vertical_bar",
                "stacked_horizontal_bar", "line", "radar", "combo"):
        assert "classifying_var" in _keys(cat[cid]), (
            f"{cid} should expose a classifying variable"
        )


def test_single_series_types_split_by_one_classifier(rb_wire):
    """Pie/doughnut/funnel split into up to three panels by a classifying variable
    (spec 2026-08-22). They DO take a classifier, but never a second one, a
    cross-tab layout, or a Total reference series — none of which a row of pies
    can express."""
    cat = _catalog(rb_wire)
    for cid in ("pie", "doughnut", "funnel"):
        keys = _keys(cat[cid])
        assert "classifying_var" in keys, (
            f"{cid} must offer a classifying variable to split into panels"
        )
        for absent in ("classifying_var_2", "xtab_layout", "show_total", "percent_base"):
            assert absent not in keys, (
                f"{cid} must not offer {absent}"
            )


def test_panel_chart_types_expose_classifying_var_for_configure_panel_warning(rb_wire):
    """CONTRACT for the configure panel's "too many groups" warning (spec
    2026-08-22, StepConfigure.tsx ClassifyingVarWidget). Nothing in the
    TypeScript enforces this: the classifying-variable picker — and with it the
    amber over-three-groups notice — only renders for pie/doughnut/funnel
    because THIS field is present in the catalog. If it silently disappears,
    the frontend warning silently stops firing (and the picker itself
    disappears) with no test in the web/ tree to catch it."""
    cat = _catalog(rb_wire)
    for cid in ("pie", "doughnut", "funnel"):
        assert "classifying_var" in _keys(cat[cid]), (
            f"{cid} must expose classifying_var — the configure panel's "
            f"classifying-variable picker (and its group-count warning) is "
            f"built purely from this schema field"
        )


def test_stacked_classifying_var_optional(rb_wire):
    """Total-only stacked bars are valid, so classifying_var is optional (present
    but not required)."""
    cat = _catalog(rb_wire)
    for cid in ("stacked_vertical_bar", "stacked_horizontal_bar"):
        fld = next(f for f in cat[cid]["config"] if f["key"] == "classifying_var")
        assert fld.get("required") in (False, None)


def test_select_fields_carry_their_options(rb_wire):
    """Options are carried IN the schema (plugin-driven), not hardcoded in the UI."""
    cat = _catalog(rb_wire)
    stat = next(f for f in cat["pie"]["config"] if f["key"] == "statistic")
    assert stat["widget"] == "select"
    values = [o["value"] for o in stat["options"]]
    assert "pct" in values and "mean" in values


def test_scatter_and_wordcloud_are_note_only(rb_wire):
    cat = _catalog(rb_wire)
    assert _keys(cat["scatter"]) == ["note"]
    assert _keys(cat["wordcloud"]) == ["note"]
