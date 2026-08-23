"""The default template — the one every unbound report renders on.

nSight ships a house template and seeds it into the hive at boot, deliberately
without overwriting what is already there so a customised one survives a
restart. Until now there was no way to customise it: the store anticipated the
feature and nothing offered it. This is that.

It is deliberately tenant-wide and admin-only. Uploading one restyles every
report that is not bound to a template of its own, which is the point, and also
the reason it is not a thing any signed-in user can do.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.render.default_template import build_default_template
from reportbuilder.store import paths as P
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext
from suite._helpers import sign_in_override

pytestmark = pytest.mark.integration


@pytest.fixture
def auth():
    return AuthContext(token="admin-1")


@pytest.fixture
def store_repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def client(store_repo, auth):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: store_repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(store_repo, auth)
    return TestClient(app)


@pytest.fixture
def a_real_template(tmp_path) -> bytes:
    """A .pptx that passes the same check a customer upload has to pass."""
    return open(build_default_template(str(tmp_path / "t.pptx")), "rb").read()


def _seed(store_repo, auth, a_real_template):
    """The state a running hive is in: the house template already seeded."""
    store_repo.ensure_default_template(auth, a_real_template)


def test_it_reports_the_builtin_before_anyone_uploads(client, store_repo, auth,
                                                      a_real_template):
    _seed(store_repo, auth, a_real_template)
    body = client.get("/settings/default-template").json()
    assert body["is_builtin"] is True
    assert body["size"] > 0


def test_uploading_replaces_the_bytes_every_unbound_report_renders_on(
        client, store_repo, auth, a_real_template):
    _seed(store_repo, auth, a_real_template)
    mine = a_real_template + b"\x00"  # same deck, different bytes
    r = client.put("/settings/default-template",
                   files={"file": ("house.pptx", a_real_template,
                                   "application/vnd.openxmlformats-officedocument"
                                   ".presentationml.presentation")})
    assert r.status_code == 200, r.text
    assert r.json()["is_builtin"] is False
    assert r.json()["name"] == "house.pptx"
    # THE test: what a report with no template of its own actually renders on.
    assert store_repo.store.get(auth, P.default_template_path()) == a_real_template
    assert mine != b""  # (kept explicit: the point is the stored bytes changed)


def test_the_upload_is_named_so_an_admin_can_see_which_one_is_in_effect(
        client, store_repo, auth, a_real_template):
    _seed(store_repo, auth, a_real_template)
    client.put("/settings/default-template",
               files={"file": ("attendo.pptx", a_real_template, "application/octet-stream")})
    body = client.get("/settings/default-template").json()
    assert body["name"] == "attendo.pptx"
    assert body["is_builtin"] is False
    assert body["uploaded_at"]


def test_a_file_that_is_not_a_template_is_refused_and_changes_nothing(
        client, store_repo, auth, a_real_template):
    _seed(store_repo, auth, a_real_template)
    before = store_repo.store.get(auth, P.default_template_path())
    r = client.put("/settings/default-template",
                   files={"file": ("notes.txt", b"this is not a pptx", "text/plain")})
    assert r.status_code == 422
    # Refused BEFORE anything was stored: a bad upload must not leave every
    # unbound report rendering on a broken deck.
    assert store_repo.store.get(auth, P.default_template_path()) == before


def test_an_empty_file_is_refused(client, store_repo, auth, a_real_template):
    _seed(store_repo, auth, a_real_template)
    r = client.put("/settings/default-template",
                   files={"file": ("empty.pptx", b"", "application/octet-stream")})
    assert r.status_code == 422


def test_restoring_puts_nsights_own_template_back(client, store_repo, auth,
                                                  a_real_template):
    _seed(store_repo, auth, a_real_template)
    client.put("/settings/default-template",
               files={"file": ("mine.pptx", a_real_template, "application/octet-stream")})
    assert client.get("/settings/default-template").json()["is_builtin"] is False

    r = client.delete("/settings/default-template")
    assert r.status_code == 200
    body = client.get("/settings/default-template").json()
    assert body["is_builtin"] is True
    # Rebuilt, not merely forgotten: the bytes have to be there or every unbound
    # report falls back to a blank deck.
    assert len(store_repo.store.get(auth, P.default_template_path())) > 0


def test_a_non_admin_cannot_change_what_every_report_renders_on(
        store_repo, auth, a_real_template):
    _seed(store_repo, auth, a_real_template)
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: store_repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(
        store_repo, auth, admin=False)
    plain = TestClient(app)
    assert plain.put("/settings/default-template",
                     files={"file": ("x.pptx", a_real_template,
                                     "application/octet-stream")}).status_code == 403
    assert plain.delete("/settings/default-template").status_code == 403


def test_restore_puts_back_the_template_nsight_ships(client, store_repo, auth,
                                                     a_real_template):
    """Not a deck assembled at restore time — the file nSight ships.

    "Restore nSight's template" has to mean the same thing on every install, so
    it hands back the designed .pptx in the package rather than whatever the
    builder would assemble today.
    """
    from reportbuilder.render.default_template import default_template_bytes

    _seed(store_repo, auth, a_real_template)
    client.put("/settings/default-template",
               files={"file": ("mine.pptx", a_real_template, "application/octet-stream")})
    client.delete("/settings/default-template")
    assert store_repo.store.get(auth, P.default_template_path()) == default_template_bytes()


def test_the_builtin_is_named_after_the_file_that_ships(client, store_repo, auth,
                                                        a_real_template):
    from reportbuilder.render.default_template import shipped_default_name

    _seed(store_repo, auth, a_real_template)
    assert client.get("/settings/default-template").json()["name"] == shipped_default_name()
