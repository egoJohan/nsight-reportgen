"""Integration tests for the QUESTIONS browse API (routes_questions).

Covers the material-scoped, soffice-FREE endpoints:
  - GET  /chart-types                              (material-independent catalog)
  - GET  /materials/{mid}/questions                (browse + suggested chart type)
  - GET  /materials/{mid}/questions/{qid}/summary  (rich detail + distribution)
  - GET  /materials/{mid}/variables                (classifying-var picker source)
  - PUT  /materials/{mid}/grouping                 (stateless single/multi preview)

All tests use `client_mock` — the Mock DataHive returns synthetic SAV bytes, so
any material_id resolves. The synthetic SAV exposes single q1 (categorical
"Satisfaction": Yes/No), an `age` scale, and two single categoricals m1/m2 that
form a valid multi group. None of these routes touch LibreOffice.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# GET /chart-types
# ---------------------------------------------------------------------------


def test_chart_types_lists_all_twelve_with_config_schema(client_mock):
    """The catalog exposes every registered plugin with its declarative config
    schema (id/label/requires/config) — the frontend renders the per-chart form
    purely from this, so all 12 plugins must be present."""
    r = client_mock.get("/chart-types")
    assert r.status_code == 200
    types = r.json()["chart_types"]
    assert len(types) == 12
    ids = {t["id"] for t in types}
    # A representative spread across the plugin families.
    assert {"vertical_bar", "stacked_vertical_bar", "pie", "scatter",
            "wordcloud"} <= ids
    for t in types:
        assert set(t.keys()) == {"id", "label", "requires", "config"}
        assert isinstance(t["requires"], list)
        assert isinstance(t["config"], list)
    # config entries are declarative widget dicts (schema flows from plugins).
    vbar = next(t for t in types if t["id"] == "vertical_bar")
    assert all("key" in f and "widget" in f for f in vbar["config"])


def test_chart_types_material_independent(client_mock):
    """Same catalog regardless of material — it is safe to fetch once."""
    a = client_mock.get("/chart-types").json()
    b = client_mock.get("/chart-types").json()
    assert a == b


# ---------------------------------------------------------------------------
# GET /materials/{mid}/questions
# ---------------------------------------------------------------------------


def test_questions_returns_q1_with_expected_fields(client_mock):
    r = client_mock.get("/materials/mat-x/questions")
    assert r.status_code == 200
    questions = r.json()["questions"]
    by_qid = {q["qid"]: q for q in questions}
    assert "q1" in by_qid
    q1 = by_qid["q1"]
    expected_keys = {
        "qid", "kind", "variables", "text", "chartable", "non_chartable_reason",
        "suggested_chart_type", "compatible_chart_types", "missing_values",
        "values", "category_labels", "is_demographic",
    }
    assert expected_keys <= set(q1.keys())
    assert q1["kind"] == "single"
    assert q1["chartable"] is True
    # A chartable single-choice question is assigned a concrete suggested type.
    assert q1["suggested_chart_type"] is not None
    assert q1["suggested_chart_type"] in {t["id"] for t in
                                          client_mock.get("/chart-types").json()["chart_types"]}
    # Its compatible list is a non-empty subset of the catalog.
    assert q1["compatible_chart_types"]
    # Category labels reflect the Yes/No value labels.
    assert "Yes" in q1["category_labels"] and "No" in q1["category_labels"]


# ---------------------------------------------------------------------------
# GET /materials/{mid}/questions/{qid}/summary
# ---------------------------------------------------------------------------


def test_summary_returns_metadata_and_distribution_for_q1(client_mock):
    r = client_mock.get("/materials/mat-x/questions/q1/summary")
    assert r.status_code == 200
    s = r.json()
    assert s["qid"] == "q1"
    assert s["kind"] == "single"
    assert s["chartable"] is True
    assert s["statistic"] == "pct"
    assert s["base_n"] is not None
    # The computed distribution has one row per category with count + pct.
    dist = s["distribution"]
    assert dist and isinstance(dist, list)
    cats = {row["category"] for row in dist}
    assert {"Yes", "No"} <= cats
    for row in dist:
        assert set(row.keys()) == {"category", "count", "pct", "mean"}
    # Percentages sum to ~100 for a single-choice distribution.
    assert abs(sum(row["pct"] for row in dist) - 100.0) < 0.01


def test_summary_unknown_qid_is_404(client_mock):
    r = client_mock.get("/materials/mat-x/questions/does-not-exist/summary")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /materials/{mid}/variables
# ---------------------------------------------------------------------------


def test_variables_sorted_categorical_first_with_expected_keys(client_mock):
    r = client_mock.get("/materials/mat-x/variables")
    assert r.status_code == 200
    variables = r.json()["variables"]
    assert variables
    expected_keys = {"name", "label", "measurement", "n_values",
                     "aggregatable", "segmentable", "tickbox", "scale", "scale_key",
                     "scale_compat_key"}
    for v in variables:
        assert set(v.keys()) == expected_keys
    # Categorical variables sort ahead of scale variables (stable tiering).
    tier = [0 if v["measurement"] == "categorical" else 1 for v in variables]
    assert tier == sorted(tier)
    names = {v["name"] for v in variables}
    assert "q1" in names  # the categorical single is offered


# ---------------------------------------------------------------------------
# PUT /materials/{mid}/grouping
# ---------------------------------------------------------------------------


def test_regroup_invalid_groups_are_ignored(client_mock):
    """Regroup is lenient: invalid groups (too few / unknown / scale-or-non-tick)
    are silently skipped, returning 200 with the reshaped list."""
    def post(groups):
        return client_mock.post("/materials/mat-x/regroup", json={"groups": groups})
    assert post([{"kind": "multi", "variables": ["q1"]}]).status_code == 200
    assert post([{"kind": "multi", "variables": ["q1", "no-such-var"]}]).status_code == 200
    assert post([{"kind": "multi", "variables": ["q1", "age"]}]).status_code == 200


def test_regroup_valid_multi_returns_questions(client_mock):
    """m1/m2 form a valid multi group; regroup returns the reshaped question list."""
    r = client_mock.post("/materials/mat-x/regroup",
                         json={"groups": [{"kind": "multi", "variables": ["m1", "m2"]}], "singles": []})
    assert r.status_code == 200
    body = r.json()
    assert "questions" in body
    # The battery-suggestion hint list is always present (empty when nothing qualifies).
    assert isinstance(body.get("battery_suggestions"), list)
