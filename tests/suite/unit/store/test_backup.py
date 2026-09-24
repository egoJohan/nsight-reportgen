"""Backup and restore: does the zip hold everything that matters, and does
restoring it into an empty store bring the app back?
"""
import io
import json
import zipfile

import pytest

from reportbuilder.store import backup
from reportbuilder.store import paths as P
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


def _stored_password_hash(repo, auth, user_id: str):
    """Read a legacy hash straight from the store — there is no accessor left."""
    from reportbuilder.store import paths as P
    from reportbuilder.store.seam import NotFound

    try:
        return repo._read_json(auth, P.user_password_path(user_id)).get("hash")
    except (NotFound, ValueError):
        return None


def _legacy_password_hash(repo, auth, user_id: str, value: str = "$argon2id$legacy") -> None:
    """Write a password hash the way a pre-SSO store holds one.

    `set_password` is gone — accounts come from an invitation and people sign
    in with Google or Microsoft — but a store written before that change can
    still hold a hash, and the code that sweeps one on delete (and the backup
    that carries it) has to keep working. Written through the store directly
    because there is deliberately no API left that creates one.
    """
    from reportbuilder.store import paths as P

    repo._write_json(auth, P.user_password_path(user_id), {"hash": value},
                     [P.LABEL_PASSWORD])



@pytest.fixture
def auth():
    return AuthContext(token="user-1")


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


def _populated(repo, auth):
    """A store with one of most things: customer, study, SAV, report, deck,
    template, user, password, grants, settings."""
    from reportbuilder.auth.permissions import Grant, User

    c = repo.create_customer(auth, "Attendo", owner_id="usr-1")
    k = repo.create_case(auth, c.id, "Bränditutkimus")
    repo.attach_material(auth, c.id, k.id, "wave1.sav", b"SAV BYTES")
    r = repo.save_report(auth, c.id, k.id, json.dumps({"name": "Q1", "charts": []}))
    repo.save_render(auth, c.id, k.id, r.id, b"PPTX BYTES", key="k1")
    repo.upload_template(auth, c.id, "Brand.pptx", b"TEMPLATE BYTES")
    repo.save_user(auth, User(id="usr-1", email="a@example.com", name="A",
                              is_admin=True, grants=(Grant(c.id, "edit"),)))
    _legacy_password_hash(repo, auth, "usr-1")
    repo.set_setting(auth, "access.json", {"allowed_domains": ["egoiq.com"]})
    return c, k, r


class TestWhatIsInIt:
    def test_every_object_is_carried_with_its_path_and_labels(self, repo, auth):
        _populated(repo, auth)
        stored = {i.path: i for i in repo.store.list(auth, "")
                  if not backup.EXCLUDED_LABELS.intersection(i.labels)}

        z = zipfile.ZipFile(io.BytesIO(backup.to_bytes(repo, auth)))
        manifest = json.loads(z.read("manifest.json"))

        assert {e["path"] for e in manifest["objects"]} == set(stored)
        for e in manifest["objects"]:
            assert set(e["labels"]) == set(stored[e["path"]].labels)

    def test_the_uploaded_sav_bytes_are_in_there(self, repo, auth):
        c, k, _ = _populated(repo, auth)
        mats = repo.list_materials(auth, c.id, k.id)

        z = zipfile.ZipFile(io.BytesIO(backup.to_bytes(repo, auth)))
        manifest = json.loads(z.read("manifest.json"))
        entry = next(e for e in manifest["objects"]
                     if e["path"] == P.material_path(c.id, k.id, mats[0].id))
        assert z.read(entry["member"]) == b"SAV BYTES"

    def test_rendered_decks_are_left_out(self, repo, auth):
        c, k, r = _populated(repo, auth)

        z = zipfile.ZipFile(io.BytesIO(backup.to_bytes(repo, auth)))
        manifest = json.loads(z.read("manifest.json"))
        paths = {e["path"] for e in manifest["objects"]}
        assert P.report_render_path(c.id, k.id, r.id) not in paths
        assert not any(P.LABEL_RENDER in e["labels"] for e in manifest["objects"])

    def test_sessions_are_left_out(self, repo, auth):
        from reportbuilder.auth import session
        from reportbuilder.auth.permissions import User

        u = repo.save_user(auth, User(id="", email="s@example.com", name="S"))
        session.create(repo, auth, u.id)

        z = zipfile.ZipFile(io.BytesIO(backup.to_bytes(repo, auth)))
        manifest = json.loads(z.read("manifest.json"))
        assert not any(P.LABEL_SESSION in e["labels"] for e in manifest["objects"])

    def test_password_hashes_and_the_signing_key_are_included(self, repo, auth):
        """Deliberate: a restore has to leave people able to sign in."""
        from reportbuilder.auth import keys

        _populated(repo, auth)
        keys.get_or_create_signing_key(repo, auth)

        z = zipfile.ZipFile(io.BytesIO(backup.to_bytes(repo, auth)))
        manifest = json.loads(z.read("manifest.json"))
        labels = [set(e["labels"]) for e in manifest["objects"]]
        assert any(P.LABEL_PASSWORD in ls for ls in labels)
        assert any(P.LABEL_SETTINGS in ls for ls in labels)

    def test_a_report_does_not_claim_a_deck_the_backup_does_not_hold(
        self, repo, auth
    ):
        """`rendered` is read off `render_key`. Carrying the stamp without the
        bytes would restore reports that call themselves generated and 404 on
        download."""
        c, k, r = _populated(repo, auth)
        assert repo.list_reports(auth, c.id, k.id)[0].rendered  # true before

        z = zipfile.ZipFile(io.BytesIO(backup.to_bytes(repo, auth)))
        manifest = json.loads(z.read("manifest.json"))
        entry = next(e for e in manifest["objects"]
                     if e["path"] == P.report_meta_path(c.id, k.id, r.id))
        meta = json.loads(z.read(entry["member"]))
        assert "render_key" not in meta
        assert "rendered_at" not in meta

    def test_members_are_numbered_not_named_after_store_paths(self, repo, auth):
        _populated(repo, auth)
        z = zipfile.ZipFile(io.BytesIO(backup.to_bytes(repo, auth)))
        members = [n for n in z.namelist() if n.startswith("objects/")]
        assert members and all(n.removeprefix("objects/").isdigit() for n in members)


