"""Tests for opt-in disk persistence in InMemoryDataHiveClient (demo store).

Covers: round-trip across a simulated restart, id-counter continuity, corrupt/missing
file tolerance, atomic-write file layout, and unchanged pure in-memory behavior.
"""
import os

import pytest

from reportbuilder.store.memory_client import InMemoryDataHiveClient


def test_round_trip_across_restart(tmp_path):
    d = str(tmp_path)
    c1 = InMemoryDataHiveClient(storage_dir=d)
    cid = c1.create_case("My Case")
    mat_bytes = b"\x00\x01SAV-RAW-BYTES\xff\xfe"
    mid = c1.attach_material(cid, "data.sav", mat_bytes, "codebook")
    report_json = '{"title": "Report", "n": 42}'
    rid = c1.save_report(cid, None, report_json, "readable")

    # Simulate a restart: a fresh client on the same dir.
    c2 = InMemoryDataHiveClient(storage_dir=d)
    assert {x["id"] for x in c2.list_cases()} == {cid}
    assert c2.list_cases()[0]["name"] == "My Case"
    assert c2.get_material(mid) == mat_bytes  # byte-identical
    assert c2.load_report(cid, rid) == report_json  # verbatim JSON
    assert c2._material_meta[mid] == {"case_id": cid, "name": "data.sav"}


def test_id_counter_continuity(tmp_path):
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
        assert new != old
        assert int(new.rsplit("-", 1)[1]) > int(old.rsplit("-", 1)[1])


def test_missing_files_start_empty(tmp_path):
    # Empty existing dir -> empty store, no crash.
    c = InMemoryDataHiveClient(storage_dir=str(tmp_path))
    assert c.list_cases() == []
    assert c._n == 0


def test_nonexistent_dir_start_empty(tmp_path):
    d = str(tmp_path / "does-not-exist-yet")
    c = InMemoryDataHiveClient(storage_dir=d)
    assert c.list_cases() == []
    # First mutation creates the dir and persists.
    c.create_case("c")
    assert os.path.isfile(os.path.join(d, "cases.json"))


def test_corrupt_files_tolerated(tmp_path):
    d = tmp_path
    (d / "cases.json").write_text("{not valid json")
    (d / "state.json").write_text("garbage")
    (d / "reports.json").write_text("")
    c = InMemoryDataHiveClient(storage_dir=str(d))  # must not raise
    assert c.list_cases() == []
    assert c._n == 0
    # Still usable after recovering from corruption.
    cid = c.create_case("ok")
    assert cid in {x["id"] for x in c.list_cases()}


def test_atomic_write_produces_expected_files(tmp_path):
    d = tmp_path
    c = InMemoryDataHiveClient(storage_dir=str(d))
    cid = c.create_case("c")
    mid = c.attach_material(cid, "m", b"bytes", "cb")
    c.save_report(cid, None, "{}", "r")
    for name in ["cases.json", "material_meta.json", "reports.json", "state.json"]:
        assert (d / name).is_file()
    assert (d / "materials" / f"{mid}.sav").is_file()
    # No stray temp files left behind.
    assert not list(d.glob("*.tmp"))


def test_delete_report_persisted(tmp_path):
    d = str(tmp_path)
    c1 = InMemoryDataHiveClient(storage_dir=d)
    cid = c1.create_case("c")
    rid = c1.save_report(cid, None, "{}", "r")
    c1.delete_report(cid, rid)
    c2 = InMemoryDataHiveClient(storage_dir=d)
    with pytest.raises(KeyError):
        c2.load_report(cid, rid)


def test_pure_in_memory_unchanged(tmp_path):
    # storage_dir=None -> no disk writes at all, original behavior.
    c = InMemoryDataHiveClient()
    assert c.storage_dir is None
    cid = c.create_case("c")
    mid = c.attach_material(cid, "m", b"abc", "cb")
    rid = c.save_report(cid, None, '{"a":1}', "r")
    assert c.get_material(mid) == b"abc"
    assert c.load_report(cid, rid) == '{"a":1}'
    assert os.listdir(tmp_path) == []  # nothing written anywhere


def test_in_memory_get_material_missing_raises():
    c = InMemoryDataHiveClient()
    with pytest.raises(KeyError):
        c.get_material("mat-999")
