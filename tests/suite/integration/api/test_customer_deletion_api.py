"""Deleting a customer removes every study in it permanently.

"That will just remove all studies permanently" (Johan, 2026-09-24): nothing is
kept read-only, the decks of read-only studies included. Spec:
docs/superpowers/specs/2026-09-24-dataset-deletion-design.md, "Deleting a
customer".
"""
from __future__ import annotations

import json

import pytest

from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import EDIT, Grant, User
from reportbuilder.store import paths as P

pytestmark = pytest.mark.integration

DECK = b"PK\x03\x04 the delivered deck"


def _repo(client):
    return client.app.dependency_overrides[get_repository](), \
        client.app.dependency_overrides[get_auth]()


def _with_consent(client, method, url):
    repo, _auth = _repo(client)
    for _ in range(200):
        resp = client.request(method, url)
        detail = resp.json().get("detail") if resp.status_code == 409 else None
        if isinstance(detail, dict) and detail.get("error") == "consent_required":
            repo.store.approve(detail["request_id"])
            continue
        return resp
    raise AssertionError("consent loop did not converge")


@pytest.fixture
def customer(client_memory, synthetic_bytes):
    """A customer with a live study (a generated report) and a read-only one."""
    c = client_memory
    cust = c.post("/customers", json={"name": "Acme"}).json()["id"]
    repo, auth = _repo(c)
    studies = []
    for name in ("Brändi", "Arkisto"):
        cid = c.post(f"/customers/{cust}/cases", json={"name": name}).json()["id"]
        mid = c.post(f"/cases/{cid}/materials", files={
            "file": ("brandi.sav", synthetic_bytes, "application/octet-stream")}).json()["material_id"]
        rep = repo.save_report(auth, cust, cid, json.dumps({"name": "Delivered"}))
        repo.save_render(auth, cust, cid, rep.id, DECK, repo.render_key(auth, cust, cid, rep.id, mid))
        studies.append(cid)
    assert _with_consent(c, "POST", f"/cases/{studies[1]}/archive").status_code == 200
    return {"cust": cust, "studies": studies}


def test_every_study_goes_with_it_decks_included(client_memory, customer):
    c, s = client_memory, customer
    resp = _with_consent(c, "DELETE", f"/customers/{s['cust']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == s["cust"]
    assert c.get(f"/customers/{s['cust']}").status_code == 404
    assert all(x["id"] != s["cust"] for x in c.get("/customers").json())
    repo, auth = _repo(c)
    assert list(repo.store.list(auth, P.customer_prefix(s["cust"]))) == []


def test_the_grants_and_permission_mode_naming_it_go_too(client_memory, customer):
    c, s = client_memory, customer
    repo, auth = _repo(c)
    other = repo.save_user(auth, User(id="", email="maija@example.com", name="Maija"))
    repo.set_grants(auth, other.id, (Grant(s["cust"], EDIT), Grant("keep-me", EDIT)))
    assert c.put(f"/customers/{s['cust']}/permission-mode",
                 json={"mode": "manual"}).status_code == 200
    assert _with_consent(c, "DELETE", f"/customers/{s['cust']}").status_code == 200
    assert [g.scope for g in repo.get_user(auth, other.id).grants] == ["keep-me"]
    assert s["cust"] not in repo.customer_modes(auth)


def test_only_the_owner_may_delete_it(client_memory, customer):
    c, s = client_memory, customer
    repo, auth = _repo(c)
    editor = repo.save_user(auth, User(id="", email="e@example.com", name="Editor",
                                       grants=(Grant(s["cust"], EDIT),)))
    c.app.dependency_overrides[current_user] = lambda: repo.get_user(auth, editor.id)
    resp = c.delete(f"/customers/{s['cust']}")
    assert resp.status_code == 403
    assert repo.find_customer(auth, s["cust"]) is not None


def test_someone_elses_open_report_blocks_it(client_memory, customer):
    c, s = client_memory, customer
    repo, auth = _repo(c)
    [rep] = repo.list_reports(auth, s["cust"], s["studies"][0])
    repo.lock_report(auth, s["cust"], s["studies"][0], rep.id, "usr-other", "Maija Meikäläinen")
    resp = c.delete(f"/customers/{s['cust']}")
    assert resp.status_code == 409 and "Maija Meikäläinen" in resp.json()["detail"]
    assert repo.find_customer(auth, s["cust"]) is not None


def test_an_unknown_customer_is_404(client_memory):
    assert client_memory.delete("/customers/cus-nope").status_code == 404
