# Permissions Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give nSight a permission model — who may see which customer, and whether they may edit — enforced in one place and covered by tests, while the app still signs in with the dev bearer.

**Architecture:** Grants are data in datahive (`settings/user/{id}.grants`), a grant being a path prefix plus a `view`/`edit` mode. One module answers `may_read` / `may_write`; FastAPI dependencies apply it to routes; the seven repository listings that used to be filtered by datahive filter through it instead.

**Tech Stack:** Python 3.13, FastAPI, pytest. Frontend untouched by this plan.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-20-user-management-design.md`. Read §5 and §5.3 before starting.
- All persisted state goes to datahive via `Repository`. Never `localStorage`, never a local file.
- Paths are built only by `reportbuilder/store/paths.py` helpers — never an f-string at a call site.
- Run tests with `.venv/bin/python -m pytest`, not `uv run` (that rebuilds into an env without pandas).
- A grant scope is a datahive path prefix: `"attendo"` or `"attendo/case-9b32"`. Never a trailing slash.
- `mode` is exactly `"view"` or `"edit"`.
- This plan adds no login. Every route keeps working with the dev bearer; the user is resolved by a stub that Plan 2 replaces.

## File Structure

New:

| File | Responsibility |
|---|---|
| `src/reportbuilder/auth/permissions.py` | The grant model and the two questions. No I/O, no FastAPI, no datahive — so it is testable as arithmetic and reviewable as security. |
| `src/reportbuilder/api/deps_auth.py` | Request → user, and user → allowed. The only file Plan 2 has to reopen. |

Modified:

| File | Change |
|---|---|
| `src/reportbuilder/store/paths.py` | Two path helpers and their labels. |
| `src/reportbuilder/store/repository.py` | User/grant CRUD; `user=` on seven listings; the material-location cache. |
| `src/reportbuilder/store/repository_client.py` | Passes the user down to `find_*`. |
| `src/reportbuilder/api/deps.py` | `get_client` resolves the user. |
| the nine `routes_*.py` | One dependency per route. No logic. |

Why permissions and dependencies are separate files: the rules are worth reading
on their own, and `deps_auth` drags in FastAPI, the store and the request. Keeping
`permissions.py` free of all three is what lets its test file read as a
specification of the policy rather than a test of the framework.

---

### Task 1: The grant model and its rules

**Files:**
- Create: `src/reportbuilder/auth/__init__.py`
- Create: `src/reportbuilder/auth/permissions.py`
- Test: `tests/suite/unit/auth/__init__.py`
- Test: `tests/suite/unit/auth/test_permissions.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Grant(scope: str, mode: str)`, `User(id, email, name, is_admin, grants: tuple[Grant, ...])`, `may_read(user, path) -> bool`, `may_write(user, path) -> bool`, `visible_scopes(user) -> tuple[str, ...]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/suite/unit/auth/test_permissions.py
"""Who may see what.

This is the security-critical file: with nSight holding a tenant-wide datahive
token, these functions are the only thing separating one customer's data from
another's. Every case below is a customer-visible failure if it regresses.
"""
import pytest

from reportbuilder.auth.permissions import Grant, User, may_read, may_write, visible_scopes


def user(*grants, admin=False):
    return User(id="u1", email="a@b.c", name="A", is_admin=admin,
                grants=tuple(Grant(s, m) for s, m in grants))


class TestCustomerGrant:
    def test_reaches_the_customer_itself(self):
        u = user(("attendo", "edit"))
        assert may_read(u, "attendo/customer.json")

    def test_reaches_the_cases_under_it(self):
        u = user(("attendo", "edit"))
        assert may_read(u, "attendo/case-9b32/report/rep-1")

    def test_does_not_reach_another_customer(self):
        u = user(("attendo", "edit"))
        assert not may_read(u, "synsam/customer.json")

    def test_does_not_match_a_customer_by_prefix(self):
        """"attendo" must not admit "attendo-oy" — a path prefix is a path
        prefix, not a string prefix."""
        u = user(("attendo", "edit"))
        assert not may_read(u, "attendo-oy/customer.json")


class TestCaseGrant:
    def test_reaches_its_own_case(self):
        u = user(("attendo/case-9b32", "edit"))
        assert may_read(u, "attendo/case-9b32/report/rep-1")

    def test_does_not_reach_the_customer_above_it(self):
        """Speksi 2 P-O-06/07: access to one study WITHOUT its customer."""
        u = user(("attendo/case-9b32", "edit"))
        assert not may_read(u, "attendo/customer.json")

    def test_does_not_reach_a_sibling_case(self):
        u = user(("attendo/case-9b32", "edit"))
        assert not may_read(u, "attendo/case-0000/report/rep-1")


class TestMode:
    def test_view_can_read(self):
        assert may_read(user(("attendo", "view")), "attendo/customer.json")

    def test_view_cannot_write(self):
        assert not may_write(user(("attendo", "view")), "attendo/customer.json")

    def test_edit_can_write(self):
        assert may_write(user(("attendo", "edit")), "attendo/customer.json")

    def test_the_most_specific_grant_decides(self):
        """A view grant on one case does not override edit on the customer, and
        an edit grant on one case does not leak edit to its siblings."""
        u = user(("attendo", "view"), ("attendo/case-9b32", "edit"))
        assert may_write(u, "attendo/case-9b32/report/rep-1")
        assert not may_write(u, "attendo/case-0000/report/rep-1")


class TestAdmin:
    def test_admin_is_not_access(self):
        """Administering access and having access are different things. An admin
        with no grant sees no data."""
        u = user(admin=True)
        assert not may_read(u, "attendo/customer.json")
        assert not may_write(u, "attendo/customer.json")

    def test_admin_with_a_grant_is_ordinary(self):
        u = user(("attendo", "view"), admin=True)
        assert may_read(u, "attendo/customer.json")
        assert not may_write(u, "attendo/customer.json")


class TestSettingsPaths:
    def test_nobody_reaches_settings_by_grant(self):
        """`settings/**` holds users, grants and app configuration. It is
        reached by the admin dependency, never by a data grant — otherwise a
        grant named "settings" would be privilege escalation."""
        u = user(("settings", "edit"))
        assert not may_read(u, "settings/user/u2")
        assert not may_write(u, "settings/access.json")


