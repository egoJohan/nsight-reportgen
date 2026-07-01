"""Server-side listing of a case's materials and reports (multi-user gap fix).

Case→material/report association must live in the store, not the browser, so any
user/device opening a case sees its material and reports.
"""
from __future__ import annotations

import pytest

from reportbuilder.store.memory_client import InMemoryDataHiveClient


def _client(tmp_path) -> InMemoryDataHiveClient:
    return InMemoryDataHiveClient(storage_dir=str(tmp_path / "store"))


def test_list_materials_scoped_to_case(tmp_path):
    c = _client(tmp_path)
    case = c.create_case("A")
    other = c.create_case("B")
    m1 = c.attach_material(case, "f1.sav", b"x", "cb")
    m2 = c.attach_material(case, "f2.sav", b"y", "cb")
    mo = c.attach_material(other, "g.sav", b"z", "cb")

    mats = c.list_materials(case)
    ids = [m["material_id"] for m in mats]
    assert set(ids) == {m1, m2}
    assert mo not in ids
    assert all("name" in m for m in mats)


def test_list_reports_scoped_to_case_with_names(tmp_path):
    c = _client(tmp_path)
    case = c.create_case("A")
    other = c.create_case("B")
    r1 = c.save_report(case, None, '{"a":1}', "Report 1")
    r2 = c.save_report(case, None, '{"a":2}', "Report 2")
    ro = c.save_report(other, None, '{"a":3}', "Other")

    reps = c.list_reports(case)
    ids = [r["report_id"] for r in reps]
    assert set(ids) == {r1, r2}
    assert ro not in ids
    names = {r["report_id"]: r["name"] for r in reps}
    assert names[r1] == "Report 1"


def test_report_case_link_persists_across_restart(tmp_path):
    c = _client(tmp_path)
    case = c.create_case("A")
    r1 = c.save_report(case, None, '{"a":1}', "Report 1")
    # Fresh client on the same dir = a "restart" / another server process.
    c2 = InMemoryDataHiveClient(storage_dir=str(tmp_path / "store"))
    assert [r["report_id"] for r in c2.list_reports(case)] == [r1]


def test_material_case_link_persists_across_restart(tmp_path):
    c = _client(tmp_path)
    case = c.create_case("A")
    m1 = c.attach_material(case, "f.sav", b"x", "cb")
    c2 = InMemoryDataHiveClient(storage_dir=str(tmp_path / "store"))
    assert [m["material_id"] for m in c2.list_materials(case)] == [m1]


def test_delete_report_drops_from_listing(tmp_path):
    c = _client(tmp_path)
    case = c.create_case("A")
    r1 = c.save_report(case, None, "{}", "R1")
    c.delete_report(case, r1)
    assert c.list_reports(case) == []


def test_delete_case_cascade_clears_listings(tmp_path):
    c = _client(tmp_path)
    case = c.create_case("A")
    c.attach_material(case, "f.sav", b"x", "cb")
    c.save_report(case, None, "{}", "R1")
    c.delete_case(case)
    assert c.list_materials(case) == []
    assert c.list_reports(case) == []


def test_legacy_report_without_case_link_is_tolerated(tmp_path):
    """A report saved before case-tagging (no meta) must not break listing or load."""
    c = _client(tmp_path)
    case = c.create_case("A")
    r1 = c.save_report(case, None, '{"a":1}', "R1")
    # Simulate a legacy entry: report bytes present, but strip its case meta.
    c._report_meta.pop(r1, None)  # type: ignore[attr-defined]
    c._save()  # type: ignore[attr-defined]
    c2 = InMemoryDataHiveClient(storage_dir=str(tmp_path / "store"))
    # Not listed per-case (orphaned), but still loadable by id and no crash.
    assert r1 not in [r["report_id"] for r in c2.list_reports(case)]
    assert c2.load_report(case, r1) == '{"a":1}'
