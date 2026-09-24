"""Backing up and restoring the LIVE local hive, both ways round.

Disaster recovery is the one feature nobody exercises until they need it, and
nothing here can be proved against a fake store: what makes a restore hard is
the hive — an object it will not serve, a Postgres plane that has to be
replayed, a passphrase that must be refused. So this runs against the real
local hive, and only when asked:

    NSIGHT_LIVE_HIVE_BACKUP=1 .venv/bin/python -m pytest -q \\
        tests/suite/integration/store/test_live_hive_backup_restore.py

It is opt-in because it WRITES to that hive. Everything it creates it removes
again, and the two tests that replay a plane take their own archive first.

What was found the first time this was run by hand (2026-09-22):

  * nSight's own backup could not be produced at all — `backup.write` stopped
    on `shared/hr/scan.bin`, which the hive refuses to serve because its path
    is marked for pseudonymization and its content type cannot be masked. Now
    it is reported and skipped; `tests/suite/unit/store/test_backup.py` pins
    that behaviour without a hive.
  * `datahive restore --with-data` on the image this hive runs dies taking its
    own mandatory safety archive (`TypeError: str expected, not OptionInfo`).
    egohive's source already carries the fix; the image does not. So the
    hive-level test drives the same two calls the fixed CLI makes.
  * `restore --with-data` replays POSTGRES only. The objects plane is in the
    archive but has to be unpacked by hand with the hive stopped. Rolling the
    object INDEX back is enough to undo a change, because the index lives in
    Postgres — losing the object volume itself is a different recovery.
"""
from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTAINER = os.environ.get("NSIGHT_HIVE_CONTAINER", "egohive-nsight")
STATE = "/var/lib/datahive"
CONFIG = f"{STATE}/datahive.yaml"
BACKUPS = f"{STATE}/backups"


def _docker(*args: str, stdin: str | None = None, user: str = "datahive",
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec", "-u", user]
    if stdin is not None:
        cmd.insert(2, "-i")
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    cmd.append(CONTAINER)
    cmd += list(args)
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=1800)


@pytest.fixture(scope="module")
def live():
    """The live hive, or a skip. Yields (repo, auth)."""
    if os.environ.get("NSIGHT_LIVE_HIVE_BACKUP") != "1":
        pytest.skip("opt-in: set NSIGHT_LIVE_HIVE_BACKUP=1 to run against the live hive")
    if not os.environ.get("NSIGHT_DATAHIVE_URL"):
        pytest.skip("NSIGHT_DATAHIVE_URL is not set")
    from reportbuilder.api.deps_store import build_repository, service_auth

    return build_repository(), service_auth()


@pytest.fixture
def probe(live):
    """A customer of our own, removed again however the test ends."""
    repo, auth = live
    name = f"ZZ backup test {uuid.uuid4().hex[:8]}"
    customer = repo.create_customer(auth, name)
    case = repo.create_case(auth, customer.id, "Probe case")
    repo.save_report(auth, customer.id, case.id, json.dumps(
        {"name": "Probe report", "render_mode": "image", "template_ref": "", "charts": []}))
    try:
        yield customer, case
    finally:
        try:
            repo.delete_customer(auth, customer.id)
        except Exception:  # noqa: BLE001 — a test must not leave the hive dirty, or fail trying
            pass


def _customer_ids(repo, auth) -> set[str]:
    return {c.id for c in repo.list_customers(auth)}


# ── nSight's own backup, against the real hive ──────────────────────────────

def test_a_deleted_customer_comes_back_from_an_nsight_backup(live, probe, tmp_path):
    """The whole point of Settings > Backup: what was lost comes back.

    A restore MERGES — it puts back what is missing and leaves what survived —
    so this deletes the probe and restores it, rather than asserting that the
    store is byte-identical afterwards.
    """
    from reportbuilder.store import backup

    repo, auth = live
    customer, case = probe
    archive = tmp_path / "nsight-backup.zip"
    with archive.open("wb") as fh:
        written = backup.write(repo, auth, fh)
    assert written.object_count > 0
    # An object the hive will not serve is named, not fatal (see the docstring).
    for path in written.unreadable:
        assert isinstance(path, str) and path

    assert repo.delete_customer(auth, customer.id) > 0
    assert customer.id not in _customer_ids(repo, auth), "the probe is gone"

    summary = backup.read(repo, auth, str(archive))

    assert summary.problems == [], summary.problems
    assert customer.id in _customer_ids(repo, auth), "the probe did not come back"
    cases = repo.list_cases(auth, customer.id)
    assert [c.name for c in cases] == ["Probe case"]
    assert repo.list_reports(auth, customer.id, case.id), "its report did not come back"


