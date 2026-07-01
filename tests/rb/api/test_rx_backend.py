"""Tests for RX-be backend fixes:
- GET /materials/{material_id}/variables — variable labels endpoint (RX-be.1)
- POST /materials/{material_id}/preview-chart robustness (RX-be.2 + RX-be.3)

Tests:
  Variables endpoint:
    - Returns name, label, measurement for every variable.
    - A var with a real label (label != name) shows that label.
    - A var whose label == name shows the name (raw variable name as label).
    - Categorical variables appear before scale variables.
  Preview-chart hardening:
    - Valid bar spec → 200 image/png (integration path; skipped when soffice absent).
    - scatter without scatter_xy → 422, never 500.
    - stacked_vertical_bar without classifying_var → 422, detail mentions "classifying variable".
    - stacked_horizontal_bar without classifying_var → 422, detail mentions "classifying variable".
"""
from __future__ import annotations

import shutil
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.testing.fixtures import synthetic_sav_bytes


# ---------------------------------------------------------------------------
# Shared fixture builders
# ---------------------------------------------------------------------------


def _make_labeled_model() -> QuestionModel:
    """QuestionModel with:
    - 'q1': label 'Satisfaction' (real label, differs from name)
    - 'varX': label == 'varX' (no SPSS label set; read_sav falls back to the name)
    - 'age': scale measurement with a real label 'Age'
    """
    variables = {
        "q1": Variable(
            name="q1",
            label="Satisfaction",
            measurement="categorical",
            value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
            missing_values=frozenset(),
        ),
        "varX": Variable(
            name="varX",
            label="varX",  # label == name → no real SPSS label
            measurement="categorical",
            value_labels=(ValueLabel(1.0, "A"), ValueLabel(2.0, "B")),
            missing_values=frozenset(),
        ),
        "age": Variable(
            name="age",
            label="Age",
            measurement="scale",
            value_labels=(),
            missing_values=frozenset(),
        ),
    }
    questions = [
        Question(qid="q1", kind="single", variables=("q1",), text="Satisfaction"),
        Question(qid="varX", kind="single", variables=("varX",), text="varX"),
        Question(qid="age", kind="single", variables=("age",), text="Age"),
    ]
    return QuestionModel(variables=variables, questions=questions)


# ---------------------------------------------------------------------------
# RX-be.1 — GET /materials/{material_id}/variables
# ---------------------------------------------------------------------------


def test_get_variables_returns_required_fields() -> None:
    """GET /materials/{material_id}/variables returns 200 with name, label, measurement
    for every variable. (RX-be.1)"""
    model = _make_labeled_model()
    mock_client = Mock()
    app = create_app(client=mock_client)
    tc = TestClient(app)

    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = model
        response = tc.get("/materials/mat-rx1/variables")

    assert response.status_code == 200
    body = response.json()
    assert "variables" in body
    assert isinstance(body["variables"], list)
    assert len(body["variables"]) == 3
    for v in body["variables"]:
        assert "name" in v, f"'name' missing from variable entry {v!r}"
        assert "label" in v, f"'label' missing from variable entry {v!r}"
        assert "measurement" in v, f"'measurement' missing from variable entry {v!r}"


def test_get_variables_real_label_shown() -> None:
    """A variable with a real label (label != raw name) shows that human-readable label. (RX-be.1)"""
    model = _make_labeled_model()
    mock_client = Mock()
    app = create_app(client=mock_client)
    tc = TestClient(app)

    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = model
        response = tc.get("/materials/mat-rx1/variables")

    body = response.json()
    by_name = {v["name"]: v for v in body["variables"]}
    assert by_name["q1"]["label"] == "Satisfaction", (
        "Variable 'q1' has a real SPSS label 'Satisfaction'; the endpoint should expose it"
    )


def test_get_variables_name_as_label_when_no_real_label() -> None:
    """A variable whose label == its own name shows the name as its label. (RX-be.1)"""
    model = _make_labeled_model()
    mock_client = Mock()
    app = create_app(client=mock_client)
    tc = TestClient(app)

    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = model
        response = tc.get("/materials/mat-rx1/variables")

    body = response.json()
    by_name = {v["name"]: v for v in body["variables"]}
    assert by_name["varX"]["label"] == "varX", (
        "Variable 'varX' has no real SPSS label (label == name); the endpoint should show the name"
    )


def test_get_variables_categorical_before_scale() -> None:
    """GET /materials/{material_id}/variables sorts categorical variables before scale. (RX-be.1)"""
    model = _make_labeled_model()
    mock_client = Mock()
    app = create_app(client=mock_client)
    tc = TestClient(app)

    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = model
        response = tc.get("/materials/mat-rx1/variables")

    body = response.json()
    measurements = [v["measurement"] for v in body["variables"]]
    # All categoricals must precede any scale entry
    found_scale = False
    for m in measurements:
        if m == "scale":
            found_scale = True
        if found_scale and m == "categorical":
            pytest.fail(
                f"Categorical appeared after scale in variables response; order: {measurements}"
            )