class TestRestore:
    def test_an_empty_store_comes_back(self, repo, auth):
        c, k, r = _populated(repo, auth)
        data = backup.to_bytes(repo, auth)

        fresh = Repository(InMemoryObjectStore())
        summary = backup.read(fresh, auth, io.BytesIO(data))

        assert summary.problems == []
        assert [x.name for x in fresh.list_customers(auth)] == ["Attendo"]
        assert [x.name for x in fresh.list_cases(auth, c.id)] == ["Bränditutkimus"]
        assert [x.email for x in fresh.list_users(auth)] == ["a@example.com"]
        assert _stored_password_hash(fresh, auth, "usr-1") == "$argon2id$legacy"
        assert fresh.get_setting(auth, "access.json") == {
            "allowed_domains": ["egoiq.com"]}

    def test_the_sav_survives_the_round_trip(self, repo, auth):
        c, k, _ = _populated(repo, auth)
        mid = repo.list_materials(auth, c.id, k.id)[0].id
        data = backup.to_bytes(repo, auth)

        fresh = Repository(InMemoryObjectStore())
        backup.read(fresh, auth, io.BytesIO(data))
        assert fresh.get_material(auth, c.id, k.id, mid) == b"SAV BYTES"

    def test_a_restored_report_is_a_draft_again(self, repo, auth):
        c, k, r = _populated(repo, auth)
        data = backup.to_bytes(repo, auth)

        fresh = Repository(InMemoryObjectStore())
        backup.read(fresh, auth, io.BytesIO(data))
        restored = fresh.list_reports(auth, c.id, k.id)[0]
        assert restored.rendered is False
        # And not merely "not current": the archive holds no deck at all, so it
        # must not claim one was ever produced either. `has_render` is what a
        # view-only client is shown by, and it SURVIVES a save by design — so a
        # sidecar carrying it with no render_key beside it is the ordinary case,
        # and it went through the stripper untouched.
        assert restored.has_render is False
        assert fresh.load_render(auth, c.id, k.id, r.id, key="k1") is None

    def test_restoring_overwrites_what_is_there_and_keeps_what_is_not(
        self, repo, auth
    ):
        c, _, _ = _populated(repo, auth)
        data = backup.to_bytes(repo, auth)
        repo.rename_customer(auth, c.id, "Renamed after the backup")
        later = repo.create_customer(auth, "Made after the backup")

        summary = backup.read(repo, auth, io.BytesIO(data))

        assert summary.problems == []
        names = {x.name for x in repo.list_customers(auth)}
        assert names == {"Attendo", "Made after the backup"}
        assert repo.get_customer(auth, later.id).name == "Made after the backup"


