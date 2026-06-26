"""Unit tests for the real DataHiveClient REST methods — uses httpx.MockTransport.
No real network calls are made.

REQ-C-03/07/08/12
"""
from __future__ import annotations

import json

import httpx
import pytest

from reportbuilder.store.datahive_client import DataHiveClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE = "http://hive.test"
_TOKEN = "tok-abc"
_CASE = "proj-111"
_ITEM = "item-999"
_REF = "report-7"
_REPORT_JSON = '{"a": 1}'
_READABLE = "My Report"


def _make_client(handler) -> DataHiveClient:
    """Build a DataHiveClient that routes all requests through the mock handler."""
    return DataHiveClient(
        base_url=_BASE,
        token=_TOKEN,
        transport=httpx.MockTransport(handler),
    )


def _json_resp(data: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data)


def _check_auth(request: httpx.Request) -> None:
    assert request.headers.get("Authorization") == f"Bearer {_TOKEN}", (
        f"Missing/wrong Bearer header: {request.headers.get('Authorization')!r}"
    )


# ---------------------------------------------------------------------------
# 1. create_case  (REQ-C-03/07)
# ---------------------------------------------------------------------------

def test_create_case_posts_to_projects_and_returns_id():
    """create_case POSTs to /api/v1/projects with name + template_ref and the Bearer header;
    returns the project id from the response.  REQ-C-03/07.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        _check_auth(request)
        assert request.method == "POST"
        assert str(request.url).endswith("/api/v1/projects")
        body = json.loads(request.content)
        assert body["name"] == "Test Case"
        assert "template_ref" in body
        return _json_resp({"id": "proj-001", "name": "Test Case"})

    client = _make_client(handler)
    result = client.create_case("Test Case")
    assert result == "proj-001"


def test_create_case_accepts_project_id_field():
    """create_case returns the id from 'project_id' when 'id' is absent.  REQ-C-03."""
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_resp({"project_id": "proj-alt", "name": "X"})

    client = _make_client(handler)
    assert client.create_case("X") == "proj-alt"


def test_create_case_raises_on_non_2xx():
    """create_case raises RuntimeError with status + body snippet on non-2xx.  REQ-C-03."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    client = _make_client(handler)
    with pytest.raises(RuntimeError, match="400"):
        client.create_case("Bad")


# ---------------------------------------------------------------------------
# 2. list_cases  (REQ-C-07)
# ---------------------------------------------------------------------------

def test_list_cases_gets_projects_and_returns_list():
    """list_cases GETs /api/v1/projects and returns the projects list.  REQ-C-07."""
    projects = [{"id": "p1", "name": "Alpha"}, {"id": "p2", "name": "Beta"}]

    def handler(request: httpx.Request) -> httpx.Response:
        _check_auth(request)
        assert request.method == "GET"
        assert str(request.url).endswith("/api/v1/projects")
        return _json_resp({"count": 2, "projects": projects})

    client = _make_client(handler)
    result = client.list_cases()
    assert result == projects


# ---------------------------------------------------------------------------
# 3. save_report with None report_id — generates a reference_id  (REQ-C-08)
# ---------------------------------------------------------------------------

def test_save_report_generates_reference_id_when_none():
    """save_report(case, None, json, readable) POSTs to the docs endpoint with a generated
    reference_id; returns that reference_id; label must be 'report'.  REQ-C-08.
    """
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        _check_auth(request)
        assert request.method == "POST"
        assert f"/api/v1/projects/{_CASE}/docs" in str(request.url)
        body = json.loads(request.content)
        captured.append(body)
        return _json_resp({"reference_id": body["reference_id"]})

    client = _make_client(handler)
    result = client.save_report(_CASE, None, _REPORT_JSON, _READABLE)

    assert len(captured) == 1
    body = captured[0]
    assert body["text"] == _REPORT_JSON
    assert body["label"] == "report"
    assert body["reference_id"].startswith("report-")
    assert result == body["reference_id"]


# ---------------------------------------------------------------------------
# 4. save_report with explicit report_id — versioned replace  (REQ-C-08)
# ---------------------------------------------------------------------------

def test_save_report_uses_explicit_reference_id():
    """save_report(case, 'report-7', ...) sends reference_id == 'report-7'.  REQ-C-08."""
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["reference_id"] == _REF
        return _json_resp({"reference_id": _REF})

    client = _make_client(handler)
    result = client.save_report(_CASE, _REF, _REPORT_JSON, _READABLE)
    assert result == _REF


