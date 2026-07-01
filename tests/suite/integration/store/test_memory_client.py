"""Integration tests for the local-fs InMemoryDataHiveClient store.

Deterministic, no network. Covers pure in-memory behavior (storage_dir=None) and
opt-in disk persistence (storage_dir set): CRUD on cases/materials/reports, the
shared monotonic id counter, byte-exact material round-trips, verbatim report
round-trips, cascade deletes, error semantics, restart continuity, tolerant load
of missing/corrupt state, and on-disk file layout.
"""
from __future__ import annotations

import os

import pytest

from reportbuilder.store.memory_client import InMemoryDataHiveClient


# ---------------------------------------------------------------------------
# Pure in-memory (storage_dir=None)
# ---------------------------------------------------------------------------

def test_create_and_list_cases():
    c = InMemoryDataHiveClient()
    cid1 = c.create_case("Alpha")
    cid2 = c.create_case("Beta")
    listing = c.list_cases()
    assert {x["id"] for x in listing} == {cid1, cid2}
    by_id = {x["id"]: x["name"] for x in listing}
    assert by_id == {cid1: "Alpha", cid2: "Beta"}


def test_list_cases_returns_copies_not_internal_dicts():
    c = InMemoryDataHiveClient()
    cid = c.create_case("Alpha")
    listing = c.list_cases()
    listing[0]["name"] = "Mutated"
    # Mutating the returned dict must not affect the store.
    assert c.list_cases()[0]["name"] == "Alpha"
    assert cid


def test_id_prefixes():
    c = InMemoryDataHiveClient()
    cid = c.create_case("c")
    mid = c.attach_material(cid, "m", b"x", "cb")
    rid = c.save_report(cid, None, "{}", "r")
    assert cid.startswith("case-")
    assert mid.startswith("mat-")
    assert rid.startswith("rep-")


def test_shared_counter_monotonic_across_types():
    """_n is a single counter shared across cases + materials + reports."""
    c = InMemoryDataHiveClient()
    cid = c.create_case("c")          # -> case-1
    mid = c.attach_material(cid, "m", b"x", "cb")  # -> mat-2
    rid = c.save_report(cid, None, "{}", "r")      # -> rep-3
    cid2 = c.create_case("c2")        # -> case-4
    nums = [int(x.rsplit("-", 1)[1]) for x in (cid, mid, rid, cid2)]
    assert nums == [1, 2, 3, 4]
    assert c._n == 4


def test_attach_and_get_material_byte_exact():
    c = InMemoryDataHiveClient()
    cid = c.create_case("c")
    raw = b"\x00\x01SAV\xff\xfe" + bytes(range(256))
    mid = c.attach_material(cid, "data.sav", raw, "codebook")
    got = c.get_material(mid)
    assert got == raw
    assert isinstance(got, bytes)


def test_attach_material_copies_input_bytes():
    """attach stores bytes(...) — a later mutation of a bytearray must not leak in."""
    c = InMemoryDataHiveClient()
    cid = c.create_case("c")
    buf = bytearray(b"orig")
    mid = c.attach_material(cid, "m", buf, "cb")
    buf.extend(b"XXX")
    assert c.get_material(mid) == b"orig"


def test_get_material_missing_raises_keyerror():
    c = InMemoryDataHiveClient()
    with pytest.raises(KeyError):
        c.get_material("mat-999")


def test_save_and_load_report_verbatim():
    c = InMemoryDataHiveClient()
    cid = c.create_case("c")
    report_json = '{"title":"Report","n":42,"unicode":"äö"}'
    rid = c.save_report(cid, None, report_json, "My Report")
    assert c.load_report(cid, rid) == report_json


def test_save_report_explicit_id_overwrites():
    c = InMemoryDataHiveClient()
    cid = c.create_case("c")
    rid = c.save_report(cid, None, '{"v":1}', "r")
    # Re-save under the same id with new content.
    same = c.save_report(cid, rid, '{"v":2}', "r")
    assert same == rid
    assert c.load_report(cid, rid) == '{"v":2}'


def test_save_report_explicit_id_does_not_bump_counter():
    c = InMemoryDataHiveClient()
    cid = c.create_case("c")
    n_before = c._n
    c.save_report(cid, "rep-explicit", "{}", "r")
    assert c._n == n_before  # explicit id → no new id generated