class TestRefusals:
    def test_a_zip_that_is_not_a_backup_is_refused(self, repo, auth):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("holiday.jpg", b"not a backup")

        with pytest.raises(backup.BadBackup, match="not an nSight backup"):
            backup.read(repo, auth, io.BytesIO(buf.getvalue()))

    def test_a_future_format_version_is_refused(self, repo, auth):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("manifest.json", json.dumps(
                {"format": backup.FORMAT, "version": 99, "objects": []}))

        with pytest.raises(backup.BadBackup, match="version"):
            backup.read(repo, auth, io.BytesIO(buf.getvalue()))

    def test_a_path_that_climbs_out_of_the_store_is_refused(self, repo, auth):
        """The manifest decides where bytes land, so it is checked, not
        trusted."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("objects/000001", b"evil")
            z.writestr("manifest.json", json.dumps({
                "format": backup.FORMAT, "version": backup.VERSION,
                "objects": [{"member": "objects/000001",
                             "path": "../../etc/passwd",
                             "content_type": "text/plain", "labels": []}]}))

        summary = backup.read(repo, auth, io.BytesIO(buf.getvalue()))
        assert summary.restored == 0
        assert any("suspicious" in p for p in summary.problems)

    def test_one_unreadable_member_does_not_abandon_the_rest(self, repo, auth):
        _populated(repo, auth)
        data = backup.to_bytes(repo, auth)
        z_in = zipfile.ZipFile(io.BytesIO(data))
        manifest = json.loads(z_in.read("manifest.json"))
        manifest["objects"].append({"member": "objects/999999", "path": "gone",
                                    "content_type": "text/plain", "labels": []})

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            for name in z_in.namelist():
                if name != "manifest.json":
                    z.writestr(name, z_in.read(name))
            z.writestr("manifest.json", json.dumps(manifest))

        fresh = Repository(InMemoryObjectStore())
        summary = backup.read(fresh, auth, io.BytesIO(out.getvalue()))

        assert summary.restored == len(manifest["objects"]) - 1
        assert any("Missing from the zip" in p for p in summary.problems)
        assert [x.name for x in fresh.list_customers(auth)] == ["Attendo"]


# ── an object the store will not serve ──────────────────────────────────────
#
# A hive refuses to hand over an object whose path is marked for
# pseudonymization when its content type cannot be masked. `write` caught only
# `NotFound` — the snapshot race — so one such object ended the whole backup
# with an error about masking, and Settings > Backup produced nothing at all.
# Found on the local hive, where a 400-byte fixture (`shared/hr/scan.bin`) made
# every backup impossible. One object nobody can read is not a reason to have
# no archive; it is a reason to say which object. (2026-09-22)

class _RefusingStore(InMemoryObjectStore):
    """A store that will not serve one path."""

    def __init__(self, refuse: str):
        super().__init__()
        self._refuse = refuse

    def get(self, auth, path):
        from reportbuilder.store.seam import AccessDenied

        if path == self._refuse:
            raise AccessDenied(f"{path}: cannot_mask_this_object")
        return super().get(auth, path)


def _one_customer(repo, auth, name="Asiakas"):
    return repo.create_customer(auth, name)


def test_an_unreadable_object_does_not_stop_the_backup():
    auth = AuthContext(token="t")
    repo = Repository(_RefusingStore("shared/hr/scan.bin"))
    _one_customer(repo, auth)
    repo.store.put(auth, "shared/hr/scan.bin", b"x" * 400, "application/octet-stream")
    repo.store.put(auth, "shared/public/note", b"readable", "text/plain")

    buf = io.BytesIO()
    summary = backup.write(repo, auth, buf)

    assert summary.unreadable == ["shared/hr/scan.bin"]
    assert summary.object_count >= 2, "everything else is still in the archive"
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
        paths = {e["path"] for e in json.loads(z.read("manifest.json"))["objects"]}
    assert "shared/public/note" in paths
    assert "shared/hr/scan.bin" not in paths


def test_the_archive_says_which_objects_it_could_not_read():
    """A year from now, whoever restores this must be able to tell a complete
    archive from one with a hole in it."""
    auth = AuthContext(token="t")
    repo = Repository(_RefusingStore("shared/hr/scan.bin"))
    _one_customer(repo, auth)
    repo.store.put(auth, "shared/hr/scan.bin", b"x" * 400, "application/octet-stream")

    buf = io.BytesIO()
    backup.write(repo, auth, buf)

    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
        manifest = json.loads(z.read("manifest.json"))
    assert manifest["unreadable"] == ["shared/hr/scan.bin"]


def test_what_was_refused_restores_from_an_older_archive():
    """The hole is in this archive, not in the store: an object that was
    readable when an earlier backup was taken still restores from that one."""
    auth = AuthContext(token="t")
    repo = Repository(InMemoryObjectStore())
    _one_customer(repo, auth)
    repo.store.put(auth, "shared/hr/scan.bin", b"x" * 400, "application/octet-stream")
    good = io.BytesIO()
    backup.write(repo, auth, good)

    fresh = Repository(InMemoryObjectStore())
    summary = backup.read(fresh, auth, io.BytesIO(good.getvalue()))

    assert summary.problems == []
    assert fresh.store.get(auth, "shared/hr/scan.bin") == b"x" * 400