class TestVisibleScopes:
    def test_lists_what_a_user_may_see(self):
        u = user(("attendo", "edit"), ("synsam/case-1", "view"))
        assert visible_scopes(u) == ("attendo", "synsam/case-1")

    def test_no_grants_is_empty_not_everything(self):
        assert visible_scopes(user()) == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/suite/unit/auth/test_permissions.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'reportbuilder.auth'`

- [ ] **Step 3: Write the implementation**

```python
# src/reportbuilder/auth/__init__.py
"""Who a request is, and what they may reach."""
```

```python
# src/reportbuilder/auth/permissions.py
"""Who may see what.

nSight holds a datahive token that is read-write across the whole tenant (spec
D3), so datahive no longer filters anything per user. These two functions are
the only thing separating one customer's data from another's — treat changes
here as security changes.

A grant is a datahive PATH PREFIX plus a mode:

    Grant("attendo",            "edit")   the customer and everything under it
    Grant("attendo/case-9b32",  "view")   one study, without its customer

which are Speksi 2's P-O-05 and P-O-06/07 expressed as data rather than as a
token caveat.
"""
from __future__ import annotations

from dataclasses import dataclass, field

VIEW = "view"
EDIT = "edit"

#: Objects under this prefix are app configuration — users, grants, fonts,
#: templates settings. They are reached through the admin dependency, never
#: through a data grant, or a grant named "settings" would be an escalation.
_RESERVED = ("settings",)


@dataclass(frozen=True)
class Grant:
    scope: str
    mode: str = VIEW

    def covers(self, path: str) -> bool:
        """Does this grant's prefix contain *path*?

        Segment-wise, so "attendo" does not admit "attendo-oy": a path prefix is
        a prefix of the SEGMENTS, not of the string.
        """
        want = [s for s in self.scope.split("/") if s]
        have = [s for s in path.split("/") if s]
        return len(have) >= len(want) and have[: len(want)] == want


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str = ""
    is_admin: bool = False
    grants: tuple[Grant, ...] = field(default_factory=tuple)


def _best(user: User, path: str) -> Grant | None:
    """The most specific grant covering *path*, or None.

    Most specific wins, so a view grant on a customer and an edit grant on one
    of its cases mean what they look like they mean.
    """
    covering = [g for g in user.grants if g.covers(path)]
    if not covering:
        return None
    return max(covering, key=lambda g: len([s for s in g.scope.split("/") if s]))


def _reserved(path: str) -> bool:
    head = next((s for s in path.split("/") if s), "")
    return head in _RESERVED


def may_read(user: User, path: str) -> bool:
    if _reserved(path):
        return False
    return _best(user, path) is not None


def may_write(user: User, path: str) -> bool:
    if _reserved(path):
        return False
    grant = _best(user, path)
    return grant is not None and grant.mode == EDIT


def visible_scopes(user: User) -> tuple[str, ...]:
    """The scopes this user may see, for filtering a listing cheaply."""
    return tuple(g.scope for g in user.grants)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/auth/test_permissions.py -q`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add src/reportbuilder/auth tests/suite/unit/auth
git commit -m "feat(auth): the grant model — who may see what"
```

---

### Task 2: Users and grants in datahive

**Files:**
- Modify: `src/reportbuilder/store/paths.py` (add label + path helpers)
- Modify: `src/reportbuilder/store/repository.py` (add user CRUD near the settings section, ~line 524)
- Test: `tests/suite/unit/store/test_repository_users.py`

**Interfaces:**
- Consumes: `Grant`, `User` from Task 1.
- Produces: `Repository.save_user(auth, user) -> User`, `.get_user(auth, user_id) -> User | None`, `.find_user_by_email(auth, email) -> User | None`, `.list_users(auth) -> list[User]`, `.delete_user(auth, user_id) -> None`, `.set_grants(auth, user_id, grants) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/suite/unit/store/test_repository_users.py
"""Users and their grants, stored in datahive.

Per spec §2 there is no local user list: attaching a different hive must bring
the users with it.
"""
import pytest

from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


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


def test_deleting_a_user_takes_its_grants(repo, auth):
    u = repo.save_user(auth, User(id="", email="a@x.c", grants=(Grant("attendo", "edit"),)))
    repo.delete_user(auth, u.id)
    assert repo.get_user(auth, u.id) is None
    assert repo.list_users(auth) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/suite/unit/store/test_repository_users.py -q`
Expected: FAIL — `AttributeError: 'Repository' object has no attribute 'save_user'`

- [ ] **Step 3: Add the paths**

In `src/reportbuilder/store/paths.py`, add to the label block (after `LABEL_SETTINGS`):

```python
LABEL_USER = "nsight:user"
LABEL_GRANTS = "nsight:grants"
```

and after `settings_path`:

```python
def user_path(user_id: str) -> str:
    return f"{SETTINGS_ROOT}/user/{_seg(user_id, 'user_id')}"


def user_grants_path(user_id: str) -> str:
    """Grants are a sibling of the user, not part of it: they are rewritten far
    more often than the identity they belong to, exactly as material curation is
    a sibling of the .sav."""
    return f"{user_path(user_id)}.grants"
```

Also add the two new paths to the module docstring's map, beneath `settings/{key}`:

```
    settings/user/{user_id}                          nsight:user
    settings/user/{user_id}.grants                   nsight:grants
```

- [ ] **Step 4: Add the repository methods**

In `src/reportbuilder/store/repository.py`, immediately after `set_setting` (~line 533):

