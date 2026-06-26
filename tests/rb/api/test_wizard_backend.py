"""Wizard backend tests — W1: suggested_chart_type, preview-chart, missing_values.

Tests for:
- GET /materials/{material_id}/questions returning suggested_chart_type + missing_values (W1.1, W1.3)
- POST /materials/{material_id}/preview-chart returning image/png (W1.2)
- POST /materials/{material_id}/preview-chart with bad spec returning 422 (W1.2)

(REQ-C-05, REQ-C-13, REQ-C-19, REQ-D-06)
"""
from __future__ import annotations

import shutil
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.render.plugins import CHART_PLUGINS
from reportbuilder.testing.fixtures import synthetic_sav_bytes


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_model_with_missing() -> QuestionModel:
    """QuestionModel with one question whose primary variable has a missing value."""
    variables = {
        "q1": Variable(
            name="q1",
            label="Satisfaction",
            measurement="categorical",
            value_labels=(
                ValueLabel(1.0, "Very good"),
                ValueLabel(2.0, "Good"),
                ValueLabel(3.0, "Poor"),
                ValueLabel(4.0, "Very poor"),
                ValueLabel(99.0, "Don't know"),
            ),
            missing_values=frozenset({99.0}),
        ),
    }
    questions = [
        Question(qid="q1", kind="single", variables=("q1",), text="Satisfaction"),
    ]
    return QuestionModel(variables=variables, questions=questions)


def _make_simple_model() -> QuestionModel:
    """QuestionModel with one question, no missing values."""
    variables = {
        "q1": Variable(
            name="q1",
            label="Satisfaction",
            measurement="categorical",
            value_labels=(
                ValueLabel(1.0, "Yes"),
                ValueLabel(2.0, "No"),
            ),
            missing_values=frozenset(),
        ),
    }
    questions = [
        Question(qid="q1", kind="single", variables=("q1",), text="Satisfaction"),
    ]
    return QuestionModel(variables=variables, questions=questions)


# ---------------------------------------------------------------------------
# W1.1 + W1.3 — GET /materials/{material_id}/questions
# ---------------------------------------------------------------------------


def test_get_questions_returns_suggested_chart_type() -> None:
    """GET questions returns suggested_chart_type (a known plugin id) per question. (REQ-C-05, REQ-C-13)"""
    model = _make_simple_model()
    mock_client = Mock()
    app = create_app(client=mock_client)
    client = TestClient(app)

    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = model
        response = client.get("/materials/mat-w1/questions")

    assert response.status_code == 200
    body = response.json()
    questions = body["questions"]
    assert len(questions) >= 1
    for q in questions:
        assert "suggested_chart_type" in q, "missing suggested_chart_type field"
        assert isinstance(q["suggested_chart_type"], str)
        # Must be a registered chart type
        assert q["suggested_chart_type"] in CHART_PLUGINS, (
            f"suggested_chart_type {q['suggested_chart_type']!r} is not a registered plugin"
        )


def test_get_questions_returns_missing_values_list() -> None:
    """GET questions returns missing_values as a list of {code, label} per question. (REQ-C-05, REQ-D-06)"""
    model = _make_model_with_missing()
    mock_client = Mock()
    app = create_app(client=mock_client)
    client = TestClient(app)

    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = model
        response = client.get("/materials/mat-w1/questions")

    assert response.status_code == 200
    body = response.json()
    questions = body["questions"]
    assert len(questions) == 1
    q = questions[0]

    assert "missing_values" in q, "missing missing_values field"
    mv = q["missing_values"]
    assert isinstance(mv, list)
    # q1 has exactly one missing value: code 99.0 → "Don't know"
    assert len(mv) == 1
    assert mv[0]["code"] == 99.0
    assert mv[0]["label"] == "Don't know"


def test_get_questions_missing_values_empty_when_none() -> None:
    """GET questions returns empty missing_values list when variable has no missing codes. (REQ-D-06)"""
    model = _make_simple_model()
    mock_client = Mock()
    app = create_app(client=mock_client)
    client = TestClient(app)

    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = model
        response = client.get("/materials/mat-w1/questions")

    assert response.status_code == 200
    body = response.json()
    for q in body["questions"]:
        assert q["missing_values"] == [], (
            f"expected empty missing_values for q with no missing codes, got {q['missing_values']}"
        )


