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


def _run_with_consent(repo, call, rounds: int = 12):
    """Run `call`, approving datahive's delete gate as it asks.

    Deleting is consent-gated (floor rule 4) and a removal touches several
    objects, so it raises once per object until each is approved. Production's
    admin bearer already carries that authority; in a memory store we stand in
    for `datahive consent approve`.
    """
    from reportbuilder.store.seam import ConsentRequired

    for _ in range(rounds):
        try:
            return call()
        except ConsentRequired as exc:
            repo.store.approve(exc.request_id)
    raise AssertionError("still asking for consent after several approvals")


def _remove_with_consent(repo, auth, user_id: str):
    from reportbuilder.auth import users

    return _run_with_consent(repo, lambda: users.remove_user(repo, auth, user_id))


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
    """Against `users.remove_user` rather than the route.

    The route is consent-gated in this fixture and always answers 409, so an
    earlier version of this test hid its only real assertion behind
    `if status == 204` and passed with the invalidation removed from all three
    routes. This drives the function every deletion path shares.
    """
    from reportbuilder.auth import users

    _client, repo, auth = store
    them = repo.save_user(auth, User(id="", email="gone@egoiq.com", name="Gone"))
    repo.save_user(auth, User(id="", email="admin@egoiq.com", name="A", is_admin=True))
    session._cache.put("their-session", them)
    assert them.id in _cached_ids()

    _remove_with_consent(repo, auth, them.id)
    assert them.id not in _cached_ids()


def test_revoking_an_accepted_invitation_drops_it_too(store):
    """The second caller of remove_user, and the one that did not invalidate.

    Revoking an accepted invitation removes the user behind it — spec §6 — and
    that path went straight to the store, so the person kept full access until
    the cache expired.
    """
    from reportbuilder.auth import invites

    _client, repo, auth = store
    repo.save_user(auth, User(id="", email="admin@egoiq.com", name="A", is_admin=True))
    invite = repo.create_invite(auth, email="guest@egoiq.com", grants=(),
                                invited_by="A", lifetime_seconds=3600)
    them = repo.save_user(auth, User(id="", email="guest@egoiq.com", name="Guest"))
    repo.mark_invite_accepted(auth, invite.id, them.id)
    session._cache.put("their-session", them)
    assert them.id in _cached_ids()

    _run_with_consent(repo, lambda: invites.revoke_invitation(repo, auth, invite.id))
    assert them.id not in _cached_ids()