```python
    # --- users and grants -------------------------------------------------
    #
    # Stored in datahive so that attaching a different hive brings the people
    # with it (spec §2). nSight keeps no user list of its own.

    def save_user(self, auth: AuthContext, user: "User") -> "User":
        """Create or replace. An empty id means create."""
        from dataclasses import replace  # noqa: PLC0415

        uid = user.id or _new_id("usr")
        self._write_json(auth, P.user_path(uid),
                         {"id": uid, "email": user.email.strip(),
                          "name": user.name, "is_admin": bool(user.is_admin)},
                         [P.LABEL_USER])
        self.set_grants(auth, uid, user.grants)
        return replace(user, id=uid)

    def set_grants(self, auth: AuthContext, user_id: str, grants) -> None:
        self._write_json(auth, P.user_grants_path(user_id),
                         {"grants": [{"scope": g.scope, "mode": g.mode} for g in grants]},
                         [P.LABEL_GRANTS])

    def _grants(self, auth: AuthContext, user_id: str) -> tuple:
        from reportbuilder.auth.permissions import Grant  # noqa: PLC0415

        try:
            d = self._read_json(auth, P.user_grants_path(user_id))
        except (NotFound, ValueError, UnicodeDecodeError):
            return ()
        return tuple(Grant(g["scope"], g.get("mode", "view"))
                     for g in d.get("grants", []) if g.get("scope"))

    def get_user(self, auth: AuthContext, user_id: str) -> "User | None":
        from reportbuilder.auth.permissions import User  # noqa: PLC0415

        try:
            d = self._read_json(auth, P.user_path(user_id))
        except (NotFound, ValueError, UnicodeDecodeError):
            return None
        return User(id=d["id"], email=d.get("email", ""), name=d.get("name", ""),
                    is_admin=bool(d.get("is_admin")), grants=self._grants(auth, d["id"]))

    def list_users(self, auth: AuthContext) -> list:
        out = []
        for info in self.store.list(auth, P.SETTINGS_ROOT + "/", labels=[P.LABEL_USER]):
            user = self.get_user(auth, info.path.rsplit("/", 1)[-1])
            if user is not None:
                out.append(user)
        return sorted(out, key=lambda u: u.email.lower())

    def find_user_by_email(self, auth: AuthContext, email: str) -> "User | None":
        """Sign-in has a verified email and nothing else.

        Case-insensitive: an IdP may return `Maija@Egoiq.com` today and
        `maija@egoiq.com` tomorrow, and they are the same person.
        """
        wanted = (email or "").strip().lower()
        return next((u for u in self.list_users(auth) if u.email.lower() == wanted), None)

    def delete_user(self, auth: AuthContext, user_id: str) -> None:
        for path in (P.user_path(user_id), P.user_grants_path(user_id)):
            try:
                self.store.delete(auth, path)
            except NotFound:
                pass
```

Add `SETTINGS_ROOT` to the paths import usage if it is not already exported — check `paths.py` defines it; if the constant is named differently, use that name.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/store/test_repository_users.py -q`
Expected: 8 passed

- [ ] **Step 6: Run the whole suite**

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures (1543 passed, 1 known live-consent failure)

- [ ] **Step 7: Commit**

```bash
git add src/reportbuilder/store/paths.py src/reportbuilder/store/repository.py tests/suite/unit/store/test_repository_users.py
git commit -m "feat(store): users and grants live in datahive"
```

---

### Task 3: Close the listings that stopped being filtered

**Files:**
- Modify: `src/reportbuilder/store/repository.py` — `list_customers` (134), `list_cases` (173), `find_case` (193), `list_materials` (247), `find_material` (289), `list_reports` (356), `recent_reports` (367)
- Test: `tests/suite/unit/store/test_listing_isolation.py`

**Interfaces:**
- Consumes: `may_read`, `User` from Task 1; `AuthContext`.
- Produces: every listed method accepts an optional `user: User | None = None` and filters when given. `None` means unfiltered — used by Plan 2's bootstrap and by admin-only maintenance.

**Why this task exists:** spec §5.3. Today these seven listings are filtered by datahive because nSight calls it as the logged-in user. Under D3 they are called with a tenant-wide service token and silently return everything. Nothing errors.

- [ ] **Step 1: Write the failing tests**

```python
# tests/suite/unit/store/test_listing_isolation.py
"""Listings must not leak another customer's existence.

Spec §5.3: these seven calls used to be filtered by datahive, because nSight
talked to it as the logged-in user. Holding a tenant-wide service token instead
means each one returns the whole tenant unless it filters here. Nothing throws
when this regresses — hence these tests.
"""
import json

import pytest

from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def tree(repo, auth):
    """Two customers, one case each, one report each, one material each."""
    a = repo.create_customer(auth, "Attendo")
    b = repo.create_customer(auth, "Synsam")
    ka = repo.create_case(auth, a.id, "A-study")
    kb = repo.create_case(auth, b.id, "B-study")
    repo.save_report(auth, a.id, ka.id, json.dumps({"name": "A-report"}))
    repo.save_report(auth, b.id, kb.id, json.dumps({"name": "B-report"}))
    ma = repo.attach_material(auth, a.id, ka.id, "a.sav", b"SAV")
    mb = repo.attach_material(auth, b.id, kb.id, "b.sav", b"SAV")
    return {"a": a, "b": b, "ka": ka, "kb": kb, "ma": ma, "mb": mb}


@pytest.fixture
def only_a(tree):
    return User(id="u", email="a@b.c", grants=(Grant(tree["a"].id, "edit"),))


def test_list_customers_hides_the_other_customer(repo, auth, tree, only_a):
    assert [c.name for c in repo.list_customers(auth, user=only_a)] == ["Attendo"]


def test_list_cases_refuses_an_ungranted_customer(repo, auth, tree, only_a):
    assert repo.list_cases(auth, tree["b"].id, user=only_a) == []


def test_find_case_does_not_resolve_an_ungranted_case(repo, auth, tree, only_a):
    assert repo.find_case(auth, tree["kb"].id, user=only_a) is None
    assert repo.find_case(auth, tree["ka"].id, user=only_a) is not None


def test_find_material_does_not_resolve_an_ungranted_material(repo, auth, tree, only_a):
    """The seventeen material-addressed routes rest on this (spec §5.1): a
    material id is not authorisation."""
    assert repo.find_material(auth, tree["mb"].id, user=only_a) is None
    assert repo.find_material(auth, tree["ma"].id, user=only_a) is not None


def test_list_materials_refuses_an_ungranted_case(repo, auth, tree, only_a):
    assert repo.list_materials(auth, tree["b"].id, tree["kb"].id, user=only_a) == []


def test_list_reports_refuses_an_ungranted_case(repo, auth, tree, only_a):
    assert repo.list_reports(auth, tree["b"].id, tree["kb"].id, user=only_a) == []


def test_recent_reports_spans_only_granted_customers(repo, auth, tree, only_a):
    """The landing page. Unfiltered, it shows everyone's work to everyone."""
    names = [r.name for r in repo.recent_reports(auth, user=only_a)]
    assert names == ["A-report"]


def test_a_case_grant_sees_its_case_but_not_its_customer(repo, auth, tree):
    u = User(id="u", email="a@b.c",
             grants=(Grant(f"{tree['a'].id}/{tree['ka'].id}", "view"),))
    assert [c.name for c in repo.list_customers(auth, user=u)] == []
    assert repo.find_case(auth, tree["ka"].id, user=u) is not None


