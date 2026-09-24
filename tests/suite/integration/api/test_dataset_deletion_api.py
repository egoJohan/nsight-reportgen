"""Deleting a study's last dataset, over HTTP.

Spec: docs/superpowers/specs/2026-09-24-dataset-deletion-design.md. The study
becomes read-only for good — enforced by the server for every write route, not
only hidden in the UI — and its generated decks stay downloadable.
"""
from __future__ import annotations

import json
import re

import pytest
from fastapi.routing import APIRoute

from reportbuilder.api.deps_store import get_auth, get_repository

pytestmark = pytest.mark.integration

DECK = b"PK\x03\x04 the delivered deck"


def _repo(client):
    return client.app.dependency_overrides[get_repository](), \
        client.app.dependency_overrides[get_auth]()


def _with_consent(client, method, url):
    repo, _auth = _repo(client)
    for _ in range(100):
        resp = client.request(method, url)
        detail = resp.json().get("detail") if resp.status_code == 409 else None
        if isinstance(detail, dict) and detail.get("error") == "consent_required":
            repo.store.approve(detail["request_id"])
            continue
        return resp
    raise AssertionError("consent loop did not converge")


@pytest.fixture
def study(client_memory, synthetic_bytes):
    """A study with one dataset, a generated report and a never-generated one."""
    c = client_memory
    cust = c.post("/customers", json={"name": "Acme"}).json()["id"]
    cid = c.post(f"/customers/{cust}/cases", json={"name": "Brändi"}).json()["id"]
    mid = c.post(f"/cases/{cid}/materials", files={
        "file": ("brandi.sav", synthetic_bytes, "application/octet-stream")}).json()["material_id"]
    repo, auth = _repo(c)
    done = repo.save_report(auth, cust, cid, json.dumps({"name": "Delivered"}))
    repo.save_render(auth, cust, cid, done.id, DECK, repo.render_key(auth, cust, cid, done.id, mid))
    draft = repo.save_report(auth, cust, cid, json.dumps({"name": "Draft"}))
    return {"cust": cust, "cid": cid, "mid": mid, "done": done.id, "draft": draft.id}


def _delete_dataset(client, s):
    return _with_consent(client, "DELETE", f"/cases/{s['cid']}/materials/{s['mid']}")


def test_the_warning_names_what_is_kept_and_what_is_lost(client_memory, study):
    u = client_memory.get(f"/cases/{study['cid']}/materials/{study['mid']}/usage").json()
    assert u == {"last_dataset": True, "remaining": [],
                 "with_deck": ["Delivered"], "without_deck": ["Draft"]}


def test_deleting_the_last_dataset_leaves_only_the_decks(client_memory, study):
    c, s = client_memory, study
    resp = _delete_dataset(c, s)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": s["mid"], "read_only": True}

    listed = c.get(f"/cases/{s['cid']}/reports").json()["reports"]
    assert [(r["report_id"], r["deck_only"], r["rendered"]) for r in listed] == \
        [(s["done"], True, True)]
    assert c.get(f"/cases/{s['cid']}/materials").json()["materials"] == []
    assert c.get(f"/cases/{s['cid']}/reports/{s['done']}").status_code == 404

    deck = c.get(f"/cases/{s['cid']}/reports/{s['done']}/preview.pptx")
    assert deck.status_code == 200 and deck.content == DECK


def test_the_study_says_it_is_read_only(client_memory, study):
    c, s = client_memory, study
    _delete_dataset(c, s)
    got = c.get(f"/customers/{s['cust']}/cases/{s['cid']}").json()["dataset_deleted"]
    assert got["completed"] is True and got["files"] == ["brandi.sav"]
    listed = {k["id"]: k for k in c.get(f"/customers/{s['cust']}/cases").json()}
    assert listed[s["cid"]]["dataset_deleted"]["completed"] is True


def _write_routes(app):
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            if "{case_id}" in route.path:
                yield method, route.path


