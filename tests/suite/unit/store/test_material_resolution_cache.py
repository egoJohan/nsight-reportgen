"""Resolving a flat material id must not list the tenant every time.

The cache maps id -> (customer, case). It deliberately does NOT cache the
permission answer: the location of a material is the same fact for everyone,
who may see it is not, and caching the second would be the bug this whole plan
exists to prevent.
"""
import pytest

from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, ConsentRequired


def approve_all(store, fn):
    """Run *fn*, approving each consent request until it completes.

    datahive gates destructive operations behind an approval, and the
    in-memory seam mirrors that, so any test that deletes something goes
    through here (see tests/suite/unit/store/test_repository.py).
    """
    for _ in range(50):
        try:
            return fn()
        except ConsentRequired as exc:
            store.approve(exc.request_id)
    raise AssertionError("consent loop did not converge")


class CountingStore(InMemoryObjectStore):
    """An object store that remembers how often it was asked to list.

    InMemoryObjectStore is a dataclass whose fields all have defaults, so a
    plain subclass calling `super().__init__()` gets a fresh, empty store.
    """

    def __init__(self):
        super().__init__()
        self.lists = 0

    def list(self, auth, path_prefix="", labels=()):
        self.lists += 1
        return super().list(auth, path_prefix, labels=labels)


@pytest.fixture
def repo():
    return Repository(CountingStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def material(repo, auth):
    c = repo.create_customer(auth, "Attendo")
    k = repo.create_case(auth, c.id, "Study")
    return repo.attach_material(auth, c.id, k.id, "a.sav", b"SAV")


def test_the_second_lookup_does_not_list_again(repo, auth, material):
    repo.find_material(auth, material.id)
    repo.store.lists = 0
    got = repo.find_material(auth, material.id)
    assert got is not None and got.case_id == material.case_id
    assert repo.store.lists == 0


def test_a_cached_material_is_still_permission_checked(repo, auth, material):
    """The location is cached; the ANSWER is not. A user warmed the cache;
    another user with no grant must still get None."""
    repo.find_material(auth, material.id)
    stranger = User(id="u", email="a@b.c", grants=(Grant("cust-other", "edit"),))
    assert repo.find_material(auth, material.id, user=stranger) is None


def test_an_unknown_id_is_not_cached_as_missing(repo, auth):
    """Caching a negative would break the ordinary case of looking for a
    material a moment before it is attached."""
    assert repo.find_material(auth, "mat-later") is None
    c = repo.create_customer(auth, "A")
    k = repo.create_case(auth, c.id, "S")
    m = repo.attach_material(auth, c.id, k.id, "a.sav", b"SAV")
    assert repo.find_material(auth, m.id) is not None


def test_deleting_a_material_evicts_it(repo, auth, material):
    repo.find_material(auth, material.id)
    approve_all(repo.store, lambda: repo.delete_material(
        auth, material.customer_id, material.case_id, material.id))
    assert repo.find_material(auth, material.id) is None


def test_attaching_seeds_the_cache(repo, auth):
    """The id is handed back by attach_material, so its location is known
    without any listing at all."""
    c = repo.create_customer(auth, "A")
    k = repo.create_case(auth, c.id, "S")
    m = repo.attach_material(auth, c.id, k.id, "a.sav", b"SAV")
    repo.store.lists = 0
    assert repo.find_material(auth, m.id) is not None
    assert repo.store.lists == 0