def test_get_questions_all_required_fields_present() -> None:
    """GET questions response has all five required fields per question. (REQ-C-05, REQ-C-13, REQ-D-06)"""
    model = _make_simple_model()
    mock_client = Mock()
    app = create_app(client=mock_client)
    client = TestClient(app)

    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = model
        response = client.get("/materials/mat-w1/questions")

    assert response.status_code == 200
    for q in response.json()["questions"]:
        for field in ("qid", "kind", "variables", "text", "suggested_chart_type", "missing_values"):
            assert field in q, f"field {field!r} missing from question response"


# ---------------------------------------------------------------------------
# W1.2 — POST /materials/{material_id}/preview-chart  (PNG preview)
# ---------------------------------------------------------------------------


_VALID_SPEC = {
    "question_ref": "q1",
    "chart_type": "horizontal_bar",
    "statistic": "pct",
}


def test_preview_chart_returns_png() -> None:
    """POST preview-chart with a valid spec returns 200 image/png with non-empty content.

    Requires LibreOffice (soffice) which IS present on this machine.
    (REQ-C-05, REQ-C-13, REQ-C-19)
    """
    soffice_present = shutil.which("soffice") is not None or shutil.which("libreoffice") is not None
    if not soffice_present:
        pytest.skip("soffice not found — skipping PNG assertion (integration-only path)")

    sav_bytes = synthetic_sav_bytes()
    mock_client = Mock()
    mock_client.get_material.return_value = sav_bytes

    app = create_app(client=mock_client)
    client = TestClient(app)

    response = client.post("/materials/mat-w1/preview-chart", json=_VALID_SPEC)

    assert response.status_code == 200, (
        f"Expected 200 from preview-chart, got {response.status_code}: {response.text[:500]}"
    )
    assert response.headers["content-type"].startswith("image/png"), (
        f"Expected image/png content-type, got {response.headers['content-type']}"
    )
    assert len(response.content) > 100, "PNG response content is too small to be a real image"
    # Verify PNG magic bytes
    assert response.content[:4] == b"\x89PNG", "Response content does not start with PNG magic bytes"


def test_preview_chart_value_error_returns_422() -> None:
    """POST preview-chart whose build_pptx raises ValueError returns 422, not 500. (REQ-C-13, REQ-C-19)"""
    sav_bytes = synthetic_sav_bytes()
    mock_client = Mock()
    mock_client.get_material.return_value = sav_bytes

    app = create_app(client=mock_client)
    client = TestClient(app)

    with patch("reportbuilder.api.routes_questions.build_pptx") as mock_build:
        mock_build.side_effect = ValueError("chart configuration error: scatter requires scatter_xy")

        response = client.post("/materials/mat-w1/preview-chart", json=_VALID_SPEC)

    assert response.status_code == 422, (
        f"Expected 422 for chart ValueError, got {response.status_code}"
    )
    assert "scatter_xy" in response.json().get("detail", "") or "chart configuration error" in response.json().get("detail", ""), (
        "422 detail should contain the original ValueError message"
    )


def test_preview_chart_503_when_soffice_absent() -> None:
    """POST preview-chart returns 503 when LibreOffice is not available. (REQ-C-19)"""
    sav_bytes = synthetic_sav_bytes()
    mock_client = Mock()
    mock_client.get_material.return_value = sav_bytes

    app = create_app(client=mock_client)
    client = TestClient(app)

    with patch("reportbuilder.api.routes_questions.shutil.which", return_value=None):
        response = client.post("/materials/mat-w1/preview-chart", json=_VALID_SPEC)

    assert response.status_code == 503, (
        f"Expected 503 when soffice absent, got {response.status_code}"
    )
    assert "soffice" in response.json().get("detail", "").lower() or "libreoffice" in response.json().get("detail", "").lower()
