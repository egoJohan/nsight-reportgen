"""Taking access away has to bite now, not in thirty seconds.

Identity is cached per session so that every request does not re-read a user
and their grants. The cache was invalidated when a grant was ADDED — so the
customer you just created appears in your own sidebar at once — and not when
one was taken away. An admin removes somebody's access, is told it is done, and
that person keeps reading the customer until the TTL runs out.

Convenience was invalidated; the security direction was not.
"""
import pytest

from reportbuilder.auth import session
from reportbuilder.auth.permissions import Grant, User

pytestmark = pytest.mark.integration


@pytest.fixture
def store(client_memory):
    from reportbuilder.api.deps_store import get_auth, get_repository

    overrides = client_memory.app.dependency_overrides
    return client_memory, overrides[get_repository](), overrides[get_auth]()


def _cached_ids() -> set[str]:
    return {v.id for v, _at, _ttl in session._cache._entries.values() if v is not None}


def test_removing_a_grant_drops_the_cached_identity(store):
    client, repo, auth = store
    cid = client.post("/customers", json={"name": "Asiakas"}).json()["id"]
    them = repo.save_user(auth, User(id="", email="maija@egoiq.com", name="Maija",
                                     grants=(Grant(cid, "edit"),)))
    # As a live session would have it.
    session._cache.put("their-session", them)
    assert them.id in _cached_ids()

    r = client.put(f"/users/{them.id}/grants", json={"grants": []})
    assert r.status_code == 200, r.text
    assert them.id not in _cached_ids(), "they can still read it for another TTL"


def test_demoting_an_admin_drops_it_too(store):
    """Admin is the grant that opens every route there is."""
    client, repo, auth = store
    them = repo.save_user(auth, User(id="", email="a@egoiq.com", name="A",
                                     is_admin=True))
    # A second admin, so the demotion is not refused as the last one.
    repo.save_user(auth, User(id="", email="b@egoiq.com", name="B", is_admin=True))
    session._cache.put("their-session", them)

    r = client.patch(f"/users/{them.id}", json={"is_admin": False})
    assert r.status_code == 200, r.text
    assert them.id not in _cached_ids()


def test_deleting_a_user_drops_it(store):
    client, repo, auth = store
    them = repo.save_user(auth, User(id="", email="gone@egoiq.com", name="Gone"))
    session._cache.put("their-session", them)

    r = client.delete(f"/users/{them.id}")
    assert r.status_code in (204, 409), r.text
    if r.status_code == 204:
        assert them.id not in _cached_ids()
