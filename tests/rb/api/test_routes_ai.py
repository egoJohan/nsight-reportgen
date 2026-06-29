"""Tests for the AI text routes (C.4): /ai/slide-title and /ai/short-labels.

All offline: egoHive is replaced by a fake via monkeypatching
``reportbuilder.api.routes_ai.egohive_chat`` (looked up at call time), and the
reference corpus is patched to a tiny in-memory one.
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.ai.reference import ReferenceLabels
from reportbuilder.testing.fixtures import synthetic_sav_bytes
from nsight.agent.egohive_client import EgoHiveError


def _client_with_material() -> TestClient:
    mock_client = Mock()
    mock_client.get_material.return_value = synthetic_sav_bytes()
    app = create_app(client=mock_client)
    return TestClient(app)


# --------------------------------------------------------------------------- #
# /ai/slide-title
# --------------------------------------------------------------------------- #
def test_slide_title_returns_title(monkeypatch) -> None:
    monkeypatch.setattr(
        "reportbuilder.api.routes_ai.egohive_chat",
        lambda prompt, **kw: "Tyytyväisyys on korkealla tasolla",
    )
    client = _client_with_material()
    resp = client.post("/materials/mat-1/ai/slide-title", json={"question_ref": "q1"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"title": "Tyytyväisyys on korkealla tasolla"}


def test_slide_title_egohive_error_returns_503(monkeypatch) -> None:
    def boom(prompt, **kw):
        raise EgoHiveError("egohive down")

    monkeypatch.setattr("reportbuilder.api.routes_ai.egohive_chat", boom)
    client = _client_with_material()
    resp = client.post("/materials/mat-1/ai/slide-title", json={"question_ref": "q1"})
    assert resp.status_code == 503, resp.text
    assert "egoHive" in resp.json()["detail"]


def test_slide_title_empty_findings_falls_back(monkeypatch) -> None:
    """No computable findings → return the question text, never call the LLM
    (which would otherwise reply with a meta-question)."""
    def boom(*a, **k):
        raise AssertionError("egohive_chat must not be called when findings are empty")

    monkeypatch.setattr("reportbuilder.api.routes_ai.egohive_chat", boom)
    monkeypatch.setattr(
        "reportbuilder.api.routes_ai._findings_from_series", lambda series, n: []
    )
    client = _client_with_material()
    resp = client.post("/materials/mat-1/ai/slide-title", json={"question_ref": "q1"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"]  # the question text (non-empty), not LLM gibberish


def test_slide_title_unknown_question_returns_404(monkeypatch) -> None:
    monkeypatch.setattr(
        "reportbuilder.api.routes_ai.egohive_chat", lambda prompt, **kw: "x"
    )
    client = _client_with_material()
    resp = client.post("/materials/mat-1/ai/slide-title", json={"question_ref": "nope"})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# /ai/short-labels
# --------------------------------------------------------------------------- #
def test_short_labels_returns_overrides(monkeypatch) -> None:
    monkeypatch.setattr(
        "reportbuilder.api.routes_ai._reference_labels",
        lambda: ReferenceLabels(labels=[], titles=[]),
    )
    monkeypatch.setattr(
        "reportbuilder.api.routes_ai.egohive_chat",
        lambda prompt, **kw: "1. Tyytyväiset\n2. Tyytymättömät",
    )
    client = _client_with_material()
    resp = client.post(
        "/materials/mat-1/ai/short-labels",
        json={
            "categories": [
                "Erittäin tai melko tyytyväiset",
                "Erittäin tai melko tyytymättömät",
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "overrides": [
            ["Erittäin tai melko tyytyväiset", "Tyytyväiset"],
            ["Erittäin tai melko tyytymättömät", "Tyytymättömät"],
        ]
    }


def test_short_labels_from_question_ref(monkeypatch) -> None:
    monkeypatch.setattr(
        "reportbuilder.api.routes_ai._reference_labels",
        lambda: ReferenceLabels(labels=[], titles=[]),
    )
    monkeypatch.setattr(
        "reportbuilder.api.routes_ai.egohive_chat",
        lambda prompt, **kw: "1. Kyllä\n2. Ei",
    )
    client = _client_with_material()
    resp = client.post("/materials/mat-1/ai/short-labels", json={"question_ref": "q1"})
    assert resp.status_code == 200, resp.text
    assert "overrides" in resp.json()


def test_short_labels_ai_unreachable_degrades_to_200(monkeypatch) -> None:
    """shorten_labels swallows EgoHiveError -> originals; endpoint stays 200 (C.2)."""
    monkeypatch.setattr(
        "reportbuilder.api.routes_ai._reference_labels",
        lambda: ReferenceLabels(labels=[], titles=[]),
    )

    def boom(prompt, **kw):
        raise EgoHiveError("down")

    monkeypatch.setattr("reportbuilder.api.routes_ai.egohive_chat", boom)
    client = _client_with_material()
    resp = client.post(
        "/materials/mat-1/ai/short-labels", json={"categories": ["Jokin otsikko"]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"overrides": []}  # fell back to originals


def test_short_labels_reference_extract_error_returns_503(monkeypatch) -> None:
    def boom():
        raise RuntimeError("pptx corpus blew up")

    monkeypatch.setattr("reportbuilder.api.routes_ai._reference_labels", boom)
    client = _client_with_material()
    resp = client.post(
        "/materials/mat-1/ai/short-labels", json={"categories": ["A long label here"]}
    )
    assert resp.status_code == 503


def test_short_labels_requires_categories_or_question_ref() -> None:
    client = _client_with_material()
    resp = client.post("/materials/mat-1/ai/short-labels", json={})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Optional live egoHive smoke test (skipped unless reachable)
# --------------------------------------------------------------------------- #
@pytest.mark.live
def test_live_egohive_slide_title_smoke() -> None:
    from reportbuilder.ai.text import generate_slide_title
    from nsight.agent.egohive_client import EgoHiveError, egohive_chat

    try:
        title = generate_slide_title(
            "Kuinka tyytyväinen olet palveluun?",
            [("Erittäin tyytyväinen", 62.0), ("Melko tyytyväinen", 28.0)],
            chat=egohive_chat,
        )
    except EgoHiveError as exc:
        pytest.skip(f"egoHive unreachable: {exc}")
    assert isinstance(title, str) and title.strip()
