"""Integration tests for the real DataHiveClient REST behavior.

Deterministic, NO real network: every request is routed through an
``httpx.MockTransport`` handler that fakes DataHive responses. Covers all 8
methods (correct HTTP method + path, request body/multipart, response parsing),
the Bearer auth header, a byte-exact attach->get round-trip through a stateful
mock, DataHiveError semantics on non-2xx, and clean context-manager close.
"""
from __future__ import annotations

import json
import re

import httpx
import pytest

from reportbuilder.store.datahive_client import DataHiveClient, DataHiveError


_BASE = "http://hive.test"
_TOKEN = "tok-abc"
_CASE = "proj-111"
_ITEM = "item-999"
_REF = "report-7"
_REPORT_JSON = '{"a": 1, "chart": "bar"}'
_READABLE = "My Report"


def _make_client(handler) -> DataHiveClient:
    return DataHiveClient(
        base_url=_BASE,
        token=_TOKEN,
        transport=httpx.MockTransport(handler),
    )


def _json_resp(data: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data)


def _check_auth(request: httpx.Request) -> None:
    assert request.headers.get("Authorization") == f"Bearer {_TOKEN}"


# ---------------------------------------------------------------------------
# create_case
# ---------------------------------------------------------------------------

def test_create_case_posts_projects_with_name_and_template():
    def handler(request):
        _check_auth(request)
        assert request.method == "POST"
        assert str(request.url).endswith("/api/v1/projects")
        body = json.loads(request.content)
        assert body["name"] == "Test Case"
        assert body["template_ref"]  # default template forwarded
        return _json_resp({"id": "proj-001", "name": "Test Case"})

    assert _make_client(handler).create_case("Test Case") == "proj-001"


def test_create_case_reads_id_field():
    handler = lambda r: _json_resp({"id": "the-id", "project_id": "ignored"})
    assert _make_client(handler).create_case("X") == "the-id"


def test_create_case_falls_back_to_project_id():
    handler = lambda r: _json_resp({"project_id": "proj-alt", "name": "X"})
    assert _make_client(handler).create_case("X") == "proj-alt"


def test_create_case_custom_template_ref_forwarded():
    def handler(request):
        assert json.loads(request.content)["template_ref"] == "wftemplate:custom"
        return _json_resp({"id": "p1"})

    c = DataHiveClient(
        base_url=_BASE, token=_TOKEN, template_ref="wftemplate:custom",
        transport=httpx.MockTransport(handler),
    )
    assert c.create_case("X") == "p1"


# ---------------------------------------------------------------------------
# list_cases
# ---------------------------------------------------------------------------

def test_list_cases_gets_projects_and_unwraps():
    projects = [{"id": "p1", "name": "Alpha"}, {"id": "p2", "name": "Beta"}]

    def handler(request):
        _check_auth(request)
        assert request.method == "GET"
        assert str(request.url).endswith("/api/v1/projects")
        return _json_resp({"count": 2, "projects": projects})

    assert _make_client(handler).list_cases() == projects


# ---------------------------------------------------------------------------
# save_report
# ---------------------------------------------------------------------------

def test_save_report_generates_reference_id_when_none():
    captured = []

    def handler(request):
        _check_auth(request)
        assert request.method == "POST"
        assert f"/api/v1/projects/{_CASE}/docs" in str(request.url)
        body = json.loads(request.content)
        captured.append(body)
        return _json_resp({"reference_id": body["reference_id"]})

    result = _make_client(handler).save_report(_CASE, None, _REPORT_JSON, _READABLE)
    body = captured[0]
    assert body["text"] == _REPORT_JSON
    assert body["label"] == "report"
    assert body["name"] == _READABLE
    assert body["reference_id"].startswith("report-")
    assert result == body["reference_id"]


def test_save_report_uses_explicit_reference_id():
    def handler(request):
        assert json.loads(request.content)["reference_id"] == _REF
        return _json_resp({"reference_id": _REF})

    assert _make_client(handler).save_report(_CASE, _REF, _REPORT_JSON, _READABLE) == _REF


