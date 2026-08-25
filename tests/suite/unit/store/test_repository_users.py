"""Users and their grants, stored in datahive.

Per spec §2 there is no local user list: attaching a different hive must bring
the users with it.
"""
import pytest

from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, ConsentRequired


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



def approve_all(store, fn):
    """Run *fn*, approving each consent request until it completes.

    datahive gates destructive operations behind an approval, and the in-memory
    seam mirrors that, so any test that deletes something goes through here.
    """
    for _ in range(50):
        try:
            return fn()
        except ConsentRequired as exc:
            store.approve(exc.request_id)
    raise AssertionError("consent loop did not converge")


@pytest.fixture
def store():
    return InMemoryObjectStore()


@pytest.fixture
def repo(store):
    return Repository(store)


@pytest.fixture
def auth():
    return AuthContext(token="t")


def test_a_saved_user_comes_back_whole(repo, auth):
    u = User(id="", email="maija@egoiq.com", name="Maija", is_admin=True,
             grants=(Grant("attendo", "edit"),))
    saved = repo.save_user(auth, u)
    assert saved.id
    got = repo.get_user(auth, saved.id)
    assert got.email == "maija@egoiq.com"
    assert got.name == "Maija"
    assert got.is_admin is True
    assert got.grants == (Grant("attendo", "edit"),)


def test_a_user_is_found_by_verified_email(repo, auth):
    """Sign-in has an email and nothing else — this is the lookup it needs."""
    repo.save_user(auth, User(id="", email="Maija@Egoiq.com", name="M"))
    found = repo.find_user_by_email(auth, "maija@egoiq.com")
    assert found is not None and found.name == "M"


def test_email_matching_ignores_case(repo, auth):
    repo.save_user(auth, User(id="", email="maija@egoiq.com", name="M"))
    assert repo.find_user_by_email(auth, "MAIJA@EGOIQ.COM") is not None


def test_an_unknown_email_is_none_not_an_error(repo, auth):
    assert repo.find_user_by_email(auth, "nobody@example.com") is None


def test_grants_can_be_replaced(repo, auth):
    u = repo.save_user(auth, User(id="", email="a@b.c", grants=(Grant("attendo", "view"),)))
    repo.set_grants(auth, u.id, (Grant("synsam", "edit"), Grant("attendo/case-1", "view")))
    got = repo.get_user(auth, u.id)
    assert got.grants == (Grant("synsam", "edit"), Grant("attendo/case-1", "view"))


def test_a_user_with_no_grants_round_trips(repo, auth):
    """Domain auto-join creates exactly this: admitted, granted nothing."""
    u = repo.save_user(auth, User(id="", email="new@egoiq.com"))
    assert repo.get_user(auth, u.id).grants == ()


def test_listing_returns_every_user(repo, auth):
    repo.save_user(auth, User(id="", email="a@x.c"))
    repo.save_user(auth, User(id="", email="b@x.c"))
    assert {u.email for u in repo.list_users(auth)} == {"a@x.c", "b@x.c"}


def test_deleting_a_user_takes_its_grants(repo, store, auth):
    u = repo.save_user(auth, User(id="", email="a@x.c", grants=(Grant("attendo", "edit"),)))
    approve_all(store, lambda: repo.delete_user(auth, u.id))
    assert repo.get_user(auth, u.id) is None
    assert repo.list_users(auth) == []


def test_deleting_a_user_takes_its_password_too(repo, store, auth):
    """Orphaned credential material: leaving a password hash behind after
    its account is gone serves no purpose and nothing else ever cleans it
    up -- see `delete_user`'s docstring."""
    u = repo.save_user(auth, User(id="", email="a@x.c"))
    _legacy_password_hash(repo, auth, u.id)
    approve_all(store, lambda: repo.delete_user(auth, u.id))
    assert _stored_password_hash(repo, auth, u.id) is None


def test_deleting_a_user_with_no_password_is_not_an_error(repo, store, auth):
    """Most users never set one (Google/Microsoft sign-in only) -- the
    missing password path must not turn deletion into a NotFound error."""
    u = repo.save_user(auth, User(id="", email="a@x.c"))
    approve_all(store, lambda: repo.delete_user(auth, u.id))
    assert repo.get_user(auth, u.id) is None


def test_malformed_grants_are_skipped_not_propagated(repo, auth):
    """A bad grant row must cost its owner that one grant, not their whole account.

    Grant.__post_init__ now validates and raises ValueError on malformed scopes
    (trailing slash, . or .. segments) and invalid modes. The _grants() method
    has two guards:
    - Pre-check: skip rows where `g.get("scope")` is falsy (empty/missing scope)
    - ValueError handler: catch Grant construction errors (trailing slash, .. segments,
      or mode outside {view, edit})

    A malformed row in datahive would break the entire user if the error
    propagated; instead, _grants() skips it, leaving the user loadable with
    their valid grants intact.
    """
    u = repo.save_user(auth, User(id="", email="test@x.c", name="Test"))
    from reportbuilder.store import paths as P
    # Craft a stored grants object with one valid and four malformed rows
    repo._write_json(auth, P.user_grants_path(u.id),
                     {"grants": [
                         {"scope": "attendo/case-1", "mode": "view"},  # valid
                         {"scope": "", "mode": "edit"},  # caught by pre-check: empty scope
                         {"scope": "attendo/", "mode": "view"},  # caught by ValueError: trailing slash
                         {"scope": "attendo/../synsam", "mode": "view"},  # caught by ValueError: .. segment
                         {"scope": "attendo", "mode": "delete"},  # caught by ValueError: invalid mode
                     ]},
                     [P.LABEL_GRANTS])
    # The user should still load, with only the valid grant
    got = repo.get_user(auth, u.id)
    assert got is not None
    assert got.grants == (Grant("attendo/case-1", "view"),)


def test_find_user_by_email_returns_none_for_empty_query(repo, auth):
    """An empty or whitespace email query must fail safe, not match a user with
    an empty email (a misconfigured IdP claim or upstream bug). This is the
    load-bearing path into a user record per spec §4."""
    # Save a user with an empty email (to demonstrate the guard is needed)
    u = repo.save_user(auth, User(id="", email="", name="Empty"))
    # A query for empty string must return None, not the user
    assert repo.find_user_by_email(auth, "") is None
    assert repo.find_user_by_email(auth, "   ") is None
    # But a normal email still finds the right user
    repo.save_user(auth, User(id="", email="test@x.c", name="Test"))
    assert repo.find_user_by_email(auth, "test@x.c") is not None
