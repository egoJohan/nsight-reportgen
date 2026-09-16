"""A material's config is read once per request, not four times.

One `preview-chart` read `<material>.config` four times and listed the
customer's templates three. The client that does it is built per request
(`deps.get_client`) and already memoises the case and the material record for
exactly this reason — the config is the same kind of thing and was not.

A config CAN change inside a request: `set_marked_classifier` and the
sensitive-terms acceptance both write it. So the memo is dropped on every
write through this client, which is the only way it changes under a request
that is already running. (Johan, 2026-09-16)
"""
from __future__ import annotations

import pytest

from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.repository_client import RepositoryClient
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.unit

AUTH = AuthContext(token="t")


class CountingStore(InMemoryObjectStore):
    def __init__(self):
        super().__init__()
        self.reads: list[str] = []

    def get(self, auth, path):
        self.reads.append(path)
        return super().get(auth, path)


@pytest.fixture
def client():
    store = CountingStore()
    repo = Repository(store)
    cust = repo.create_customer(AUTH, "Asiakas")
    case = repo.create_case(AUTH, cust.id, "Tutkimus")
    mat = repo.attach_material(AUTH, cust.id, case.id, "s.sav", b"data")
    return RepositoryClient(repo, AUTH), store, mat.id


def _config_reads(store) -> list[str]:
    return [p for p in store.reads if p.endswith(".config")]


def test_reading_it_twice_hits_storage_once(client):
    c, store, mid = client
    c.marked_classifiers(mid)
    store.reads.clear()
    c.marked_classifiers(mid)
    assert not _config_reads(store), (
        f"read the config again inside one request: {_config_reads(store)}")


def test_the_value_is_the_same_both_times(client):
    c, _store, mid = client
    assert c.marked_classifiers(mid) == c.marked_classifiers(mid)


def test_a_write_is_visible_to_the_next_read(client):
    """The memo must not outlive the thing it describes."""
    c, _store, mid = client
    assert c.marked_classifiers(mid) == []
    c.set_marked_classifier(mid, "sukupuoli", True)
    assert c.marked_classifiers(mid) == ["sukupuoli"]
    c.set_marked_classifier(mid, "sukupuoli", False)
    assert c.marked_classifiers(mid) == []


def test_a_second_client_does_not_inherit_the_memo(client):
    """One request's memo is not another's — the client is per request, and a
    stale config across requests is exactly what must not happen."""
    c, store, mid = client
    c.marked_classifiers(mid)
    fresh = RepositoryClient(c.repo, AUTH)
    store.reads.clear()
    fresh.marked_classifiers(mid)
    assert _config_reads(store), "a new request reused the previous one's memo"
