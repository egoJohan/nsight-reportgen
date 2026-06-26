"""REQ-C-30 — DataHiveError HTTP mapping tests.

When the DataHiveClient raises DataHiveError, the FastAPI exception handler
must translate it into a meaningful HTTP response for the Flutter UI:
  - 4xx from datahive → same status (401, 403, 404, 409, 422, 400)
  - 5xx / other from datahive → 502 (bad upstream)
The response body always contains a JSON ``detail`` field starting with
"datahive: ".
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.store.datahive_client import DataHiveClient, DataHiveError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_client(exc: Exception) -> MagicMock:
    """Return a DataHiveClient mock whose load_report always raises ``exc``."""
    mock = MagicMock(spec=DataHiveClient)
    mock.load_report.side_effect = exc
    return mock


def _client_for(exc: Exception) -> TestClient:
    mock = _make_mock_client(exc)
    app = create_app(client=mock)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# REQ-C-30: 4xx datahive → 4xx nSight
# ---------------------------------------------------------------------------

def test_datahive_404_maps_to_404():
    """REQ-C-30: DataHiveError(404, ...) → route returns HTTP 404 with datahive detail."""
    err = DataHiveError(404, '{"error":"not_found"}', "GET", "http://h/x")
    tc = _client_for(err)

    resp = tc.get("/cases/c1/reports/r1")

    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    detail = resp.json().get("detail", "")
    assert "datahive" in detail, f"Expected 'datahive' in detail, got {detail!r}"


def test_datahive_401_maps_to_401():
    """REQ-C-30: DataHiveError(401, ...) → route returns HTTP 401."""
    err = DataHiveError(401, "Unauthorized", "GET", "http://h/x")
    tc = _client_for(err)

    resp = tc.get("/cases/c1/reports/r1")

    assert resp.status_code == 401


def test_datahive_403_maps_to_403():
    """REQ-C-30: DataHiveError(403, ...) → route returns HTTP 403."""
    err = DataHiveError(403, "Forbidden", "GET", "http://h/x")
    tc = _client_for(err)

    resp = tc.get("/cases/c1/reports/r1")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# REQ-C-30: 5xx datahive → 502 nSight
# ---------------------------------------------------------------------------

def test_datahive_500_maps_to_502():
    """REQ-C-30: DataHiveError(500, ...) → route returns HTTP 502 (bad upstream)."""
    err = DataHiveError(500, "Internal Server Error", "GET", "http://h/x")
    tc = _client_for(err)

    resp = tc.get("/cases/c1/reports/r1")

    assert resp.status_code == 502, f"Expected 502, got {resp.status_code}"
    detail = resp.json().get("detail", "")
    assert "datahive" in detail, f"Expected 'datahive' in detail, got {detail!r}"


def test_datahive_503_maps_to_502():
    """REQ-C-30: DataHiveError(503, ...) → route returns HTTP 502."""
    err = DataHiveError(503, "Service Unavailable", "GET", "http://h/x")
    tc = _client_for(err)

    resp = tc.get("/cases/c1/reports/r1")

    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# REQ-C-30: detail body contains datahive body text (truncated at 500 chars)
# ---------------------------------------------------------------------------

def test_detail_contains_datahive_body():
    """REQ-C-30: The response detail includes the datahive error body."""
    err = DataHiveError(404, '{"error":"not_found"}', "GET", "http://h/x")
    tc = _client_for(err)

    resp = tc.get("/cases/c1/reports/r1")

    detail = resp.json()["detail"]
    assert '{"error":"not_found"}' in detail


def test_long_body_truncated_to_500_chars():
    """REQ-C-30: detail is capped so very long datahive bodies don't leak excessive data."""
    long_body = "x" * 1000
    err = DataHiveError(500, long_body, "GET", "http://h/x")
    tc = _client_for(err)

    resp = tc.get("/cases/c1/reports/r1")

    detail = resp.json()["detail"]
    assert len(detail) <= 500


# ---------------------------------------------------------------------------
# REQ-C-30: DataHiveError IS-A RuntimeError (backward compat)
# ---------------------------------------------------------------------------

def test_datahive_error_is_runtime_error():
    """DataHiveError must be a subclass of RuntimeError for backward-compat with existing tests."""
    err = DataHiveError(404, "not found", "GET", "http://h/x")
    assert isinstance(err, RuntimeError)


def test_datahive_error_attributes():
    """DataHiveError exposes status_code, body, method, url attributes."""
    err = DataHiveError(422, "bad body", "POST", "http://h/docs")
    assert err.status_code == 422
    assert err.body == "bad body"
    assert err.method == "POST"
    assert err.url == "http://h/docs"