def test_load_report_missing_raises_keyerror():
    c = InMemoryDataHiveClient()
    cid = c.create_case("c")
    with pytest.raises(KeyError):
        c.load_report(cid, "rep-missing")


def test_delete_report_removes_it():
    c = InMemoryDataHiveClient()
    cid = c.create_case("c")
    rid = c.save_report(cid, None, "{}", "r")
    c.delete_report(cid, rid)
    with pytest.raises(KeyError):
        c.load_report(cid, rid)


def test_delete_report_missing_is_tolerated():
    c = InMemoryDataHiveClient()
    cid = c.create_case("c")
    # pop(..., None) — deleting an unknown report must not raise.
    c.delete_report(cid, "rep-nope")


def test_rename_case_updates_listing():
    c = InMemoryDataHiveClient()
    cid = c.create_case("Old")
    c.rename_case(cid, "New")
    by_id = {x["id"]: x["name"] for x in c.list_cases()}
    assert by_id[cid] == "New"


def test_rename_case_missing_raises_keyerror():
    c = InMemoryDataHiveClient()
    with pytest.raises(KeyError):
        c.rename_case("case-999", "Whatever")


def test_delete_case_removes_it():
    c = InMemoryDataHiveClient()
    cid = c.create_case("c")
    c.delete_case(cid)
    assert c.list_cases() == []


def test_delete_case_missing_raises_keyerror():
    c = InMemoryDataHiveClient()
    with pytest.raises(KeyError):
        c.delete_case("case-999")


def test_delete_case_cascades_materials():
    c = InMemoryDataHiveClient()
    cid = c.create_case("c")
    other = c.create_case("other")
    mid = c.attach_material(cid, "m", b"bytes", "cb")
    other_mid = c.attach_material(other, "m2", b"keep", "cb")
    c.delete_case(cid)
    # The deleted case's material is gone.
    with pytest.raises(KeyError):
        c.get_material(mid)
    # The unrelated case's material survives.
    assert c.get_material(other_mid) == b"keep"


def test_aggregate_returns_stub_shape():
    c = InMemoryDataHiveClient()
    result = c.aggregate("mat-1", ["q1", "seg"], {}, weight=None)
    assert result == {"dimensions": ["q1", "seg"], "cells": [], "total": 0}


def test_aggregate_dimensions_is_a_fresh_list():
    c = InMemoryDataHiveClient()
    group_by = ["q1"]
    result = c.aggregate("mat-1", group_by, {})
    assert result["dimensions"] == ["q1"]
    assert result["dimensions"] is not group_by  # list(group_by) copies


# ---------------------------------------------------------------------------
# Disk persistence (storage_dir set)
# ---------------------------------------------------------------------------

def test_storage_dir_attribute_set(tmp_path):
    c = InMemoryDataHiveClient(storage_dir=str(tmp_path))
    assert c.storage_dir == str(tmp_path)


def test_round_trip_across_restart(tmp_path):
    d = str(tmp_path)
    c1 = InMemoryDataHiveClient(storage_dir=d)
    cid = c1.create_case("My Case")
    raw = b"\x00\x01SAV-RAW\xff\xfe" + bytes(range(64))
    mid = c1.attach_material(cid, "data.sav", raw, "codebook")
    report_json = '{"title":"Report","n":42}'
    rid = c1.save_report(cid, None, report_json, "readable")

    # Restart: a fresh client on the same dir.
    c2 = InMemoryDataHiveClient(storage_dir=d)
    assert {x["id"] for x in c2.list_cases()} == {cid}
    assert c2.list_cases()[0]["name"] == "My Case"
    assert c2.get_material(mid) == raw        # byte-identical, loaded from disk
    assert c2.load_report(cid, rid) == report_json