def test_a_grant_to_a_deleted_customer_is_inert(repo, auth, tree):
    """Spec §5: "a grant naming a customer or case that no longer exists is
    ignored", the way a template binding to a deleted file is. It must not
    match by accident and it must not raise."""
    u = User(id="u", email="a@b.c", grants=(Grant("cust-gone", "edit"),))
    assert repo.list_customers(auth, user=u) == []
    assert repo.find_case(auth, tree["ka"].id, user=u) is None


def test_no_user_means_unfiltered(repo, auth, tree):
    """Plan 2's bootstrap and admin maintenance need the whole tenant."""
    assert len(repo.list_customers(auth)) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/suite/unit/store/test_listing_isolation.py -q`
Expected: FAIL — `TypeError: list_customers() got an unexpected keyword argument 'user'`

- [ ] **Step 3: Add the filter helper**

In `src/reportbuilder/store/repository.py`, above `class Repository`:

```python
def _admits(user, path: str) -> bool:
    """Does *user* admit this path? A None user is unfiltered — see the
    `user=` parameter on the listing methods."""
    if user is None:
        return True
    from reportbuilder.auth.permissions import may_read  # noqa: PLC0415

    return may_read(user, path)
```

- [ ] **Step 4: Filter each of the seven**

`list_customers` (~134) — add `user=None`, filter by the customer's own path, and correct the docstring, which currently claims datahive has already filtered the listing:

```python
    def list_customers(self, auth: AuthContext, user=None) -> list[Customer]:
        """Every customer this user may see.

        Filtered HERE, not by datahive. nSight holds a tenant-wide token, so
        the store returns the whole tenant (spec §5.3). A user granted one case
        sees no customer at all — the customer object is above their grant.
        """
        out = []
        for info in self.store.list(auth, "", labels=[P.LABEL_CUSTOMER]):
            if not _admits(user, info.path):
                continue
            d = self._read_json(auth, info.path)
            out.append(Customer(id=d["id"], name=d.get("name", d["id"]),
                                template_id=d.get("template_id", "")))
        # A customer list is a directory: alphabetical is how you find a name
        # in it. Only the CASE list is newest-first.
        return sorted(out, key=lambda c: _natural_key(c.name))
```

`list_cases` (~173), `list_materials` (~247), `list_reports` (~356) — same shape: add `user=None`, and guard the loop with `if not _admits(user, info.path): continue`.

`find_case` (~193) and `find_material` (~289) — add `user=None` and return `None` when the resolved path is not admitted:

```python
            if not _admits(user, info.path):
                return None
```

`recent_reports` (~367) — add `user=None` and filter the listing comprehension:

```python
            for info in self.store.list(auth, "", labels=[P.LABEL_REPORT_META])
            if _admits(user, info.path)
```

Correct its docstring too: "The caller's most recently modified reports" becomes "The most recently modified reports this user may see."

- [ ] **Step 5: Correct the comments that still promise the old guarantee**

Spec §5.3 item 2. These assert a guarantee that stopped holding, and left alone
they will teach the next reader — human or agent — to skip the filter.

`src/reportbuilder/api/deps_store.py` line 4 says "nSight talks to datahive AS
THE LOGGED-IN USER — datahive then enforces". Replace that sentence with:

```
because nSight talks to datahive with its own service credential, which is
read-write across the tenant. datahive no longer narrows anything per user;
reportbuilder/auth/permissions.py does. See spec §5.3.
```

`src/reportbuilder/store/repository.py`, `find_material` (~289): its docstring
ends "one labelled listing, already permission-filtered". Replace that clause
with "one labelled listing, filtered here by the caller's grants — the store
returns the whole tenant."

`src/reportbuilder/store/paths.py`: if the module docstring describes listings
as permission-filtered, correct it the same way. Check with
`grep -n "permission-filtered\|filtered" src/reportbuilder/store/paths.py`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/store/test_listing_isolation.py -q`
Expected: 9 passed

- [ ] **Step 7: Run the whole suite — nothing else may break**

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures. Every existing caller omits `user=`, so behaviour is unchanged for them.

- [ ] **Step 8: Commit**

```bash
git add src/reportbuilder/store/repository.py src/reportbuilder/store/paths.py src/reportbuilder/api/deps_store.py tests/suite/unit/store/test_listing_isolation.py
git commit -m "fix(store): the seven listings filter by grant, not by datahive"
```

---

### Task 4: Route guards, and a census that keeps them honest

**Files:**
- Create: `src/reportbuilder/api/deps_auth.py`
- Modify: all nine routers — `routes_ai.py`, `routes_cases.py`, `routes_customers.py`, `routes_materials.py`, `routes_questions.py`, `routes_render.py`, `routes_reports.py`, `routes_settings.py`, `routes_templates.py`
- Test: `tests/suite/integration/api/test_route_census.py`

**Interfaces:**
- Consumes: `may_read`, `may_write`, `User` (Task 1); `Repository.find_user_by_email` (Task 2); the `user=` parameters (Task 3); `get_auth`, `get_repository` from `deps_store.py`.
- Produces, all usable as `Depends(...)` with no arguments:
  - `current_user` → `User`
  - `require_admin` → `User`
  - `require_customer` / `require_customer_write` — take `customer_id` from the path
  - `require_case` / `require_case_write` — take `case_id`
  - `require_material` / `require_material_write` — take `material_id`
  - `PUBLIC_ROUTES: frozenset[str]`

**Why the guards come in read/write pairs rather than one function with a `write=` flag:** a plain `write: bool = False` parameter on a FastAPI dependency is not a default — it is a **query parameter**. `DELETE /cases/x/reports/y?write=false` would then ask for read permission on a delete. Two named dependencies, built by one factory, cannot be talked out of their mode from the query string.

- [ ] **Step 1: Write the failing census test**

