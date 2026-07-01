"""Health endpoint + DataHiveError -> HTTP mapping, exercised through multiple routes.

Deterministic: no soffice, no network. The mapping table (REQ-C-30) is asserted
via both POST /cases and GET /cases so we know the single exception handler is
route-independent.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.store.datahive_client import DataHiveError


# --- health -----------------------------------------------------------------

def test_health_ok(client_mock):
    resp = client_mock.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_without_client():
    """An app built with no injected client still serves /health (no upstream needed)."""
    resp = TestClient(create_app()).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --- DataHiveError shape -----------------------------------------------------

def test_datahive_error_is_runtimeerror_and_carries_fields():
    err = DataHiveError(404, "nope", "GET", "http://dh/x")
    assert isinstance(err, RuntimeError)
    assert err.status_code == 404
    assert err.body == "nope"
    assert err.method == "GET"
    assert err.url == "http://dh/x"


# --- mapping table -----------------------------------------------------------

# (upstream status, expected HTTP status)
_PASS_THROUGH = [400, 401, 403, 404, 409, 422]
_COLLAPSE_TO_502 = [500, 503, 418, 599, 302]

_TABLE = [(s, s) for s in _PASS_THROUGH] + [(s, 502) for s in _COLLAPSE_TO_502]


@pytest.mark.parametrize("upstream,expected", _TABLE)
def test_error_mapping_via_post_cases(client_mock, mock_hive, upstream, expected):
    mock_hive.create_case.side_effect = DataHiveError(upstream, "boom", "POST", "http://dh/cases")
    resp = client_mock.post("/cases", json={"name": "X"})
    assert resp.status_code == expected
    detail = resp.json()["detail"]
    assert detail.startswith("datahive: ")
    assert len(detail) <= 500


@pytest.mark.parametrize("upstream,expected", _TABLE)
def test_error_mapping_via_get_cases(client_mock, mock_hive, upstream, expected):
    mock_hive.list_cases.side_effect = DataHiveError(upstream, "boom", "GET", "http://dh/cases")
    resp = client_mock.get("/cases")
    assert resp.status_code == expected
    detail = resp.json()["detail"]
    assert detail.startswith("datahive: ")
    assert len(detail) <= 500


def test_error_detail_truncated_to_500_chars(client_mock, mock_hive):
    mock_hive.list_cases.side_effect = DataHiveError(500, "z" * 1000, "GET", "http://dh/cases")
    resp = client_mock.get("/cases")
    assert resp.status_code == 502
    assert len(resp.json()["detail"]) == 500