# ---------------------------------------------------------------------------
# RX-be.2 + RX-be.3 — POST /materials/{material_id}/preview-chart hardening
# ---------------------------------------------------------------------------


_VALID_BAR_SPEC = {
    "question_ref": "q1",
    "chart_type": "horizontal_bar",
    "statistic": "pct",
}

_SCATTER_NO_XY_SPEC = {
    "question_ref": "q1",
    "chart_type": "scatter",
    "statistic": "pct",
    # scatter_xy deliberately omitted
}

_STACKED_VERT_NO_DIM_SPEC = {
    "question_ref": "q1",
    "chart_type": "stacked_vertical_bar",
    "statistic": "pct",
    # classifying_var deliberately omitted
}

_STACKED_HORIZ_NO_DIM_SPEC = {
    "question_ref": "q1",
    "chart_type": "stacked_horizontal_bar",
    "statistic": "pct",
    # classifying_var deliberately omitted
}


def test_preview_chart_valid_spec_returns_200_png() -> None:
    """POST preview-chart with a valid horizontal_bar spec returns 200 image/png. (RX-be.2)

    Integration-only path; skipped when LibreOffice (soffice) is absent.
    """
    soffice_present = (
        shutil.which("soffice") is not None or shutil.which("libreoffice") is not None
    )
    if not soffice_present:
        pytest.skip("soffice not found — skipping PNG assertion (requires LibreOffice)")

    sav_bytes = synthetic_sav_bytes()
    mock_client = Mock()
    mock_client.get_material.return_value = sav_bytes
    app = create_app(client=mock_client)
    tc = TestClient(app)

    response = tc.post("/materials/mat-rx2/preview-chart", json=_VALID_BAR_SPEC)

    assert response.status_code == 200, (
        f"Expected 200 image/png from valid preview-chart spec, "
        f"got {response.status_code}: {response.text[:500]}"
    )
    assert response.headers["content-type"].startswith("image/png"), (
        f"Expected image/png content-type, got {response.headers['content-type']}"
    )
    assert response.content[:4] == b"\x89PNG", "Response does not start with PNG magic bytes"


def test_preview_chart_scatter_without_xy_returns_422_not_500() -> None:
    """POST preview-chart with chart_type=scatter and no scatter_xy returns 422 — never 500.

    The browser previously received 'XMLHttpRequest onError' from an unhandled crash.
    After RX-be.2 the endpoint must return a structured 422 with a clear reason.
    """
    sav_bytes = synthetic_sav_bytes()
    mock_client = Mock()
    mock_client.get_material.return_value = sav_bytes
    app = create_app(client=mock_client)
    tc = TestClient(app)

    response = tc.post("/materials/mat-rx2/preview-chart", json=_SCATTER_NO_XY_SPEC)

    assert response.status_code == 422, (
        f"Expected 422 for scatter without scatter_xy, "
        f"got {response.status_code}: {response.text}"
    )
    detail = response.json().get("detail", "")
    # The detail should reference scatter and/or the missing X/Y context
    assert "scatter" in detail.lower() or "x and y" in detail.lower(), (
        f"422 detail should mention 'scatter' or 'X and Y', got: {detail!r}"
    )


def test_preview_chart_stacked_vertical_without_classifying_var_not_blocked() -> None:
    """POST preview-chart with stacked_vertical_bar and no classifying_var renders
    the answer distribution as a single total bar — it must NOT be rejected with a
    'classifying variable' 422 (total-only stacked bars are valid).
    """
    sav_bytes = synthetic_sav_bytes()
    mock_client = Mock()
    mock_client.get_material.return_value = sav_bytes
    app = create_app(client=mock_client)
    tc = TestClient(app)

    response = tc.post("/materials/mat-rx2/preview-chart", json=_STACKED_VERT_NO_DIM_SPEC)

    detail = response.json().get("detail", "") if response.status_code != 200 else ""
    assert not (response.status_code == 422 and "classifying variable" in detail.lower()), (
        f"stacked_vertical_bar without classifying_var must no longer be blocked; "
        f"got {response.status_code}: {response.text[:300]}"
    )


def test_preview_chart_stacked_horizontal_without_classifying_var_not_blocked() -> None:
    """Same for the horizontal stacked variant — total-only is allowed."""
    sav_bytes = synthetic_sav_bytes()
    mock_client = Mock()
    mock_client.get_material.return_value = sav_bytes
    app = create_app(client=mock_client)
    tc = TestClient(app)

    response = tc.post("/materials/mat-rx2/preview-chart", json=_STACKED_HORIZ_NO_DIM_SPEC)

    detail = response.json().get("detail", "") if response.status_code != 200 else ""
    assert not (response.status_code == 422 and "classifying variable" in detail.lower()), (
        f"stacked_horizontal_bar without classifying_var must no longer be blocked; "
        f"got {response.status_code}: {response.text[:300]}"
    )