```python
# tests/suite/integration/api/test_route_census.py
"""No route serves data without resolving a user.

What this holds is that a route ADDED LATER cannot quietly skip the check.
Whoever adds one either declares a guard or writes themselves into
PUBLIC_ROUTES, in a diff a reviewer can see. There is no runtime symptom when
a route forgets — it just serves the whole tenant.
"""
from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import GUARD_NAMES, PUBLIC_ROUTES


def _guarded(route) -> bool:
    """True when one of this route's dependencies resolves a user."""
    return any(getattr(d.call, "__name__", "") in GUARD_NAMES
               for d in route.dependant.dependencies)


def test_every_route_is_guarded_or_explicitly_public():
    app = create_app()
    unguarded = [
        f"{sorted(getattr(route, 'methods', []))} {route.path}"
        for route in app.routes
        if hasattr(route, "dependant")
        and route.path not in PUBLIC_ROUTES
        and not _guarded(route)
    ]
    assert unguarded == [], (
        "these routes resolve no user — add a guard from deps_auth, or list "
        "them in PUBLIC_ROUTES with a reason:\n  " + "\n  ".join(sorted(unguarded)))


def test_public_routes_are_few_and_named():
    """A growing public list is the failure this test exists to make visible."""
    assert PUBLIC_ROUTES == frozenset({
        "/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_route_census.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reportbuilder.api.deps_auth'`

- [ ] **Step 3: Write the dependencies**

```python
# src/reportbuilder/api/deps_auth.py
"""Turning a request into a user, and a user into an answer.

Plan 2 adds sign-in. Until then `current_user` resolves a development user, and
it is the ONLY function in this file that changes when the session cookie
arrives — everything below it asks the permission model, not the request.
"""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request

from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import Grant, User, may_read, may_write
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

#: Routes that serve no customer data. Anything else must resolve a user — see
#: tests/suite/integration/api/test_route_census.py.
PUBLIC_ROUTES = frozenset({"/health", "/openapi.json", "/docs",
                           "/docs/oauth2-redirect", "/redoc"})


def current_user(request: Request,
                 auth: AuthContext = Depends(get_auth),
                 repo: Repository = Depends(get_repository)) -> User:
    """The user this request acts as.

    DEVELOPMENT STAND-IN. `NSIGHT_DEV_USER` names an email that must already
    exist in the store; without it the request is an admin granted every
    customer, which is exactly today's pre-login behaviour, so nothing that
    works now stops working. Plan 2 replaces this body with a session lookup
    and deletes the environment variable.
    """
    email = os.environ.get("NSIGHT_DEV_USER", "").strip()
    if email:
        user = repo.find_user_by_email(auth, email)
        if user is None:
            raise HTTPException(401, f"NSIGHT_DEV_USER '{email}' is not a known user")
        return user
    return User(id="dev", email="dev@localhost", name="Development",
                is_admin=True,
                grants=tuple(Grant(c.id, "edit") for c in repo.list_customers(auth)))


def require_admin(user: User = Depends(current_user)) -> User:
    """Managing users and tenant-wide settings. Not a data grant (spec §5)."""
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user


def _check(user: User, path: str, write: bool) -> None:
    if (may_write if write else may_read)(user, path):
        return
    # A read you may not do is 404, not 403: a 403 confirms the object exists,
    # which is what "never leak the existence of an out-of-scope path" forbids.
    # A write is 403 — you can already see the thing, you just may not change it.
    raise HTTPException(403 if write else 404, "Not found")


def _customer_guard(write: bool):
    def guard(customer_id: str, user: User = Depends(current_user)) -> User:
        _check(user, customer_id, write)
        return user
    guard.__name__ = "require_customer_write" if write else "require_customer"
    return guard


def _case_guard(write: bool):
    def guard(case_id: str,
              user: User = Depends(current_user),
              auth: AuthContext = Depends(get_auth),
              repo: Repository = Depends(get_repository)) -> User:
        case = repo.find_case(auth, case_id, user=user)
        if case is None:
            raise HTTPException(404, f"Case '{case_id}' not found")
        _check(user, f"{case.customer_id}/{case.id}", write)
        return user
    guard.__name__ = "require_case_write" if write else "require_case"
    return guard


def _material_guard(write: bool):
    """The material-addressed routes (spec §5.1).

    A material id is not authorisation: resolve it to its case and customer and
    ask the same question every other route asks. `find_material` already
    returns None for a material the user may not see, so the 404 arrives before
    any SAV is read.
    """
    def guard(material_id: str,
              user: User = Depends(current_user),
              auth: AuthContext = Depends(get_auth),
              repo: Repository = Depends(get_repository)) -> User:
        material = repo.find_material(auth, material_id, user=user)
        if material is None:
            raise HTTPException(404, f"Material '{material_id}' not found")
        _check(user, f"{material.customer_id}/{material.case_id}", write)
        return user
    guard.__name__ = "require_material_write" if write else "require_material"
    return guard


require_customer = _customer_guard(False)
require_customer_write = _customer_guard(True)
require_case = _case_guard(False)
require_case_write = _case_guard(True)
require_material = _material_guard(False)
require_material_write = _material_guard(True)

#: What the census recognises as "this route resolved a user".
GUARD_NAMES = frozenset({
    "current_user", "require_admin",
    "require_customer", "require_customer_write",
    "require_case", "require_case_write",
    "require_material", "require_material_write",
})
```

- [ ] **Step 4: Attach a guard to every route**

Add the import to each router module:

```python
from reportbuilder.api.deps_auth import (
    current_user, require_admin, require_case, require_case_write,
    require_customer, require_customer_write, require_material,
    require_material_write,
)
from reportbuilder.auth.permissions import User
```

Then add one parameter to each route function — `user: User = Depends(<guard>)` — using this table. It is every route the app serves; nothing here is an example.

**`routes_cases.py`** — `POST /cases` has no customer in its path (a pre-hierarchy route): guard with `current_user` and let the body's customer be checked by the repository call, or reject it with 400 if it has no customer. `GET /cases` passes `user=user` to `repo.list_cases`. `PATCH /cases/{case_id}` → `require_case_write`. `DELETE /cases/{case_id}` → `require_case_write`.

