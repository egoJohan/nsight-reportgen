"""Per-material config storage (the grouping override lives here).

Mirrors the report_meta pattern: persisted, restart-safe, cascade-cleared.
"""
from __future__ import annotations

import httpx

from reportbuilder.store.datahive_client import DataHiveClient
from reportbuilder.store.memory_client import InMemoryDataHiveClient


def _mem(tmp_path):
    return InMemoryDataHiveClient(storage_dir=str(tmp_path / "s"))


def test_roundtrip(tmp_path):
    c = _mem(tmp_path)
    c.save_material_config("mat-1", '{"groups":[{"kind":"multi","variables":["a","b"]}]}')
    assert c.load_material_config("mat-1") == '{"groups":[{"kind":"multi","variables":["a","b"]}]}'


def test_none_when_unset(tmp_path):
    assert _mem(tmp_path).load_material_config("mat-x") is None


def test_persists_across_restart(tmp_path):
    c = _mem(tmp_path)
    c.save_material_config("mat-1", '{"a":1}')
    c2 = InMemoryDataHiveClient(storage_dir=str(tmp_path / "s"))
    assert c2.load_material_config("mat-1") == '{"a":1}'


def test_delete_case_cascade_drops_material_config(tmp_path):
    c = _mem(tmp_path)
    case = c.create_case("A")
    mid = c.attach_material(case, "f.sav", b"x", "cb")
    c.save_material_config(mid, '{"g":1}')
    c.delete_case(case)
    assert c.load_material_config(mid) is None


# ---- real client (assumed datahive contract — verify against live API) ----

def _real(handler):
    return DataHiveClient(base_url="https://hive.example", token="t",
                          transport=httpx.MockTransport(handler))


def test_real_load_material_config():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "GET"
        assert req.url.path == "/api/v1/projects/blobs/mat-1/config"
        return httpx.Response(200, json={"config": '{"groups":[]}'})
    assert _real(handler).load_material_config("mat-1") == '{"groups":[]}'


def test_real_load_material_config_404_is_none():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "no config"})
    assert _real(handler).load_material_config("mat-1") is None


def test_real_save_material_config():
    seen = {}
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "PUT"
        assert req.url.path == "/api/v1/projects/blobs/mat-1/config"
        import json
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"ok": True})
    _real(handler).save_material_config("mat-1", '{"a":1}')
    assert seen["body"] == {"config": '{"a":1}'}