# ---------------------------------------------------------------------------
# 5. load_report_in_case — byte-exact round-trip  (REQ-C-08)
# ---------------------------------------------------------------------------

def test_load_report_in_case_returns_text_verbatim():
    """load_report_in_case GETs the docs endpoint and returns the 'text' field verbatim.
    Byte-exact round-trip: the text returned must equal what was originally stored.
    REQ-C-08.
    """
    stored_text = _REPORT_JSON  # same string as save_report would store

    def handler(request: httpx.Request) -> httpx.Response:
        _check_auth(request)
        assert request.method == "GET"
        assert f"/api/v1/projects/{_CASE}/docs/{_REF}" in str(request.url)
        return _json_resp({
            "label": "report",
            "name": _READABLE,
            "reference_id": _REF,
            "text": stored_text,
        })

    client = _make_client(handler)
    result = client.load_report_in_case(_CASE, _REF)
    assert result == stored_text  # byte-exact


def test_load_report_raises_clear_error():
    """load_report (no case_id) raises RuntimeError directing callers to use the case-scoped variant."""
    client = _make_client(lambda r: httpx.Response(200))
    with pytest.raises(RuntimeError, match="load_report_in_case"):
        client.load_report(_REF)


# ---------------------------------------------------------------------------
# 6. delete_report_in_case  (REQ-C-12)
# ---------------------------------------------------------------------------

def test_delete_report_in_case_issues_delete():
    """delete_report_in_case issues DELETE to the right path.  REQ-C-12."""
    called: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        _check_auth(request)
        assert request.method == "DELETE"
        assert f"/api/v1/projects/{_CASE}/docs/{_REF}" in str(request.url)
        called.append("yes")
        return httpx.Response(204)

    client = _make_client(handler)
    client.delete_report_in_case(_CASE, _REF)
    assert called == ["yes"]


def test_delete_report_raises_clear_error():
    """delete_report (no case_id) raises RuntimeError directing callers to use the case-scoped variant."""
    client = _make_client(lambda r: httpx.Response(200))
    with pytest.raises(RuntimeError, match="delete_report_in_case"):
        client.delete_report(_REF)


# ---------------------------------------------------------------------------
# 7. aggregate  (D1 / REQ-C-03)
# ---------------------------------------------------------------------------

def test_aggregate_posts_group_columns_and_filters():
    """aggregate POSTs {group_columns, filters} to /api/v1/aggregation/{item_id} and
    returns the response dict.  REQ-C-03.
    """
    group_by = ["q1", "seg"]
    filters = [{"col": "x"}]
    agg_result = {"dimensions": ["q1", "seg"], "cells": [], "total": 100}

    def handler(request: httpx.Request) -> httpx.Response:
        _check_auth(request)
        assert request.method == "POST"
        assert f"/api/v1/aggregation/{_ITEM}" in str(request.url)
        body = json.loads(request.content)
        assert body["group_columns"] == group_by
        assert body["filters"] == filters
        return _json_resp(agg_result)

    client = _make_client(handler)
    result = client.aggregate(_ITEM, group_by, filters)
    assert result == agg_result


def test_aggregate_defaults_filters_to_empty_list():
    """aggregate with filters=None sends [] to the API."""
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["filters"] == []
        return _json_resp({"dimensions": [], "cells": [], "total": 0})

    client = _make_client(handler)
    result = client.aggregate(_ITEM, ["q1"])
    assert "total" in result


# ---------------------------------------------------------------------------
# 8. non-2xx raises a clear error  (general)
# ---------------------------------------------------------------------------

def test_non_2xx_raises_with_status_and_body():
    """Any non-2xx response raises RuntimeError containing the status code and body snippet."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client = _make_client(handler)
    with pytest.raises(RuntimeError, match="500"):
        client.list_cases()


# ---------------------------------------------------------------------------
# 9. Context-manager closes client
# ---------------------------------------------------------------------------

def test_context_manager_closes_client():
    """Using DataHiveClient as a context manager should not raise."""
    with DataHiveClient(
        base_url=_BASE,
        token=_TOKEN,
        transport=httpx.MockTransport(lambda r: _json_resp({"count": 0, "projects": []})),
    ) as client:
        result = client.list_cases()
    assert result == []