**`routes_customers.py`**
| route | guard |
|---|---|
| `POST /customers` | `current_user` — creating a customer needs a session; the creator is granted it in Plan 3 |
| `GET /customers` | `current_user`, and pass `user=user` to `repo.list_customers` |
| `GET /customers/{customer_id}` | `require_customer` |
| `PATCH /customers/{customer_id}` | `require_customer_write` |
| `POST /customers/{customer_id}/cases` | `require_customer_write` |
| `GET /customers/{customer_id}/cases` | `require_customer`, pass `user=user` |
| `GET /customers/{customer_id}/cases/{case_id}` | `require_case` |
| `PATCH /customers/{customer_id}/cases/{case_id}` | `require_case_write` |
| `GET /reports/recent` | `current_user`, pass `user=user` to `repo.recent_reports` |
| `GET /cases/{case_id}/resolve` | `require_case` |
| `POST /customers/{customer_id}/cases/from-material` | `require_customer_write` |
| `GET /customers/{customer_id}/cases/{case_id}/materials` | `require_case`, pass `user=user` |
| `GET /materials/{material_id}/locate` | `require_material` |

**`routes_materials.py`**
| route | guard |
|---|---|
| `GET /cases/{case_id}/materials` | `require_case` |
| `POST /cases/{case_id}/materials` | `require_case_write` |
| `GET /cases/{case_id}/materials/{material_id}/usage` | `require_case` |
| `DELETE /cases/{case_id}/materials/{material_id}` | `require_case_write` |

**`routes_reports.py`** — all six are case-addressed. `POST`, `PUT`, `DELETE`, `POST .../duplicate` → `require_case_write`; the two `GET`s → `require_case`. `GET /cases/{case_id}/reports` passes `user=user` to `repo.list_reports`.

**`routes_render.py`** — `POST .../render` → `require_case_write` (it writes a deck into the case). The two preview `GET`s → `require_case`.

**`routes_questions.py`** — `GET /chart-types` is a static enumeration with no customer data: `current_user`. The other nine are material-addressed: `GET /materials/{id}/questions`, `.../summary`, `/variables`, `/split-groups`, `.../words` → `require_material`; `POST /materials/{id}/regroup`, `PATCH .../label`, `PUT .../word-merges` → `require_material_write`; `POST /materials/{id}/preview-chart` → `require_material` (it renders, it does not persist).

**`routes_ai.py`** — all seven are material-addressed and produce text rather than storing it: `require_material` on `slide-title`, `short-labels`, `themes`, `overview`, `conclusion`, `demographics`, `chat`.

**`routes_templates.py`**
| route | guard |
|---|---|
| `POST /customers/{customer_id}/templates` | `require_customer_write` |
| `GET /customers/{customer_id}/templates` | `require_customer` |
| `GET /customers/{customer_id}/templates/{template_id}` | `require_customer` |
| `GET /customers/{customer_id}/templates/{template_id}/file` | `require_customer` |
| `DELETE /customers/{customer_id}/templates/{template_id}` | `require_customer_write` |
| `PUT /customers/{customer_id}/template` | `require_customer_write` |
| `PUT /customers/{customer_id}/cases/{case_id}/template` | `require_case_write` |
| `GET /customers/{customer_id}/cases/{case_id}/template` | `require_case` |

**`routes_settings.py`** — fonts and substitutions are tenant-wide rendering configuration (spec §5.2). Reads are `current_user`; writes are `require_admin`: `GET /settings/fonts`, `GET /settings/font-substitutions`, `GET /settings/chart-font` → `current_user`; `PUT /settings/font-substitutions`, `PUT /settings/chart-font`, `POST /settings/fonts`, `DELETE /settings/fonts/{font_id}` → `require_admin`.

- [ ] **Step 5: Filter the flat-id façade as well**

`RepositoryClient` (`store/repository_client.py`) is what twenty-odd routes
actually talk to, and it resolves flat ids with `find_material` / `find_case` —
the two calls Task 3 just taught to filter, called here without a user. Guards
run first, so this is defence in depth rather than the primary gate; it is
cheap, and it means a route someone forgets to guard still cannot resolve
another customer's material.

In `src/reportbuilder/store/repository_client.py`, take the user in the
constructor and pass it down:

```python
    def __init__(self, repo: Repository, auth: AuthContext, user=None):
        """One per request — it carries the caller's auth AND their grants, so
        it must never be shared between requests. `user=None` is unfiltered,
        for callers with no request behind them."""
        self.repo = repo
        self.auth = auth
        self.user = user

    def _material(self, material_id: str):
        m = self.repo.find_material(self.auth, material_id, user=self.user)
        if m is None:
            raise MaterialNotFound(material_id)
        return m

    def _case(self, case_id: str):
        k = self.repo.find_case(self.auth, case_id, user=self.user)
```

and add `user=self.user` to the four listing calls it makes: `list_materials`
(line 72), `list_reports` (line 109), `list_customers` (line 121), and
`list_cases` if it calls one.

In `src/reportbuilder/api/deps.py`:

```python
def get_client(
    auth: AuthContext = Depends(get_auth),
    repo: Repository = Depends(get_repository),
    user: User = Depends(current_user),
) -> RepositoryClient:
    """The storage client for this request, scoped to this caller."""
    return RepositoryClient(repo, auth, user)
```

Import `current_user` from `reportbuilder.api.deps_auth` and `User` from
`reportbuilder.auth.permissions`. Watch for an import cycle: `deps_auth` imports
from `deps_store`, not from `deps`, so this direction is fine.

Note what this does to the census: every route taking `Depends(get_client)` now
resolves a user transitively. The census only counts a route's DIRECT
dependencies, so it keeps demanding an explicit guard — which is what we want,
since `get_client` checks nothing, it only narrows lookups.

- [ ] **Step 6: Run the census, then the suite**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_route_census.py -q`
Expected: 2 passed. If a route is listed as unguarded, it is one this table missed — guard it, do not widen `PUBLIC_ROUTES`.

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures. With `NSIGHT_DEV_USER` unset the dev user is an admin granted every customer, so existing tests see today's behaviour.

- [ ] **Step 7: Commit**

```bash
git add src/reportbuilder/api src/reportbuilder/store/repository_client.py tests/suite/integration/api/test_route_census.py
git commit -m "feat(api): every data route resolves a user, and a census holds it"
```

---

### Task 5: Cache material resolution

**Files:**
- Modify: `src/reportbuilder/store/repository.py` — `find_material` (~289), `delete_material` (~457), `attach_material` (~223)
- Test: `tests/suite/unit/store/test_material_resolution_cache.py`

**Interfaces:**
- Consumes: `Material` (existing), `_admits` (Task 3).
- Produces: unchanged public signature — `find_material(auth, material_id, user=None) -> Material | None`. The cache is private.

**Why now rather than later:** spec §5.1. `find_material` lists **every**
`nsight:config` object in the tenant to resolve one id, and the material routes
are called per chart — the AI batch does roughly 60 tenant-wide listings per
report. Task 4 just added a *second* `find_material` per request, in the guard.
Shipping the guard without this doubles the cost of the worst call in the API.

- [ ] **Step 1: Write the failing tests**

```python
# tests/suite/unit/store/test_material_resolution_cache.py
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
from reportbuilder.store.seam import AuthContext


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
    repo.delete_material(auth, material.customer_id, material.case_id, material.id)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/suite/unit/store/test_material_resolution_cache.py -q`
Expected: `test_the_second_lookup_does_not_list_again` fails with `assert 1 == 0`; the eviction and seeding tests fail too.

- [ ] **Step 3: Implement**

In `Repository.__init__`, add the cache:

```python
        # material id -> (customer_id, case_id). Resolving one otherwise lists
        # every config object in the tenant, and the material routes are called
        # per chart (spec §5.1). Location only — never the permission answer,
        # which differs per user and is re-checked on every hit.
        self._material_location: dict[str, tuple[str, str]] = {}