def test_every_write_to_the_study_is_refused(client_memory, study):
    """Walks the app's own routes, so a write route added later is covered too."""
    c, s = client_memory, study
    _delete_dataset(c, s)
    allowed = {
        # Deleting the whole study: an archive can still be removed entirely.
        ("DELETE", "/cases/{case_id}"),
        # A user's OWN screen state for the study, kept in their settings —
        # it writes nothing to the study and is not gated by study access.
        ("PUT", "/settings/workspace/{case_id}"),
    }
    checked = 0
    for method, path in _write_routes(c.app):
        if (method, path) in allowed:
            continue
        url = path.replace("{case_id}", s["cid"]).replace("{customer_id}", s["cust"]) \
                  .replace("{material_id}", s["mid"]).replace("{report_id}", s["done"])
        url = re.sub(r"\{[^}]+\}", "x", url)
        resp = c.request(method, url, json={})
        detail = resp.json().get("detail") if resp.headers.get("content-type", "").startswith(
            "application/json") else None
        assert resp.status_code == 409 and isinstance(detail, dict) \
            and detail.get("error") == "study_read_only", (method, path, resp.status_code, resp.text[:200])
        checked += 1
    assert checked >= 10, f"only {checked} write routes found — the walk is not seeing the app"


def test_the_study_itself_can_still_be_deleted(client_memory, study):
    c, s = client_memory, study
    _delete_dataset(c, s)
    resp = _with_consent(c, "DELETE", f"/cases/{s['cid']}")
    assert resp.status_code == 200, resp.text
    assert all(k["id"] != s["cid"] for k in c.get("/cases").json())


def test_an_unfinished_delete_can_be_finished_and_nothing_else_written(client_memory, study):
    c, s = client_memory, study
    _delete_dataset(c, s)
    repo, auth = _repo(c)
    repo._set_dataset_deleted(auth, s["cust"], s["cid"], {
        **repo.get_case(auth, s["cust"], s["cid"]).dataset_deleted, "completed": False})

    refused = c.patch(f"/cases/{s['cid']}", json={"name": "renamed"})
    assert refused.status_code == 409 and refused.json()["detail"]["error"] == "study_read_only"
    finished = _delete_dataset(c, s)
    assert finished.status_code == 200, finished.text
    assert repo.get_case(auth, s["cust"], s["cid"]).dataset_deleted["completed"] is True


def test_someone_elses_open_report_blocks_the_delete(client_memory, study):
    c, s = client_memory, study
    repo, auth = _repo(c)
    repo.lock_report(auth, s["cust"], s["cid"], s["draft"], "usr-other", "Maija Meikäläinen")
    resp = c.delete(f"/cases/{s['cid']}/materials/{s['mid']}")
    assert resp.status_code == 409
    assert "Maija Meikäläinen" in resp.json()["detail"]
    assert repo.get_case(auth, s["cust"], s["cid"]).dataset_deleted is None


def test_one_of_two_datasets_leaves_the_study_live(client_memory, study, synthetic_bytes):
    c, s = client_memory, study
    newer = c.post(f"/cases/{s['cid']}/materials", files={
        "file": ("brandi-v2.sav", synthetic_bytes, "application/octet-stream")}).json()["material_id"]
    u = c.get(f"/cases/{s['cid']}/materials/{s['mid']}/usage").json()
    assert u["last_dataset"] is False and u["remaining"] == ["brandi-v2.sav"]
    resp = _delete_dataset(c, s)
    assert resp.json() == {"deleted": s["mid"], "read_only": False}
    assert [m["material_id"] for m in c.get(f"/cases/{s['cid']}/materials").json()["materials"]] == [newer]
    assert c.get(f"/cases/{s['cid']}/reports/{s['draft']}").status_code == 200


def test_the_decks_can_be_deleted_too(client_memory, study):
    """The warning's tick box, left empty: nothing of the reports remains."""
    c, s = client_memory, study
    resp = _with_consent(c, "DELETE", f"/cases/{s['cid']}/materials/{s['mid']}?keep_decks=false")
    assert resp.status_code == 200, resp.text
    assert c.get(f"/cases/{s['cid']}/reports").json()["reports"] == []
    assert c.get(f"/cases/{s['cid']}/reports/{s['done']}/preview.pptx").status_code == 404
    state = c.get(f"/customers/{s['cust']}/cases/{s['cid']}").json()["dataset_deleted"]
    assert state["keep_decks"] is False and state["completed"] is True
