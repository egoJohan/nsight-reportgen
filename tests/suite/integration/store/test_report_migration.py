"""Backfill case links for reports saved before case-tagging (staging recovery).

The link is inferred from the report's question_refs → the material that has those
qids → that material's case. Best-effort: unique match links, otherwise flagged.
"""
from __future__ import annotations

import json

from reportbuilder.store.memory_client import InMemoryDataHiveClient
from reportbuilder.store.report_migration import (
    infer_case,
    backfill_report_case_links,
    _load_material_index,
)


# ---- pure inference ----

def test_infer_unique_material_links_to_its_case():
    materials = {"mat-1": ("case-A", {"q1", "m", "age"})}
    cid, reason = infer_case({"q1", "m"}, materials)
    assert reason == "linked"
    assert cid == "case-A"


def test_infer_ambiguous_across_different_cases():
    materials = {
        "mat-1": ("case-A", {"q1", "x"}),
        "mat-2": ("case-B", {"q1", "x"}),
    }
    cid, reason = infer_case({"q1"}, materials)
    assert reason == "ambiguous"
    assert cid is None


def test_infer_multiple_materials_same_case_links():
    materials = {
        "mat-1": ("case-A", {"q1"}),
        "mat-2": ("case-A", {"q1", "extra"}),
    }
    cid, reason = infer_case({"q1"}, materials)
    assert reason == "linked"
    assert cid == "case-A"


def test_infer_unmatched_when_no_material_covers_refs():
    materials = {"mat-1": ("case-A", {"q1"})}
    cid, reason = infer_case({"nope"}, materials)
    assert reason == "unmatched"
    assert cid is None


def test_infer_unmatched_when_no_refs():
    materials = {"mat-1": ("case-A", {"q1"})}
    cid, reason = infer_case(set(), materials)
    assert reason == "unmatched"
    assert cid is None


# ---- store backfill (fabricated material index → no SAV needed) ----

def _orphan_report(client, rid, name, refs):
    client._reports[rid] = json.dumps(
        {"name": name, "charts": [{"question_ref": r} for r in refs]}
    )


def test_backfill_links_orphans_to_their_case(tmp_path):
    c = InMemoryDataHiveClient(storage_dir=str(tmp_path / "s"))
    a = c.create_case("A")
    b = c.create_case("B")
    _orphan_report(c, "rep-a", "RA", ["q1"])
    _orphan_report(c, "rep-b", "RB", ["x1"])
    _orphan_report(c, "rep-x", "RX", ["ghost"])

    index = {"mat-a": (a, {"q1", "m"}), "mat-b": (b, {"x1", "x2"})}
    summary = backfill_report_case_links(c, material_index=index)

    assert set(summary["linked"]) == {"rep-a", "rep-b"}
    assert summary["unmatched"] == ["rep-x"]
    assert [r["report_id"] for r in c.list_reports(a)] == ["rep-a"]
    assert [r["report_id"] for r in c.list_reports(b)] == ["rep-b"]
    # Names come from the report JSON.
    assert c.list_reports(a)[0]["name"] == "RA"


def test_backfill_persists_across_restart(tmp_path):
    c = InMemoryDataHiveClient(storage_dir=str(tmp_path / "s"))
    a = c.create_case("A")
    _orphan_report(c, "rep-a", "RA", ["q1"])
    backfill_report_case_links(c, material_index={"mat-a": (a, {"q1"})})

    c2 = InMemoryDataHiveClient(storage_dir=str(tmp_path / "s"))
    assert [r["report_id"] for r in c2.list_reports(a)] == ["rep-a"]


def test_backfill_skips_already_tagged(tmp_path):
    c = InMemoryDataHiveClient(storage_dir=str(tmp_path / "s"))
    a = c.create_case("A")
    rid = c.save_report(a, None, '{"name":"Tagged","charts":[]}', "Tagged")
    summary = backfill_report_case_links(c, material_index={"mat-a": (a, {"q1"})})
    assert rid not in summary["linked"]  # already had a case link


def test_load_material_index_reads_qids(tmp_path):
    from reportbuilder.testing.fixtures import synthetic_sav_bytes
    c = InMemoryDataHiveClient(storage_dir=str(tmp_path / "s"))
    a = c.create_case("A")
    mid = c.attach_material(a, "survey.sav", synthetic_sav_bytes(), "cb")
    index = _load_material_index(c)
    assert mid in index
    case_id, qids = index[mid]
    assert case_id == a
    assert "q1" in qids