```

Rewrite `find_material`, keeping the signature Task 3 gave it:

```python
    def find_material(self, auth: AuthContext, material_id: str,
                      user=None) -> Material | None:
        """Locate a material by id alone, without its customer or case.

        The question/preview/render routes are all keyed by a bare material id
        from before the hierarchy existed. Rather than rewrite every one of them
        and the UI that calls them, this resolves the path the same way
        find_case does — one labelled listing, filtered here by the caller's
        grants, since the store returns the whole tenant.

        Cached by location. A hit still goes through _admits, so warming the
        cache as one user tells another user nothing.
        """
        hit = self._material_location.get(material_id)
        if hit is not None:
            customer_id, case_id = hit
            path = P.material_config_path(customer_id, case_id, material_id)
            if not _admits(user, path):
                return None
            try:
                d = self._read_json(auth, path)
            except (NotFound, ValueError, UnicodeDecodeError):
                # Gone from under us — drop the stale entry and fall through to
                # a full listing rather than reporting a material that is not
                # there.
                self._material_location.pop(material_id, None)
            else:
                return Material(id=material_id, case_id=case_id,
                                customer_id=customer_id,
                                name=d.get("name") or material_id,
                                size=int(d.get("size") or 0))

        for info in self.store.list(auth, "", labels=[P.LABEL_CONFIG]):
            segments = info.path.split("/")
            # {asiakas}/{case}/material/{id}.config
            if len(segments) == 4 and segments[3] == f"{material_id}.config":
                # Remember the location before the permission check, so a user
                # who may not see it does not force the next user to list again.
                self._material_location[material_id] = (segments[0], segments[1])
                if not _admits(user, info.path):
                    return None
                try:
                    d = self._read_json(auth, info.path)
                except (NotFound, ValueError, UnicodeDecodeError):
                    return None
                return Material(id=material_id, case_id=segments[1],
                                customer_id=segments[0],
                                name=d.get("name") or material_id,
                                size=int(d.get("size") or 0))
        # A miss is NOT cached: the id may be attached a moment from now.
        return None
```

In `attach_material`, whose local for the new id is `mid`, seed the cache just
before its `return`:

```python
        self._material_location[mid] = (customer_id, case_id)