def test_an_unreadable_object_is_named_rather_than_fatal(live, tmp_path):
    """On this hive `shared/hr/scan.bin` cannot be served. Whatever the hive
    refuses, a backup is still produced and says what it could not read."""
    from reportbuilder.store import backup

    repo, auth = live
    archive = tmp_path / "nsight-backup.zip"
    with archive.open("wb") as fh:
        written = backup.write(repo, auth, fh)

    assert archive.stat().st_size > 0
    import zipfile

    with zipfile.ZipFile(archive) as z:
        manifest = json.loads(z.read("manifest.json"))
    assert manifest["unreadable"] == sorted(written.unreadable)


# ── the hive's own archive ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def passphrase() -> str:
    pw = os.environ.get("NSIGHT_HIVE_BACKUP_PASSPHRASE")
    if not pw:
        pytest.skip("set NSIGHT_HIVE_BACKUP_PASSPHRASE to exercise the hive's own archive")
    return pw


def _take_hive_backup(name: str, passphrase: str) -> str:
    out = f"{BACKUPS}/{name}"
    done = _docker("datahive", "backup", out, "--config", CONFIG, "--state-dir", STATE,
                   "--passphrase-env", "DHBAK_PASS",
                   env={"DHBAK_PASS": passphrase, "PGPASSFILE": f"{STATE}/.pgpass"})
    assert "backup written" in done.stdout, done.stdout + done.stderr
    return out


def test_a_hive_archive_carries_every_plane_that_makes_it_a_recovery_point(passphrase):
    """`objects` and `pg` are REQUIRED planes: the object store holds every SAV,
    template and report, and Postgres holds the index that finds them."""
    archive = _take_hive_backup(f"test-{uuid.uuid4().hex[:8]}.dhbak", passphrase)
    try:
        done = _docker("datahive", "backup-verify", archive, "--config", CONFIG,
                       "--state-dir", STATE, "--passphrase-env", "DHBAK_PASS",
                       env={"DHBAK_PASS": passphrase})
        assert "OK — archive decrypts" in done.stdout, done.stdout + done.stderr
        for plane in ("objects", "pg"):
            assert f"{plane}: present" in done.stdout, done.stdout
    finally:
        _docker("rm", "-f", archive, user="datahive")


def test_a_wrong_passphrase_opens_nothing(passphrase):
    """The archive is a secret in one file. A wrong passphrase must fail, and
    fail before anything is applied."""
    archive = _take_hive_backup(f"test-{uuid.uuid4().hex[:8]}.dhbak", passphrase)
    try:
        done = _docker("datahive", "backup-verify", archive, "--config", CONFIG,
                       "--state-dir", STATE, "--passphrase-env", "DHBAK_PASS",
                       env={"DHBAK_PASS": "definitely-not-the-passphrase"})
        assert done.returncode != 0, "a wrong passphrase was accepted"
        assert "wrong passphrase or tampered backup" in (done.stdout + done.stderr)
    finally:
        _docker("rm", "-f", archive, user="datahive")


def test_replaying_the_postgres_plane_undoes_what_came_after_it(live, passphrase, tmp_path):
    """The hive-level round trip: archive, change, replay, and the change is
    gone. Postgres holds the object index, so rolling it back rolls back what
    nSight can see. Takes its own archive first, so the test is reversible."""
    repo, auth = live
    archive = _take_hive_backup(f"test-{uuid.uuid4().hex[:8]}.dhbak", passphrase)
    marker = repo.create_customer(auth, f"ZZ hive restore {uuid.uuid4().hex[:8]}")
    assert marker.id in _customer_ids(repo, auth)

    replay = Path(__file__).with_name("_pg_replay.py").read_text(encoding="utf-8")
    done = _docker("sh", "-c",
                   f"cat > /tmp/_pg_replay.py <<'PY'\n{replay}\nPY\n"
                   f"/opt/datahive/.venv/bin/python /tmp/_pg_replay.py "
                   f"{archive} {CONFIG} {STATE}",
                   env={"DHBAK_PASS": passphrase, "PGPASSFILE": f"{STATE}/.pgpass"})
    try:
        assert "postgres restored" in done.stdout, done.stdout + done.stderr
        assert marker.id not in _customer_ids(repo, auth), (
            "the customer created after the archive survived the replay")
    finally:
        if marker.id in _customer_ids(repo, auth):
            repo.delete_customer(auth, marker.id)
        _docker("rm", "-f", archive, user="datahive")
