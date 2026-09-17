"""The signing key that turns a session id into a cookie (spec §9): it must
survive a process restart, which means it lives in datahive, not in memory.
"""
import base64

import pytest

from reportbuilder.auth.keys import get_or_create_signing_key
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


def test_a_fresh_hive_gets_a_32_byte_key(repo, auth):
    key = get_or_create_signing_key(repo, auth)
    assert isinstance(key, bytes) and len(key) == 32


def test_the_key_is_stable_across_calls(repo, auth):
    assert get_or_create_signing_key(repo, auth) == get_or_create_signing_key(repo, auth)


def test_the_key_survives_a_fresh_repository_over_the_same_store(repo, auth):
    """Not a new random key per process — read from the store, as spec §9
    requires so that attaching the hive elsewhere brings it along."""
    key = get_or_create_signing_key(repo, auth)
    reopened = Repository(repo.store)
    assert get_or_create_signing_key(reopened, auth) == key


def test_the_stored_value_is_base64_of_the_key(repo, auth):
    key = get_or_create_signing_key(repo, auth)
    stored = repo.get_setting(auth, "security.json")
    assert base64.b64decode(stored["signing_key"]) == key


# ── Read once per process ─────────────────────────────────────────────────────
#
# Every signed-in request asks for this key, and each ask was a hive round trip
# for a value that never changes. The hive serves one request at a time, so on a
# page that opens with fifteen requests that was fifteen extra calls queued in
# front of the ones doing the work. (2026-09-17)

def test_the_key_is_read_from_the_store_once(repo, auth, monkeypatch):
    from reportbuilder.auth import keys
    keys.forget_signing_key()
    key = get_or_create_signing_key(repo, auth)
    reads = []
    real = repo.get_setting
    monkeypatch.setattr(repo, "get_setting",
                        lambda *a, **k: reads.append(a) or real(*a, **k))
    for _ in range(5):
        assert get_or_create_signing_key(repo, auth) == key
    assert reads == []


def test_a_restore_that_replaces_the_key_is_seen_once_forgotten(repo, auth):
    """A backup restore writes a different key into the store. Once the restore
    forgets the cached one, the next request uses the restored key."""
    from reportbuilder.auth import keys
    get_or_create_signing_key(repo, auth)
    restored = bytes(range(32))
    repo.set_setting(auth, "security.json",
                     {"signing_key": base64.b64encode(restored).decode()})
    keys.forget_signing_key()
    assert get_or_create_signing_key(repo, auth) == restored


def test_the_restore_route_forgets_the_key():
    import inspect
    from reportbuilder.api import routes_backup
    assert "forget_signing_key" in inspect.getsource(routes_backup.restore_backup)