```

In `delete_material`, before the loop that removes paths:

```python
        self._material_location.pop(material_id, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/store/test_material_resolution_cache.py -q`
Expected: 5 passed

- [ ] **Step 5: Note the lifetime, which is the process**

`get_repository()` memoises one `Repository` per process, so this cache lives as
long as the backend does and is shared by every request — which is correct for
a location that only changes when a material is attached or deleted, both of
which go through this class. It is NOT correct across processes: a material
deleted by worker A stays in worker B's cache until B tries to read it, at which
point the `NotFound` branch above evicts it. That self-healing path is why the
stale entry falls through to a listing rather than returning what it remembered.

Add that as a comment above the cache declaration so the next reader does not
have to re-derive it.

- [ ] **Step 6: Run the whole suite**

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures.

- [ ] **Step 7: Commit**

```bash
git add src/reportbuilder/store/repository.py tests/suite/unit/store/test_material_resolution_cache.py
git commit -m "perf(store): resolve a material id once, not once per chart"
```

---

### Task 6: Prove the isolation end to end

**Files:**
- Test: `tests/suite/integration/api/test_permission_matrix.py`

**Interfaces:**
- Consumes: everything above. Adds no production code.

**Why separate:** Tasks 1–4 test units. This asks the question a customer would: *can Maija, who works on Attendo, reach Synsam's data through the HTTP API?*

- [ ] **Step 1: Add a fixture that uses the real client**

The existing `client_memory` fixture passes `create_app(client=memory_hive)`,
which REPLACES `get_client` with a standalone local-fs store. Reports created
over HTTP would land there while the guards read the injected `Repository` — two
stores, and every assertion below meaningless. In production `get_client`
returns a `RepositoryClient` over the same repository, so the test must too.

Add to `tests/suite/conftest.py`, beside `client_memory`:

```python
@pytest.fixture
def client_hierarchy() -> TestClient:
    """App with NO injected client, so `get_client` builds the real
    RepositoryClient over the same object store the guards read.

    `client_memory` injects a separate local-fs client, which is right for
    render and ingest tests and wrong for anything asserting on permissions:
    the routes and the guards would be looking at different stores.
    """
    from reportbuilder.api.deps_store import get_auth, get_repository
    from reportbuilder.store.memory_objects import InMemoryObjectStore
    from reportbuilder.store.repository import Repository
    from reportbuilder.store.seam import AuthContext

    app = create_app()
    repo = Repository(InMemoryObjectStore())
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: AuthContext(token="test")
    return TestClient(app)
```

- [ ] **Step 2: Write the tests**

```python
# tests/suite/integration/api/test_permission_matrix.py
"""Can one customer's analyst reach another customer's data over HTTP?

Unit tests cover may_read. This covers the whole stack: a real app, a real
store, a user with one grant, and every shape of route the API exposes.
"""
import pytest

from reportbuilder.auth.permissions import Grant, User


@pytest.fixture
def two_customers(client_hierarchy, synthetic_bytes):
    """Attendo and Synsam, each with a study, a report and a dataset."""
    made = {}
    for name in ("Attendo", "Synsam"):
        cid = client_hierarchy.post("/customers", json={"name": name}).json()["id"]
        kid = client_hierarchy.post(f"/customers/{cid}/cases",
                                 json={"name": f"{name} study"}).json()["id"]
        mid = client_hierarchy.post(
            f"/cases/{kid}/materials",
            files={"file": ("s.sav", synthetic_bytes, "application/octet-stream")},
        ).json()["material_id"]
        rid = client_hierarchy.post(f"/cases/{kid}/reports",
                                 json={"name": f"{name} report", "render_mode": "image",
                                       "template_ref": "", "charts": []}).json()["report_id"]
        made[name] = {"cid": cid, "kid": kid, "mid": mid, "rid": rid}
    return made


def sign_in(client, monkeypatch, email, *grants, admin=False):
    """Create a user in the store the test app is using, and become them.

    `client_hierarchy` builds its Repository inside the fixture and injects it with
    `app.dependency_overrides` — reaching for the module-level `get_repository()`
    would create a SECOND, empty store and the user would never be found.
    """
    from reportbuilder.api.deps_store import get_auth, get_repository

    overrides = client.app.dependency_overrides
    repo, auth = overrides[get_repository](), overrides[get_auth]()
    repo.save_user(auth, User(id="", email=email, name=email.split("@")[0],
                              is_admin=admin,
                              grants=tuple(Grant(s, m) for s, m in grants)))
    monkeypatch.setenv("NSIGHT_DEV_USER", email)


@pytest.fixture
def as_attendo_editor(client_hierarchy, two_customers, monkeypatch):
    """Sign the client in as someone granted Attendo, edit."""
    sign_in(client_hierarchy, monkeypatch, "maija@egoiq.com",
            (two_customers["Attendo"]["cid"], "edit"))
    return two_customers


def test_the_granted_customer_is_reachable(client_hierarchy, as_attendo_editor):
    a = as_attendo_editor["Attendo"]
    assert client_hierarchy.get(f"/customers/{a['cid']}/cases").status_code == 200
    assert client_hierarchy.get(f"/cases/{a['kid']}/reports").status_code == 200


def test_the_other_customer_is_absent_from_listings(client_hierarchy, as_attendo_editor):
    names = [c["name"] for c in client_hierarchy.get("/customers").json()]
    assert names == ["Attendo"]


def test_the_other_customers_case_is_not_found(client_hierarchy, as_attendo_editor):
    b = as_attendo_editor["Synsam"]
    assert client_hierarchy.get(f"/cases/{b['kid']}/reports").status_code == 404


def test_the_other_customers_material_is_not_found(client_hierarchy, as_attendo_editor):
    """A material id is not authorisation (spec §5.1)."""
    b = as_attendo_editor["Synsam"]
    assert client_hierarchy.get(f"/materials/{b['mid']}/questions").status_code == 404


def test_the_other_customers_report_cannot_be_read(client_hierarchy, as_attendo_editor):
    b = as_attendo_editor["Synsam"]
    assert client_hierarchy.get(f"/cases/{b['kid']}/reports/{b['rid']}").status_code == 404


def test_the_other_customers_report_cannot_be_deleted(client_hierarchy, as_attendo_editor):
    b = as_attendo_editor["Synsam"]
    assert client_hierarchy.delete(f"/cases/{b['kid']}/reports/{b['rid']}").status_code in (403, 404)


def test_recents_shows_only_the_granted_customer(client_hierarchy, as_attendo_editor):
    names = [r["name"] for r in client_hierarchy.get("/reports/recent").json()]
    assert names == ["Attendo report"]


def test_a_viewer_cannot_write(client_hierarchy, two_customers, monkeypatch):
    sign_in(client_hierarchy, monkeypatch, "viewer@egoiq.com",
            (two_customers["Attendo"]["cid"], "view"))
    a = two_customers["Attendo"]
    assert client_hierarchy.get(f"/cases/{a['kid']}/reports").status_code == 200
    assert client_hierarchy.delete(f"/cases/{a['kid']}/reports/{a['rid']}").status_code == 403


def test_the_resolution_cache_does_not_leak_between_users(client_hierarchy, two_customers, monkeypatch):
    """Spec §5.1's cache is per-process and shared. One user resolving their own
    material must not make it resolvable for another."""
    a, b = two_customers["Attendo"], two_customers["Synsam"]
    sign_in(client_hierarchy, monkeypatch, "s@egoiq.com", (b["cid"], "edit"))
    assert client_hierarchy.get(f"/materials/{b['mid']}/questions").status_code == 200

    sign_in(client_hierarchy, monkeypatch, "m@egoiq.com", (a["cid"], "edit"))
    assert client_hierarchy.get(f"/materials/{b['mid']}/questions").status_code == 404


def test_an_admin_without_grants_sees_nothing(client_hierarchy, two_customers, monkeypatch):
    """Administering access is not having access (spec §5)."""
    sign_in(client_hierarchy, monkeypatch, "admin@egoiq.com", admin=True)
    assert client_hierarchy.get("/customers").json() == []
```

- [ ] **Step 3: Run them**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_permission_matrix.py -q`
Expected: 10 passed. If a test fails, the defect is in Tasks 3–5, not here — fix it there.

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures.

- [ ] **Step 5: Commit**

```bash
git add tests/suite/conftest.py tests/suite/integration/api/test_permission_matrix.py
git commit -m "test(auth): one customer's analyst cannot reach another's data"
```

---

## Not in this plan

* **Sign-in** (OIDC, sessions, the login page, cookie/proxy/nginx plumbing, `NSIGHT_BOOTSTRAP_ADMINS`) — Plan 2. `current_user` is the single seam it replaces.
* **Invitations and the Users screen** (invite records, email, Settings UI) — Plan 3.
* **The `localStorage` workspace move** (spec §8) — Plan 3, with the rest of the frontend work.
* **The last-admin rule** ("the last admin cannot be removed or demoted", spec §5) — Plan 3, with the Users screen that can attempt it. Task 2's `delete_user` is deliberately unguarded; nothing calls it over HTTP yet.
* **Default grants on domain auto-join** (`settings/access.json`, spec §5) — Plan 2, where joining first becomes possible.
* **Revocation latency** (the 30-second grant cache, spec §7) — Plan 2. Grants are read fresh on every request here, which is correct and slower than it needs to be; the cache belongs with the session it hangs off.