def test_save_report_returns_server_reference_id():
    """The returned id is whatever the server echoes in reference_id."""
    def handler(request):
        return _json_resp({"reference_id": "server-assigned"})

    assert _make_client(handler).save_report(_CASE, _REF, _REPORT_JSON, _READABLE) == "server-assigned"


def test_save_report_defaults_name_when_readable_empty():
    def handler(request):
        assert json.loads(request.content)["name"] == "report"
        return _json_resp({"reference_id": "x"})

    _make_client(handler).save_report(_CASE, None, _REPORT_JSON, "")


def test_save_report_truncates_long_readable_name():
    long_name = "R" * 500

    def handler(request):
        name = json.loads(request.content)["name"]
        assert len(name) == 120
        return _json_resp({"reference_id": "x"})

    _make_client(handler).save_report(_CASE, None, _REPORT_JSON, long_name)


# ---------------------------------------------------------------------------
# load_report
# ---------------------------------------------------------------------------

def test_load_report_returns_text_verbatim():
    def handler(request):
        _check_auth(request)
        assert request.method == "GET"
        assert f"/api/v1/projects/{_CASE}/docs/{_REF}" in str(request.url)
        return _json_resp({"reference_id": _REF, "text": _REPORT_JSON})

    assert _make_client(handler).load_report(_CASE, _REF) == _REPORT_JSON


# ---------------------------------------------------------------------------
# delete_report
# ---------------------------------------------------------------------------

def test_delete_report_issues_delete():
    called = []

    def handler(request):
        _check_auth(request)
        assert request.method == "DELETE"
        assert f"/api/v1/projects/{_CASE}/docs/{_REF}" in str(request.url)
        called.append(True)
        return httpx.Response(204)

    _make_client(handler).delete_report(_CASE, _REF)
    assert called == [True]


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------

def test_aggregate_posts_group_columns_and_filters():
    group_by = ["q1", "seg"]
    filters = [{"col": "x"}]
    agg_result = {"dimensions": ["q1", "seg"], "cells": [], "total": 100}

    def handler(request):
        _check_auth(request)
        assert request.method == "POST"
        assert f"/api/v1/aggregation/{_ITEM}" in str(request.url)
        body = json.loads(request.content)
        assert body["group_columns"] == group_by
        assert body["filters"] == filters
        return _json_resp(agg_result)

    assert _make_client(handler).aggregate(_ITEM, group_by, filters) == agg_result


def test_aggregate_defaults_filters_to_empty_list():
    def handler(request):
        assert json.loads(request.content)["filters"] == []
        return _json_resp({"total": 0})

    _make_client(handler).aggregate(_ITEM, ["q1"])


def test_aggregate_normalises_single_dict_filter_to_list():
    def handler(request):
        assert json.loads(request.content)["filters"] == [{"col": "x"}]
        return _json_resp({"total": 0})

    _make_client(handler).aggregate(_ITEM, ["q1"], {"col": "x"})


# ---------------------------------------------------------------------------
# attach_material (multipart)
# ---------------------------------------------------------------------------

_SAV_BYTES = b"\x00\x01\x02SAV\xff\xfe"
_MATERIAL_ID = "material-abc123"


def test_attach_material_posts_multipart_to_blobs():
    captured = []

    def handler(request):
        _check_auth(request)
        assert request.method == "POST"
        assert f"/api/v1/projects/{_CASE}/blobs" in str(request.url)
        assert request.headers.get("content-type", "").startswith("multipart/form-data")
        body = request.content
        assert _SAV_BYTES in body            # file bytes present
        assert b"material" in body           # label field
        assert b"material-" in body          # reference_id field
        captured.append(request)
        return _json_resp({"reference_id": _MATERIAL_ID, "doc_id": "doc-1"})

    result = _make_client(handler).attach_material(_CASE, "survey.sav", _SAV_BYTES, "summary")
    assert len(captured) == 1
    assert result == _MATERIAL_ID


