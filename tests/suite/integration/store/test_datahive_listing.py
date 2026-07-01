"""Real DataHiveClient.list_materials / list_reports via httpx.MockTransport.

Defines the expected datahive contract (GET /projects/{case}/blobs and
/projects/{case}/docs). NOTE: verify these endpoints against the live datahive —
staging currently runs the in-memory client, so this is the assumed shape.
"""
from __future__ import annotations

import httpx

from reportbuilder.store.datahive_client import DataHiveClient


def _client(handler) -> DataHiveClient:
    return DataHiveClient(base_url="https://hive.example", token="t",
                          transport=httpx.MockTransport(handler))


def test_list_materials_parses_blobs():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/projects/case-1/blobs"
        return httpx.Response(200, json={"blobs": [
            {"reference_id": "mat-1", "name": "a.sav"},
            {"reference_id": "mat-2", "name": "b.sav"},
        ]})

    mats = _client(handler).list_materials("case-1")
    assert mats == [
        {"material_id": "mat-1", "name": "a.sav"},
        {"material_id": "mat-2", "name": "b.sav"},
    ]


def test_list_reports_parses_and_filters_docs():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/projects/case-1/docs"
        return httpx.Response(200, json={"docs": [
            {"reference_id": "rep-1", "name": "Report 1", "label": "report"},
            {"reference_id": "other-1", "name": "codebook", "label": "codebook"},
        ]})

    reps = _client(handler).list_reports("case-1")
    assert reps == [{"report_id": "rep-1", "name": "Report 1"}]
