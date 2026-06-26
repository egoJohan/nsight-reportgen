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
# 5. load_report — byte-exact round-trip  (REQ-C-08)
# ---------------------------------------------------------------------------

def test_load_report_returns_text_verbatim():
    """load_report GETs the docs endpoint and returns the 'text' field verbatim.
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
    result = client.load_report(_CASE, _REF)
    assert result == stored_text  # byte-exact


# ---------------------------------------------------------------------------
# 6. delete_report  (REQ-C-12)
# ---------------------------------------------------------------------------

def test_delete_report_issues_delete():
    """delete_report issues DELETE to the right path.  REQ-C-12."""
    called: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        _check_auth(request)
        assert request.method == "DELETE"
        assert f"/api/v1/projects/{_CASE}/docs/{_REF}" in str(request.url)
        called.append("yes")
        return httpx.Response(204)

    client = _make_client(handler)
    client.delete_report(_CASE, _REF)
    assert called == ["yes"]


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


# ---------------------------------------------------------------------------
# 10. attach_material — multipart POST to /api/v1/projects/{case_id}/blobs  (REQ-C-01/04)
# ---------------------------------------------------------------------------

_SAV_BYTES = b"\x00\x01\x02SAV\xff\xfe"  # non-UTF8 binary blob
_MATERIAL_ID = "material-abc123"


def test_attach_material_posts_multipart_to_blobs():
    """attach_material issues a multipart POST to /api/v1/projects/{case_id}/blobs with the
    file bytes, label='material', a reference_id starting 'material-', and the Bearer header;
    returns the reference_id from the response.  REQ-C-01/REQ-C-04.
    """
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        _check_auth(request)
        assert request.method == "POST"
        assert f"/api/v1/projects/{_CASE}/blobs" in str(request.url)
        # Multipart content-type
        ct = request.headers.get("content-type", "")
        assert ct.startswith("multipart/form-data"), f"Expected multipart, got {ct!r}"
        # Raw content must carry the binary blob bytes and the field names
        body = request.content
        assert _SAV_BYTES in body, "file bytes not in multipart body"
        assert b"material" in body, "'label=material' field not in multipart body"
        assert b"material-" in body, "reference_id not in multipart body"
        captured.append(request)
        return _json_resp({"reference_id": _MATERIAL_ID, "doc_id": "doc-1", "size": len(_SAV_BYTES)})

    client = _make_client(handler)
    result = client.attach_material(_CASE, "survey.sav", _SAV_BYTES, "summary")

    assert len(captured) == 1
    assert result == _MATERIAL_ID


def test_attach_material_falls_back_to_generated_reference_id():
    """attach_material returns the server reference_id if present; falls back to the
    locally generated one if the response omits it.  REQ-C-04.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        # Response omits reference_id — client must fall back to its own generated id.
        return _json_resp({"doc_id": "doc-2", "size": 4})

    client = _make_client(handler)
    result = client.attach_material(_CASE, "survey.sav", _SAV_BYTES, "summary")
    assert result.startswith("material-"), f"Expected fallback reference_id, got {result!r}"


# ---------------------------------------------------------------------------
# 11. get_material — byte-exact GET /api/v1/projects/blobs/{material_id}  (REQ-C-01/05)
# ---------------------------------------------------------------------------

def test_get_material_returns_raw_bytes():
    """get_material GETs /api/v1/projects/blobs/{material_id} and returns resp.content
    byte-exact (does not json-decode).  REQ-C-01/REQ-C-05.
    """
    known_bytes = b"\x89SAV\x00\x01\x02\xff\xfe"

    def handler(request: httpx.Request) -> httpx.Response:
        _check_auth(request)
        assert request.method == "GET"
        assert f"/api/v1/projects/blobs/{_MATERIAL_ID}" in str(request.url)
        return httpx.Response(200, content=known_bytes,
                              headers={"content-type": "application/octet-stream"})

    client = _make_client(handler)
    result = client.get_material(_MATERIAL_ID)
    assert result == known_bytes


def test_get_material_non_2xx_raises_clear_error():
    """get_material raises RuntimeError with status on non-2xx.  REQ-C-05."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = _make_client(handler)
    with pytest.raises(RuntimeError, match="404"):
        client.get_material("material-missing")


# ---------------------------------------------------------------------------
# 12. Byte-exact round-trip: attach → get returns identical binary  (REQ-C-01/04/05)
# ---------------------------------------------------------------------------

def test_attach_get_byte_exact_round_trip():
    """Byte-exact round-trip: attach_material stores the uploaded bytes under the
    reference_id, then get_material returns the identical bytes including non-UTF8
    binary content.  REQ-C-C-01/REQ-C-04/REQ-C-05.
    """
    store: dict[str, bytes] = {}
    captured_ref: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/blobs" in str(request.url) and "projects/" in str(request.url):
            # Extract the reference_id from the multipart body (it's a text field).
            # We look for it in the raw content; multipart encodes each field as text.
            body = request.content
            # Find the reference_id value: it starts with b"material-" in the multipart body.
            # Locate the field by scanning for "material-" followed by hex chars.
            import re
            m = re.search(rb"(material-[0-9a-f]{32})", body)
            assert m, "reference_id not found in multipart body"
            ref_id = m.group(1).decode()
            # Also extract the file bytes: the file content starts after its headers.
            # We use a simple split on the known sentinel byte sequence for the test payload.
            # The raw file bytes are embedded verbatim in the body.
            file_bytes = _SAV_BYTES  # we know what was sent in this test
            store[ref_id] = file_bytes
            captured_ref.append(ref_id)
            return _json_resp({"reference_id": ref_id, "doc_id": "doc-rt", "size": len(file_bytes)})

        if request.method == "GET":
            # GET /api/v1/projects/blobs/{material_id}
            url = str(request.url)
            ref_id = url.rstrip("/").split("/")[-1]
            if ref_id in store:
                return httpx.Response(200, content=store[ref_id],
                                      headers={"content-type": "application/octet-stream"})
            return httpx.Response(404, text="not found")

        return httpx.Response(405, text="method not allowed")

    # Use real non-UTF8 binary (simulated .sav) to prove byte-exactness.
    raw_bytes = b"\x00SPSS SAV\xff\xfe\xab\xcd" + bytes(range(256))

    client = _make_client(handler)

    # Override the handler's file_bytes reference to use raw_bytes for this test.
    # Re-implement with a closure that captures raw_bytes directly.
    store2: dict[str, bytes] = {}

    def handler2(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            import re
            body = request.content
            m = re.search(rb"(material-[0-9a-f]{32})", body)
            assert m, "reference_id not found in multipart body"
            ref_id = m.group(1).decode()
            # The file bytes are in the multipart body verbatim.
            assert raw_bytes in body, "uploaded bytes not present in multipart body"
            store2[ref_id] = raw_bytes
            return _json_resp({"reference_id": ref_id, "doc_id": "doc-rt2", "size": len(raw_bytes)})

        if request.method == "GET":
            url = str(request.url)
            ref_id = url.rstrip("/").split("/")[-1]
            if ref_id in store2:
                return httpx.Response(200, content=store2[ref_id],
                                      headers={"content-type": "application/octet-stream"})
            return httpx.Response(404, text="not found")

        return httpx.Response(405, text="method not allowed")

    client2 = _make_client(handler2)
    material_id = client2.attach_material(_CASE, "data.sav", raw_bytes, "")
    retrieved = client2.get_material(material_id)
    assert retrieved == raw_bytes, (
        f"Byte-exact round-trip failed: uploaded {len(raw_bytes)} bytes, "
        f"got back {len(retrieved)} bytes"
    )
