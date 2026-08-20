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