def test_id_counter_continues_after_restart(tmp_path):
    d = str(tmp_path)
    c1 = InMemoryDataHiveClient(storage_dir=d)
    cid = c1.create_case("c")
    mid = c1.attach_material(cid, "m", b"x", "cb")
    rid = c1.save_report(cid, None, "{}", "r")
    max_n = c1._n

    c2 = InMemoryDataHiveClient(storage_dir=d)
    assert c2._n == max_n  # counter restored
    new_cid = c2.create_case("c2")
    new_mid = c2.attach_material(new_cid, "m2", b"y", "cb")
    new_rid = c2.save_report(new_cid, None, "{}", "r")
    for old, new in [(cid, new_cid), (mid, new_mid), (rid, new_rid)]:
        assert int(new.rsplit("-", 1)[1]) > int(old.rsplit("-", 1)[1])


def test_files_written_after_ops(tmp_path):
    d = tmp_path
    c = InMemoryDataHiveClient(storage_dir=str(d))
    cid = c.create_case("c")
    mid = c.attach_material(cid, "m", b"bytes", "cb")
    c.save_report(cid, None, "{}", "r")
    for name in ["cases.json", "material_meta.json", "reports.json", "state.json"]:
        assert (d / name).is_file(), f"{name} not written"
    assert (d / "materials" / f"{mid}.sav").is_file()
    # Atomic writes leave no stray temp files.
    assert not list(d.glob("*.tmp"))


def test_delete_case_persists_and_removes_material_file(tmp_path):
    d = tmp_path
    c1 = InMemoryDataHiveClient(storage_dir=str(d))
    cid = c1.create_case("c")
    mid = c1.attach_material(cid, "m", b"bytes", "cb")
    assert (d / "materials" / f"{mid}.sav").is_file()
    c1.delete_case(cid)
    # File removed on cascade, and delete persisted across restart.
    assert not (d / "materials" / f"{mid}.sav").exists()
    c2 = InMemoryDataHiveClient(storage_dir=str(d))
    assert c2.list_cases() == []


def test_delete_report_persists(tmp_path):
    d = str(tmp_path)
    c1 = InMemoryDataHiveClient(storage_dir=d)
    cid = c1.create_case("c")
    rid = c1.save_report(cid, None, "{}", "r")
    c1.delete_report(cid, rid)
    c2 = InMemoryDataHiveClient(storage_dir=d)
    with pytest.raises(KeyError):
        c2.load_report(cid, rid)


def test_rename_case_persists(tmp_path):
    d = str(tmp_path)
    c1 = InMemoryDataHiveClient(storage_dir=d)
    cid = c1.create_case("Old")
    c1.rename_case(cid, "New")
    c2 = InMemoryDataHiveClient(storage_dir=d)
    assert {x["id"]: x["name"] for x in c2.list_cases()}[cid] == "New"


def test_empty_existing_dir_starts_empty(tmp_path):
    c = InMemoryDataHiveClient(storage_dir=str(tmp_path))
    assert c.list_cases() == []
    assert c._n == 0


def test_nonexistent_dir_starts_empty_then_creates(tmp_path):
    d = str(tmp_path / "not-there-yet")
    c = InMemoryDataHiveClient(storage_dir=d)
    assert c.list_cases() == []
    c.create_case("c")
    assert os.path.isfile(os.path.join(d, "cases.json"))


def test_corrupt_and_empty_files_tolerated(tmp_path):
    d = tmp_path
    (d / "cases.json").write_text("{not valid json")
    (d / "state.json").write_text("garbage-not-json")
    (d / "reports.json").write_text("")            # empty
    (d / "material_meta.json").write_text("[1,2,3]")  # wrong type (list, not dict)
    c = InMemoryDataHiveClient(storage_dir=str(d))  # must not raise
    assert c.list_cases() == []
    assert c._n == 0
    # Still usable after recovering from corruption.
    cid = c.create_case("ok")
    assert cid in {x["id"] for x in c.list_cases()}


def test_material_bytes_survive_but_are_lazy(tmp_path):
    """After restart the material comes off disk, byte-exact, without preload."""
    d = str(tmp_path)
    raw = bytes(range(256))
    c1 = InMemoryDataHiveClient(storage_dir=d)
    cid = c1.create_case("c")
    mid = c1.attach_material(cid, "m", raw, "cb")

    c2 = InMemoryDataHiveClient(storage_dir=d)
    assert mid not in c2._materials  # not preloaded into memory
    assert c2.get_material(mid) == raw  # read lazily from disk
    assert mid in c2._materials  # now cached
