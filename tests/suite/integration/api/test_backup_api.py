"""GET /admin/backup and POST /admin/restore — the Settings > Backup screen.

Both are admin-only: a backup hands over every password hash and the session
signing key, and a restore rewrites the store.
"""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store import backup
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.integration


@pytest.fixture
def store():
    return InMemoryObjectStore()


def _client(store, *, admin=True):
    repo = Repository(store)
    auth = AuthContext(token="user-1")
    actor = User(id="usr-1", email="a@example.com", name="A", is_admin=admin,
                 grants=tuple(Grant(c.id, "edit") for c in repo.list_customers(auth)))
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = lambda: actor
    return TestClient(app), repo, auth


class TestTheAdminGate:
    def test_a_non_admin_may_not_download_a_backup(self, store):
        client, _, _ = _client(store, admin=False)
        assert client.get("/admin/backup").status_code == 403

    def test_a_non_admin_may_not_restore(self, store):
        client, _, _ = _client(store, admin=False)
        r = client.post("/admin/restore",
                        files={"file": ("b.zip", b"whatever", "application/zip")})
        assert r.status_code == 403


class TestDownload:
    def test_the_response_is_a_zip_named_for_the_day(self, store):
        client, repo, auth = _client(store)
        repo.create_customer(auth, "Attendo", owner_id="usr-1")

        r = client.get("/admin/backup")

        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        assert "nsight-backup-" in r.headers["content-disposition"]
        assert zipfile.ZipFile(io.BytesIO(r.content)).read("manifest.json")

    def test_it_holds_the_customers_that_exist(self, store):
        client, repo, auth = _client(store)
        repo.create_customer(auth, "Attendo", owner_id="usr-1")

        z = zipfile.ZipFile(io.BytesIO(client.get("/admin/backup").content))
        manifest = json.loads(z.read("manifest.json"))
        names = [json.loads(z.read(e["member"])).get("name")
                 for e in manifest["objects"]
                 if "nsight:customer" in e["labels"]]
        assert names == ["Attendo"]


class TestUploadAndRestore:
    def test_a_downloaded_backup_restores_into_an_empty_hive(self, store):
        client, repo, auth = _client(store)
        c = repo.create_customer(auth, "Attendo", owner_id="usr-1")
        repo.create_case(auth, c.id, "Bränditutkimus")
        blob = client.get("/admin/backup").content

        fresh_store = InMemoryObjectStore()
        fresh_client, fresh_repo, fresh_auth = _client(fresh_store)
        r = fresh_client.post(
            "/admin/restore",
            files={"file": ("nsight-backup.zip", blob, "application/zip")})

        assert r.status_code == 200, r.text
        assert r.json()["restored"] > 0
        assert r.json()["problems"] == []
        assert [x.name for x in fresh_repo.list_customers(fresh_auth)] == ["Attendo"]
        assert [x.name for x in fresh_repo.list_cases(fresh_auth, c.id)] == [
            "Bränditutkimus"]

    def test_a_file_that_is_not_a_backup_is_a_400_not_a_500(self, store):
        client, _, _ = _client(store)
        r = client.post("/admin/restore",
                        files={"file": ("holiday.jpg", b"\xff\xd8\xff not a zip",
                                        "image/jpeg")})
        assert r.status_code == 400
        assert "backup" in r.json()["detail"].lower()

    def test_a_zip_without_a_manifest_is_refused(self, store):
        client, _, _ = _client(store)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("notes.txt", b"hello")

        r = client.post("/admin/restore",
                        files={"file": ("b.zip", buf.getvalue(), "application/zip")})
        assert r.status_code == 400
        assert "manifest" in r.json()["detail"].lower()

    def test_restoring_flushes_the_session_cache(self, store, monkeypatch):
        """Users, grants and the signing key have all just been replaced, so
        every cached identity describes a store that no longer exists."""
        from reportbuilder.auth import session

        client, repo, auth = _client(store)
        blob = client.get("/admin/backup").content
        called = []
        monkeypatch.setattr(session, "forget_all", lambda: called.append(True))

        client.post("/admin/restore",
                    files={"file": ("b.zip", blob, "application/zip")})

        assert called == [True]

    def test_a_backup_of_a_backup_is_still_restorable(self, store):
        """Round-tripping twice catches a format that only survives one pass —
        e.g. one that rewrites report sidecars on the way out."""
        client, repo, auth = _client(store)
        c = repo.create_customer(auth, "Attendo", owner_id="usr-1")
        k = repo.create_case(auth, c.id, "Bränditutkimus")
        rep = repo.save_report(auth, c.id, k.id, json.dumps({"name": "Q1", "charts": []}))
        repo.save_render(auth, c.id, k.id, rep.id, b"PPTX", key="k1")

        once = client.get("/admin/backup").content
        mid_store = InMemoryObjectStore()
        mid_client, mid_repo, mid_auth = _client(mid_store)
        mid_client.post("/admin/restore",
                        files={"file": ("b.zip", once, "application/zip")})
        twice = mid_client.get("/admin/backup").content

        end_store = InMemoryObjectStore()
        end_client, end_repo, end_auth = _client(end_store)
        r = end_client.post("/admin/restore",
                            files={"file": ("b.zip", twice, "application/zip")})

        assert r.status_code == 200, r.text
        assert [x.name for x in end_repo.list_customers(end_auth)] == ["Attendo"]
        assert end_repo.list_reports(end_auth, c.id, k.id)[0].rendered is False


class TestFormat:
    def test_the_zip_explains_itself_to_a_human(self, store):
        client, _, _ = _client(store)
        z = zipfile.ZipFile(io.BytesIO(client.get("/admin/backup").content))
        readme = z.read("README.txt").decode("utf-8")
        assert "password" in readme.lower()   # says plainly that it is a secret
        assert "manifest.json" in readme

    def test_the_manifest_names_the_format_and_version(self, store):
        client, _, _ = _client(store)
        z = zipfile.ZipFile(io.BytesIO(client.get("/admin/backup").content))
        m = json.loads(z.read("manifest.json"))
        assert m["format"] == backup.FORMAT
        assert m["version"] == backup.VERSION


class TestItLeavesARecord:
    """Who took a copy of everything, and when.

    These two operations are the most sensitive the app has, and neither left
    any trace that it had happened. That is the first question anyone asks
    after an incident, and the answer was nowhere. A log line is not a full
    audit trail; it is the difference between a question that can be answered
    and one that cannot.
    """

    def test_downloading_a_backup_names_the_admin(self, store, caplog):
        client, _, _ = _client(store)
        with caplog.at_level("WARNING", logger="reportbuilder.api.routes_backup"):
            assert client.get("/admin/backup").status_code == 200
        logged = " ".join(r.getMessage() for r in caplog.records)
        assert "a@example.com" in logged and "usr-1" in logged
        assert "password hashes" in logged, "say what was handed over, not just that it was"

    def test_restoring_names_the_admin_and_what_it_did(self, store, caplog):
        client, _, _ = _client(store)
        archive = client.get("/admin/backup").content
        caplog.clear()
        with caplog.at_level("WARNING", logger="reportbuilder.api.routes_backup"):
            r = client.post("/admin/restore",
                            files={"file": ("b.zip", archive, "application/zip")})
        assert r.status_code == 200, r.text
        logged = " ".join(rec.getMessage() for rec in caplog.records)
        assert "a@example.com" in logged
        assert "restored" in logged