def test_attach_material_falls_back_to_generated_reference_id():
    def handler(request):
        return _json_resp({"doc_id": "doc-2"})  # omits reference_id

    result = _make_client(handler).attach_material(_CASE, "survey.sav", _SAV_BYTES, "summary")
    assert result.startswith("material-")


# ---------------------------------------------------------------------------
# get_material
# ---------------------------------------------------------------------------

def test_get_material_returns_raw_bytes():
    known = b"\x89SAV\x00\x01\x02\xff\xfe"

    def handler(request):
        _check_auth(request)
        assert request.method == "GET"
        assert f"/api/v1/projects/blobs/{_MATERIAL_ID}" in str(request.url)
        return httpx.Response(200, content=known,
                              headers={"content-type": "application/octet-stream"})

    assert _make_client(handler).get_material(_MATERIAL_ID) == known


# ---------------------------------------------------------------------------
# Byte-exact round-trip through a stateful mock
# ---------------------------------------------------------------------------

def test_attach_get_byte_exact_round_trip():
    raw_bytes = b"\x00SPSS SAV\xff\xfe\xab\xcd" + bytes(range(256))
    store: dict[str, bytes] = {}

    def handler(request):
        url = str(request.url)
        if request.method == "POST" and "/blobs" in url:
            m = re.search(rb"(material-[0-9a-f]{32})", request.content)
            assert m, "reference_id not found in multipart body"
            ref_id = m.group(1).decode()
            assert raw_bytes in request.content, "uploaded bytes missing from body"
            store[ref_id] = raw_bytes
            return _json_resp({"reference_id": ref_id})
        if request.method == "GET":
            ref_id = url.rstrip("/").split("/")[-1]
            if ref_id in store:
                return httpx.Response(200, content=store[ref_id],
                                      headers={"content-type": "application/octet-stream"})
            return httpx.Response(404, text="not found")
        return httpx.Response(405, text="method not allowed")

    client = _make_client(handler)
    material_id = client.attach_material(_CASE, "data.sav", raw_bytes, "")
    assert client.get_material(material_id) == raw_bytes


# ---------------------------------------------------------------------------
# Error semantics — DataHiveError
# ---------------------------------------------------------------------------

def test_non_2xx_raises_datahive_error():
    def handler(request):
        return httpx.Response(500, text="Internal Server Error")

    with pytest.raises(DataHiveError):
        _make_client(handler).list_cases()


def test_datahive_error_is_runtime_error():
    assert issubclass(DataHiveError, RuntimeError)


def test_datahive_error_carries_status_body_method_url():
    def handler(request):
        return httpx.Response(404, text="missing project")

    with pytest.raises(DataHiveError) as exc:
        _make_client(handler).create_case("X")
    err = exc.value
    assert err.status_code == 404
    assert err.body == "missing project"
    assert err.method == "POST"
    assert err.url.endswith("/api/v1/projects")
    # Message includes the status code and the body snippet.
    assert "404" in str(err)
    assert "missing project" in str(err)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500, 503])
def test_various_non_2xx_all_raise(status):
    def handler(request):
        return httpx.Response(status, text="err")

    with pytest.raises(DataHiveError) as exc:
        _make_client(handler).list_cases()
    assert exc.value.status_code == status


def test_get_material_non_2xx_raises():
    def handler(request):
        return httpx.Response(404, text="not found")

    with pytest.raises(DataHiveError) as exc:
        _make_client(handler).get_material("material-missing")
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

def test_context_manager_closes_cleanly():
    handler = lambda r: _json_resp({"count": 0, "projects": []})
    with DataHiveClient(base_url=_BASE, token=_TOKEN,
                        transport=httpx.MockTransport(handler)) as client:
        assert client.list_cases() == []
    # After exit the underlying httpx client is closed.
    assert client._client.is_closed
