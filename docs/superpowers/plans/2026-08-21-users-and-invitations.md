# Users and Invitations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give nSight Studio the last piece of user management: an admin
invites someone by email, the Users screen shows who can reach which
customers and lets an admin change that, removal and demotion honour "the
last admin cannot be removed or demoted," and the app's own state stops
leaking through two lower-severity bugs the controller flagged along the way
— a break-glass condition stricter than the spec promises, and a
title-generation bug that lets two slides fight over one title.

**Architecture:** Invitations and the last-admin rule are two small,
independent policy modules (`auth/invites.py`, `auth/users.py`) sitting next
to `identity.py` and `session.py` the way Plan 1's `permissions.py` does — no
I/O logic of their own beyond calling `Repository`, so each reads as a
specification of a rule rather than a test of the framework around it.
`identity.py` gains the one branch Plan 2 deliberately left open: a pending
invitation, matched by verified email, consumed ABOVE the domain-proof guard
(Plan 2's own note in the code says exactly where). Email is sent through an
injected function, never `smtplib` called directly from business logic, so no
test ever opens a socket. One new router (`routes_users.py`) exposes all of
it, guarded by `require_admin` throughout — administering access is not a
data grant (spec §5). The per-case workspace state currently in
`localStorage` moves to a `settings/user/{id}.workspace` object, the same
per-user-sidecar shape as grants and password.

**Tech Stack:** Python 3.13, FastAPI, pytest — no new backend dependency;
`smtplib`/`email` are standard library. Frontend: React 19, TanStack Query 5,
the existing `web/src/lib/surfaces.ts` vocabulary — no new frontend
dependency. No frontend test runner exists in this repo (Playwright is an
unconfigured devDependency, confirmed by reading `web/package.json`);
frontend tasks are verified with `tsc -b` plus a described manual check,
matching Plan 2's own precedent (its Task 8 did the same for nginx/Vite).

## Scope check

Ten tasks, spanning three backend policy modules, one new router, two
datahive CRUD extensions, and four frontend surfaces (the Users tab, the
workspace migration, and one bugfix). That is smaller than Plan 2 (14 tasks
across two parts, ~3100 lines) and about the size of Plan 1 (6 tasks) plus a
third again — large, but not, on its own, past the point Plan 2 already
established as workable in one document. Every task here is independently
shippable and depends only on tasks earlier in this same list, so if review
finds it too large the natural split is at the boundary between backend and
frontend:

* **Part A — users, invitations, the last-admin rule** (Tasks 1–6): entirely
  backend, testable and mergeable while the frontend stays exactly as it is
  today.
* **Part B — the Settings screen, the workspace migration, and the wizard
  fix** (Tasks 7–10): frontend, plus the one bugfix, and depends on Part A's
  routes.

Kept as one document here, following Plan 2's own reasoning: splitting now
would mean numbering Part B's tasks before Part A has been reviewed, which is
premature. A reviewer should feel free to land Part A and ask for Part B to
be re-cut into its own plan if Part A's review changes anything Part B
assumes.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-20-user-management-design.md`. This
  plan's territory is §6 (invitations) and §8 (the workspace move), plus the
  last-admin rule in §5 and the two fixes the controller asked to be folded
  in (the break-glass condition, `updateChartByRef`). Read §5, §6, §8 and §9
  before starting.
- Model: `docs/superpowers/plans/2026-08-20-permissions-foundation.md` (Plan
  1) and `docs/superpowers/plans/2026-08-20-sign-in.md` (Plan 2) for form,
  voice and granularity — and because this plan extends, and must not
  contradict, what they actually built. **Both plans have already landed on
  this branch** (`git log` shows their commits through
  `892bbb3 fix(web): the provider buttons can be spaced, and are`) — this
  plan reads the real code, not the plan documents, wherever the two
  disagree; two places already do (see Task 1 and Task 6).
- Run tests with `.venv/bin/python -m pytest`, not `uv run` (that rebuilds
  into an env without pandas).
- "Run the whole suite" means `.venv/bin/python -m pytest tests/suite -q`.
  Baseline as of this writing: **1735 passed, 1 known live-consent failure
  (`test_delete_asks_for_consent_and_succeeds_once_granted`, needs a live
  hive), 2 skipped.**
- All persisted state — invitations, SMTP configuration, per-user workspace
  state — goes to datahive via `Repository`. Never an environment variable,
  `localStorage`, or a local file (spec §2).
- Paths are built only by `reportbuilder/store/paths.py` helpers — never an
  f-string at a call site.
- A grant scope is a datahive path prefix; `mode` is exactly `"view"` or
  `"edit"` (unchanged from Plan 1's `Grant`).
- Every route in `routes_users.py` is `require_admin`. Nothing here is
  reached by a data grant — administering access is not access (spec §5).
- Never echo a password or SMTP credential back from a `GET` — the same rule
  `routes_settings.py`'s `/settings/oidc` already follows for OIDC client
  secrets.
- The frontend has no automated test runner. Frontend tasks are verified
  with `cd web && npx tsc -b --noEmit` plus a written-out manual check, not
  an invented test file.

## File Structure

New:

| File | Responsibility |
|---|---|
| `src/reportbuilder/auth/users.py` | The last-admin rule: `remove_user`, `set_admin`. No I/O beyond `Repository` calls — testable as a specification, like `permissions.py`. |
| `src/reportbuilder/auth/mailer.py` | An injectable email transport (`smtplib`, standard library) and `settings/email.json`'s shape. No caller ever imports `smtplib` directly except this file. |
| `src/reportbuilder/auth/invites.py` | Create and revoke an invitation. Revoking an accepted one composes `users.remove_user`, so the last-admin rule applies there too. |
| `src/reportbuilder/api/routes_users.py` | The Users and Invitations HTTP surface. |
| `tests/suite/unit/auth/test_users.py` | The last-admin rule, in isolation. |
| `tests/suite/unit/auth/test_mailer.py` | Config parsing and the SMTP transport, against a fake `smtplib.SMTP` — no socket ever opens. |
| `tests/suite/unit/auth/test_invites.py` | Create/revoke, including the accepted-invite-removes-the-user composition. |
| `tests/suite/unit/store/test_repository_invites.py` | Invite CRUD against `Repository`. |
| `tests/suite/unit/store/test_repository_workspace.py` | Per-user workspace CRUD against `Repository`. |
| `tests/suite/integration/api/test_settings_email.py` | `GET`/`PUT /settings/email`. |
| `tests/suite/integration/api/test_users_api.py` | The whole Users/Invitations HTTP surface, including a real invite → register → grants-arrive → revoke round trip. |
| `tests/suite/integration/api/test_settings_workspace.py` | `GET`/`PUT /settings/workspace/{case_id}`, including cross-user isolation. |

Modified:

| File | Change |
|---|---|
| `src/reportbuilder/auth/identity.py` | Task 1: the break-glass condition. Task 5: consume a pending invite. |
| `src/reportbuilder/store/paths.py` | `invite_path`, `user_workspace_path`, their labels. |
| `src/reportbuilder/store/repository.py` | `Invite` dataclass and its CRUD; per-user workspace CRUD. |
| `src/reportbuilder/api/routes_auth.py` | Factor `public_origin(request)` out of `_callback_url` so the invite link can reuse it. |
| `src/reportbuilder/api/routes_settings.py` | `GET`/`PUT /settings/email`; `GET /settings/workspace`, `PUT /settings/workspace/{case_id}`. |
| `src/reportbuilder/api/app.py` | Register `users_router`. |
| `tests/suite/unit/auth/test_identity.py` | Task 1: rewrite two tests for the corrected break-glass condition. Task 5: a new class consuming an invite. |
| `web/src/lib/api.ts` | `WorkspaceCaseState`, `StudioUser`, `Invite` types; `api.settings.workspace`/`setCaseWorkspace`; `api.users.*`. |
| `web/src/lib/workspace.ts` | Full rewrite: backed by the API, not `localStorage`. |
| `web/src/lib/queries.ts` | `useUsers`, `useInvites`, `useUserActions`. |
| `web/src/pages/SettingsPage.tsx` | A Users tab. |
| `web/src/components/NewCaseDialog.tsx` | Its one workspace write moves off the old bare `setMaterial` import. |
| `web/src/pages/CaseDetailPage.tsx` | `clearWorkspace` becomes the `useClearWorkspace()` hook. |
| `web/src/components/wizard/ReportWizard.tsx` | `updateChartByRef` → `updateChartById`, keyed on `slide_id`. |
| `web/src/components/wizard/StepConfigure.tsx` | `aiPending` reads and `onEnsureTitles` keyed on `slide_id`. |

---

### Task 1: Break-glass fires when no ADMIN exists, not merely when no user does

**Files:**
- Modify: `src/reportbuilder/auth/identity.py`
- Modify: `tests/suite/unit/auth/test_identity.py`

**Interfaces:** unchanged — `resolve_signed_in_user(repo, auth, email, bootstrap_admins, *, email_domain_proven=True) -> User | SignInRefused`.

**The bug, read from the actual code (not the Plan 2 document, which
predates this landing):** `resolve_signed_in_user` currently gates the
bootstrap-admin branch on `not repo.list_users(auth)` — no users AT ALL.
Spec §3.1 promises recovery whenever **no admin** exists: "Losing every admin
... is recovered by setting [`NSIGHT_BOOTSTRAP_ADMINS`] again and signing
in." A hive that already has ordinary users — every domain-auto-joined
colleague is created with `is_admin=False` — is not "empty," so today's
condition refuses exactly the recovery the spec describes. Two existing
tests encode the WRONG rule and must be corrected, not merely supplemented:
`test_bootstrap_is_ignored_once_any_user_exists` (a non-admin user existing
should not block bootstrap) and `test_domain_auto_join_does_not_reactivate_bootstrap`
(a domain-auto-joined user is never an admin, so it can never have been
blocking bootstrap in the first place — under the corrected rule this
scenario is exactly when bootstrap SHOULD still fire).

- [ ] **Step 1: Rewrite the two wrong tests, and add the missing one**

In `tests/suite/unit/auth/test_identity.py`, replace this test:

```python
def test_bootstrap_is_ignored_once_any_user_exists(repo, auth):
    repo.save_user(auth, User(id="", email="someone@egoiq.com"))
    got = resolve_signed_in_user(repo, auth, "admin@egoiq.com", frozenset({"admin@egoiq.com"}))
    assert isinstance(got, SignInRefused)
```

with these two:

```python
def test_bootstrap_still_fires_once_a_non_admin_user_exists(repo, auth):
    """Spec §3.1's promise is recovery from NO ADMIN, not from an empty
    hive. A colleague who joined by domain auto-join, or any other
    non-admin record, must not block it."""
    repo.save_user(auth, User(id="", email="someone@egoiq.com", is_admin=False))
    got = resolve_signed_in_user(repo, auth, "admin@egoiq.com", frozenset({"admin@egoiq.com"}))
    assert isinstance(got, User)
    assert got.is_admin is True


def test_bootstrap_is_refused_once_a_real_admin_exists(repo, auth):
    repo.save_user(auth, User(id="", email="existing-admin@egoiq.com", is_admin=True))
    got = resolve_signed_in_user(repo, auth, "second@egoiq.com", frozenset({"second@egoiq.com"}))
    assert isinstance(got, SignInRefused)
```

And replace this test:

```python
def test_domain_auto_join_does_not_reactivate_bootstrap(repo, auth):
    """A hive with one real user is no longer "empty" even if that user came
    from domain auto-join, not the bootstrap path."""
    repo.set_setting(auth, "access.json", {"allowed_domains": ["egoiq.com"], "default_grants": []})
    resolve_signed_in_user(repo, auth, "first@egoiq.com", frozenset())
    got = resolve_signed_in_user(repo, auth, "admin@other.com", frozenset({"admin@other.com"}))
    assert isinstance(got, SignInRefused)
```

with:

```python
def test_domain_auto_join_does_not_block_bootstrap_recovery(repo, auth):
    """Corrected from the OLD "no users at all" rule: domain auto-join
    never creates an admin (spec §5), so a hive that has ONLY auto-joined
    users still has no admin, and NSIGHT_BOOTSTRAP_ADMINS must still be
    able to recover it (spec §3.1) -- this is the exact operational
    scenario the break-glass path exists for."""
    repo.set_setting(auth, "access.json", {"allowed_domains": ["egoiq.com"], "default_grants": []})
    resolve_signed_in_user(repo, auth, "first@egoiq.com", frozenset())
    got = resolve_signed_in_user(repo, auth, "admin@other.com", frozenset({"admin@other.com"}))
    assert isinstance(got, User)
    assert got.is_admin is True
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/suite/unit/auth/test_identity.py -q`
Expected: `test_bootstrap_still_fires_once_a_non_admin_user_exists`,
`test_bootstrap_is_refused_once_a_real_admin_exists`, and
`test_domain_auto_join_does_not_block_bootstrap_recovery` fail — the current
condition (`not repo.list_users(auth)`) refuses bootstrap the moment ANY
user exists, admin or not.

- [ ] **Step 3: Fix the condition**

In `src/reportbuilder/auth/identity.py`, add a helper right after the
`SignInRefused` dataclass:

```python
def _any_admin(repo: Repository, auth: AuthContext) -> bool:
    """Whether the hive already has at least one admin -- the actual
    condition spec §3.1 promises recovery from ("a hive with no ADMIN
    exists," not "no users at all"). A hive can easily have users with
    none of them admin: every domain-auto-joined user is created with
    is_admin=False (see the branch below), so a colleague joining first
    must never block the break-glass path an operator needs after losing
    every admin."""
    return any(u.is_admin for u in repo.list_users(auth))
```

Replace:

```python
    if not repo.list_users(auth) and normalized in bootstrap_admins:
```

with:

```python
    if not _any_admin(repo, auth) and normalized in bootstrap_admins:
```

Also update the module docstring's second paragraph — it currently only
frames invitations as "Plan 3," which is now this document; leave that
sentence for Task 5 to correct alongside the invite-consumption code it
introduces.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/auth/test_identity.py -q`
Expected: 17 passed (16 before this task, minus 2 rewritten in place, plus 1
new).

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures. `test_sign_in_flow.py`'s
`test_bootstrap_admin_signs_up_signs_in_acts_and_signs_out` still passes —
"no users at all" is a special case of "no admin exists," so the base case
is unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/reportbuilder/auth/identity.py tests/suite/unit/auth/test_identity.py
git commit -m "fix(auth): break-glass recovers a hive with no ADMIN, not only an empty one"
```

---

### Task 2: `auth/users.py` — the last-admin rule

**Files:**
- Create: `src/reportbuilder/auth/users.py`
- Test: `tests/suite/unit/auth/test_users.py`

**Interfaces:**
- Consumes: `User`, `Repository.get_user`/`list_users`/`save_user`/`delete_user`/`delete_sessions_for_user` (all exist).
- Produces: `LastAdminRefused(reason: str)`, `remove_user(repo, auth, user_id) -> LastAdminRefused | None`, `set_admin(repo, auth, user_id, is_admin) -> User | LastAdminRefused | None`.

Plan 1 left `delete_user` deliberately unguarded — "nothing calls
`delete_user` over HTTP yet." This is the rule that guards it before Task 6
wires it up, kept in its own module for the same reason `permissions.py` is
separate from `deps_auth.py`: it is worth reading — and reviewing — as a
security rule on its own, not mixed into request handling.

- [ ] **Step 1: Write the failing tests**

```python
# tests/suite/unit/auth/test_users.py
"""Removing and demoting users, and the last-admin rule that guards both
(spec §5): "the last admin cannot be removed or demoted."
"""
import pytest

from reportbuilder.auth import users
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


def _make(repo, auth, email, *, admin=False, grants=()):
    return repo.save_user(auth, User(id="", email=email, name=email.split("@")[0],
                                     is_admin=admin, grants=grants))


class TestRemoveUser:
    def test_removes_an_ordinary_user(self, repo, auth):
        u = _make(repo, auth, "a@x.c", grants=(Grant("attendo", "edit"),))
        assert users.remove_user(repo, auth, u.id) is None
        assert repo.get_user(auth, u.id) is None

    def test_removes_the_users_live_sessions_too(self, repo, auth):
        """Spec §7: deleting a user ends their session -- immediately here,
        not waiting on the idle timeout to catch up."""
        u = _make(repo, auth, "a@x.c")
        sid = repo.create_session(auth, u.id, lifetime_seconds=3600)
        users.remove_user(repo, auth, u.id)
        assert repo.get_session(auth, sid.id) is None

    def test_refuses_to_remove_the_last_admin(self, repo, auth):
        u = _make(repo, auth, "only-admin@x.c", admin=True)
        result = users.remove_user(repo, auth, u.id)
        assert isinstance(result, users.LastAdminRefused)
        assert repo.get_user(auth, u.id) is not None

    def test_removes_an_admin_when_another_admin_remains(self, repo, auth):
        _make(repo, auth, "keeps@x.c", admin=True)
        u = _make(repo, auth, "goes@x.c", admin=True)
        assert users.remove_user(repo, auth, u.id) is None
        assert repo.get_user(auth, u.id) is None

    def test_removing_an_unknown_user_is_a_no_op(self, repo, auth):
        assert users.remove_user(repo, auth, "usr-nope") is None


class TestSetAdmin:
    def test_promotes_an_ordinary_user(self, repo, auth):
        u = _make(repo, auth, "a@x.c")
        result = users.set_admin(repo, auth, u.id, True)
        assert isinstance(result, User) and result.is_admin is True

    def test_refuses_to_demote_the_last_admin(self, repo, auth):
        u = _make(repo, auth, "only-admin@x.c", admin=True)
        result = users.set_admin(repo, auth, u.id, False)
        assert isinstance(result, users.LastAdminRefused)
        assert repo.get_user(auth, u.id).is_admin is True

    def test_demotes_one_of_two_admins(self, repo, auth):
        _make(repo, auth, "keeps@x.c", admin=True)
        u = _make(repo, auth, "goes@x.c", admin=True)
        result = users.set_admin(repo, auth, u.id, False)
        assert isinstance(result, User) and result.is_admin is False

    def test_demoting_preserves_grants(self, repo, auth):
        _make(repo, auth, "keeps@x.c", admin=True)
        u = _make(repo, auth, "goes@x.c", admin=True, grants=(Grant("attendo", "view"),))
        users.set_admin(repo, auth, u.id, False)
        assert repo.get_user(auth, u.id).grants == (Grant("attendo", "view"),)

    def test_setting_admin_on_an_unknown_user_is_none(self, repo, auth):
        assert users.set_admin(repo, auth, "usr-nope", True) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/suite/unit/auth/test_users.py -q`
Expected: `ModuleNotFoundError: No module named 'reportbuilder.auth.users'`.

- [ ] **Step 3: Write the implementation**

```python
# src/reportbuilder/auth/users.py
"""Removing and demoting users, and the one rule that guards both (spec
§5): "the last admin cannot be removed or demoted."

Admin is a flag, not a grant (permissions.py), and it is the ONLY thing
that lets someone reach the Users screen at all. Losing every admin locks
the tenant out of granting, revoking or inviting anyone -- recoverable
only via NSIGHT_BOOTSTRAP_ADMINS and a server restart (spec §3.1). This
module is what stops that from happening by accident, from either of the
two routes that can cause it: routes_users.py's own remove/demote
controls, and invites.py's "revoking an accepted invitation removes the
user" (spec §6), which is why THAT function calls into this one rather
than deleting the user itself.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from reportbuilder.auth.permissions import User
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@dataclass(frozen=True)
class LastAdminRefused:
    """Spec §5: "refused, with the reason." `reason` is what the route
    turns into a 409 -- see routes_users.py."""
    reason: str


def _admin_count(repo: Repository, auth: AuthContext) -> int:
    return sum(1 for u in repo.list_users(auth) if u.is_admin)


def remove_user(repo: Repository, auth: AuthContext,
                user_id: str) -> "LastAdminRefused | None":
    """Delete *user_id*, their grants, their password and every live
    session of theirs (spec §7: "deleting a user...ends it" -- sessions
    are dropped here too, rather than left to the ordinary idle timeout,
    so revocation does not wait on the 30s resolution cache the way a
    plain sign-out would). A user already gone is a no-op, not an error --
    the route this backs is naturally idempotent under a double-click.
    """
    user = repo.get_user(auth, user_id)
    if user is None:
        return None
    if user.is_admin and _admin_count(repo, auth) <= 1:
        return LastAdminRefused("the last admin cannot be removed")
    repo.delete_sessions_for_user(auth, user_id)
    repo.delete_user(auth, user_id)
    return None


def set_admin(repo: Repository, auth: AuthContext, user_id: str,
              is_admin: bool) -> "User | LastAdminRefused | None":
    """Promote or demote. Promoting never needs the rule below -- only
    dropping the LAST admin's flag does."""
    user = repo.get_user(auth, user_id)
    if user is None:
        return None
    if user.is_admin and not is_admin and _admin_count(repo, auth) <= 1:
        return LastAdminRefused("the last admin cannot be demoted")
    updated = replace(user, is_admin=is_admin)
    repo.save_user(auth, updated)
    return updated
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/auth/test_users.py -q`
Expected: 11 passed.

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/reportbuilder/auth/users.py tests/suite/unit/auth/test_users.py
git commit -m "feat(auth): the last-admin rule — removal and demotion, refused with the reason"
```

---

### Task 3: Invitations in datahive

**Files:**
- Modify: `src/reportbuilder/store/paths.py`
- Modify: `src/reportbuilder/store/repository.py`
- Test: `tests/suite/unit/store/test_repository_invites.py`

**Interfaces:**
- Consumes: `Grant`, `_new_id`, `_now`, `_write_json`/`_read_json` (all exist).
- Produces: `Invite(id, email, grants, invited_by, invited_at, expires, accepted_user_id, accepted_at)`,
  `Repository.create_invite(auth, email, grants, invited_by, lifetime_seconds) -> Invite`,
  `.get_invite`, `.list_invites`, `.find_pending_invite_by_email`,
  `.mark_invite_accepted`, `.delete_invite`.

The record persists PAST acceptance — this is what makes spec §6's
"revoking an accepted invitation removes the user" possible at all in
Task 5: `revoke_invitation` needs to know WHICH user an invite became.

- [ ] **Step 1: Write the failing tests**

```python
# tests/suite/unit/store/test_repository_invites.py
"""Invitations, stored in datahive (spec §6, §9): an admin adds someone by
email, and this record is what "pending" / "accepted" MEANS.
"""
import pytest

from reportbuilder.auth.permissions import Grant
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


def test_a_created_invite_comes_back_whole(repo, auth):
    inv = repo.create_invite(auth, "Maija@Egoiq.com", (Grant("attendo", "view"),),
                             "usr-admin", lifetime_seconds=3600)
    assert inv.id and inv.email == "maija@egoiq.com"  # normalized, like find_user_by_email
    got = repo.get_invite(auth, inv.id)
    assert got.grants == (Grant("attendo", "view"),)
    assert got.invited_by == "usr-admin"
    assert got.accepted_user_id is None


def test_an_unknown_invite_id_is_none_not_an_error(repo, auth):
    assert repo.get_invite(auth, "inv-nope") is None


def test_listing_returns_every_invite_newest_first(repo, auth):
    first = repo.create_invite(auth, "a@x.c", (), "admin", lifetime_seconds=3600)
    second = repo.create_invite(auth, "b@x.c", (), "admin", lifetime_seconds=3600)
    assert [i.id for i in repo.list_invites(auth)] == [second.id, first.id]


def test_a_pending_invite_is_found_by_email(repo, auth):
    inv = repo.create_invite(auth, "a@x.c", (), "admin", lifetime_seconds=3600)
    found = repo.find_pending_invite_by_email(auth, "A@X.C")
    assert found is not None and found.id == inv.id


def test_an_accepted_invite_is_no_longer_pending(repo, auth):
    inv = repo.create_invite(auth, "a@x.c", (), "admin", lifetime_seconds=3600)
    repo.mark_invite_accepted(auth, inv.id, "usr-1")
    assert repo.find_pending_invite_by_email(auth, "a@x.c") is None
    got = repo.get_invite(auth, inv.id)
    assert got.accepted_user_id == "usr-1" and got.accepted_at


def test_an_expired_invite_is_not_pending(repo, auth):
    inv = repo.create_invite(auth, "a@x.c", (), "admin", lifetime_seconds=-1)
    assert repo.find_pending_invite_by_email(auth, "a@x.c") is None
    # Still readable directly -- expiry only changes whether sign-in matches it.
    assert repo.get_invite(auth, inv.id) is not None


def test_deleting_an_invite_removes_it(repo, auth):
    inv = repo.create_invite(auth, "a@x.c", (), "admin", lifetime_seconds=3600)
    repo.delete_invite(auth, inv.id)
    assert repo.get_invite(auth, inv.id) is None


def test_deleting_an_unknown_invite_does_nothing(repo, auth):
    repo.delete_invite(auth, "inv-nope")  # no raise


def test_marking_an_unknown_invite_accepted_does_nothing(repo, auth):
    repo.mark_invite_accepted(auth, "inv-nope", "usr-1")  # no raise
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/suite/unit/store/test_repository_invites.py -q`
Expected: `AttributeError: 'Repository' object has no attribute 'create_invite'`.

- [ ] **Step 3: Add the path**

In `src/reportbuilder/store/paths.py`, add to the label block (after
`LABEL_PASSWORD`):

```python
LABEL_INVITE = "nsight:invite"
```

and after `session_path`:

```python
def invite_path(invite_id: str) -> str:
    return f"{SETTINGS_ROOT}/invite/{_seg(invite_id, 'invite_id')}"
```

and to the module docstring's map, beneath `settings/session/{session_id}`:

```
    settings/invite/{invite_id}                       nsight:invite
```

- [ ] **Step 4: Add the `Invite` dataclass and repository methods**

In `src/reportbuilder/store/repository.py`, near `Session`:

```python
@dataclass(frozen=True)
class Invite:
    id: str
    email: str
    grants: tuple[Grant, ...]
    invited_by: str
    invited_at: str
    expires: str
    accepted_user_id: str | None = None
    accepted_at: str | None = None
```

Immediately after the sessions section (after `delete_sessions_for_user`):

```python
    # --- invitations ----------------------------------------------------------
    #
    # An admin adds someone by email (spec §6). The record persists PAST
    # acceptance -- accepted_user_id/accepted_at, once set, are what lets
    # auth.invites.revoke_invitation remove the resulting user when an
    # accepted invite is revoked. Never deleted on acceptance; only on an
    # explicit revoke (delete_invite).

    def create_invite(self, auth: AuthContext, email: str, grants,
                      invited_by: str, lifetime_seconds: int) -> Invite:
        iid = _new_id("inv")
        now = _now()
        expires = (datetime.now(timezone.utc) + timedelta(seconds=lifetime_seconds)) \
            .isoformat(timespec="seconds")
        normalized = (email or "").strip().lower()
        self._write_json(auth, P.invite_path(iid),
                         {"id": iid, "email": normalized,
                          "grants": [{"scope": g.scope, "mode": g.mode} for g in grants],
                          "invited_by": invited_by, "invited_at": now, "expires": expires,
                          "accepted_user_id": None, "accepted_at": None},
                         [P.LABEL_INVITE])
        return Invite(id=iid, email=normalized, grants=tuple(grants),
                      invited_by=invited_by, invited_at=now, expires=expires)

    def _invite_from(self, d: dict) -> Invite:
        return Invite(id=d["id"], email=d.get("email", ""),
                      grants=tuple(Grant(g["scope"], g.get("mode", "view"))
                                  for g in d.get("grants", []) if g.get("scope")),
                      invited_by=d.get("invited_by", ""), invited_at=d.get("invited_at", ""),
                      expires=d.get("expires", ""),
                      accepted_user_id=d.get("accepted_user_id"),
                      accepted_at=d.get("accepted_at"))

    def get_invite(self, auth: AuthContext, invite_id: str) -> "Invite | None":
        try:
            d = self._read_json(auth, P.invite_path(invite_id))
        except (NotFound, ValueError, UnicodeDecodeError):
            return None
        return self._invite_from(d)

    def list_invites(self, auth: AuthContext) -> list[Invite]:
        out = []
        for info in self.store.list(auth, P.SETTINGS_ROOT + "/", labels=[P.LABEL_INVITE]):
            invite = self.get_invite(auth, info.path.rsplit("/", 1)[-1])
            if invite is not None:
                out.append(invite)
        # Newest first: an admin cares most about what was just sent.
        return sorted(out, key=lambda i: i.invited_at, reverse=True)

    def find_pending_invite_by_email(self, auth: AuthContext, email: str) -> "Invite | None":
        """The live invitation for *email*, if any: not yet accepted, not
        yet expired. Sign-in has a verified email and nothing else -- same
        shape as find_user_by_email."""
        wanted = (email or "").strip().lower()
        if not wanted:
            return None
        now = _now()
        return next((i for i in self.list_invites(auth)
                    if i.email == wanted and i.accepted_user_id is None and i.expires > now),
                   None)

    def mark_invite_accepted(self, auth: AuthContext, invite_id: str, user_id: str) -> None:
        invite = self.get_invite(auth, invite_id)
        if invite is None:
            return
        self._write_json(auth, P.invite_path(invite_id),
                         {"id": invite.id, "email": invite.email,
                          "grants": [{"scope": g.scope, "mode": g.mode} for g in invite.grants],
                          "invited_by": invite.invited_by, "invited_at": invite.invited_at,
                          "expires": invite.expires, "accepted_user_id": user_id,
                          "accepted_at": _now()},
                         [P.LABEL_INVITE])

    def delete_invite(self, auth: AuthContext, invite_id: str) -> None:
        try:
            self.store.delete(auth, P.invite_path(invite_id))
        except NotFound:
            pass
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/store/test_repository_invites.py -q`
Expected: 9 passed.

- [ ] **Step 6: Run the whole suite**

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures.

- [ ] **Step 7: Commit**

```bash
git add src/reportbuilder/store/paths.py src/reportbuilder/store/repository.py tests/suite/unit/store/test_repository_invites.py
git commit -m "feat(store): invitations live in datahive"
```

---

### Task 4: Sending mail — an injectable transport, and where it's configured

**Files:**
- Create: `src/reportbuilder/auth/mailer.py`
- Modify: `src/reportbuilder/api/routes_settings.py`
- Test: `tests/suite/unit/auth/test_mailer.py`
- Test: `tests/suite/integration/api/test_settings_email.py`

**Interfaces:**
- Produces: `EmailConfig`, `config_from_settings(stored: dict) -> EmailConfig | None`,
  `Sender = Callable[[EmailConfig, str, str, str], bool]`, `send_via_smtp: Sender`.

**What this repo already has, checked before writing this task:** nothing.
`grep -rIl "smtplib\|import email\|from email"` across `src/` and `pyproject.toml`
finds no hit; the only matches for `smtp`/`mail`/`ses` in the tree are
unrelated substrings (`expenses`, `increases`, `EGOHIVE_EMAIL`, a management
credential for datahive's own API, nothing to do with sending mail).
`pyproject.toml`'s `dependencies` list has no mail library. Spec §6: "Email
is sent by nSight through a provider configured in `settings/email.json` —
SMTP or an API provider." The smallest thing that works is SMTP via
`smtplib`, which is the Python standard library — no new dependency. If an
API provider is ever needed, it is a second function next to
`send_via_smtp`, not a rewrite of this module's shape.

- [ ] **Step 1: Write the failing unit tests**

```python
# tests/suite/unit/auth/test_mailer.py
"""Sending nSight's own mail (spec §6): config from datahive, and a
transport that must never raise -- see the module docstring.
"""
import smtplib

import pytest

from reportbuilder.auth import mailer


def test_no_config_at_all_is_none():
    assert mailer.config_from_settings({}) is None
    assert mailer.config_from_settings(None) is None


def test_missing_from_addr_is_none():
    assert mailer.config_from_settings({"host": "smtp.example.com"}) is None


def test_a_full_config_parses():
    cfg = mailer.config_from_settings({
        "host": "smtp.example.com", "port": 2525, "username": "u", "password": "p",
        "from_addr": "nsight@example.com", "use_tls": False})
    assert cfg == mailer.EmailConfig(host="smtp.example.com", port=2525, username="u",
                                     password="p", from_addr="nsight@example.com",
                                     use_tls=False)


def test_port_and_tls_default():
    cfg = mailer.config_from_settings({"host": "smtp.example.com", "from_addr": "a@b.c"})
    assert cfg.port == 587 and cfg.use_tls is True


class _FakeSMTP:
    """Records what would have been sent. Opens no socket."""
    instances: list = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.started_tls = False
        self.logged_in = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, username, password):
        self.logged_in = (username, password)

    def send_message(self, msg):
        self.sent = msg


@pytest.fixture(autouse=True)
def _reset_fake():
    _FakeSMTP.instances.clear()
    yield


def test_send_via_smtp_talks_to_the_configured_server(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    cfg = mailer.EmailConfig(host="smtp.example.com", port=587, username="u", password="p",
                             from_addr="nsight@example.com", use_tls=True)
    ok = mailer.send_via_smtp(cfg, "to@example.com", "Subject line", "Body text")
    assert ok is True
    [smtp] = _FakeSMTP.instances
    assert smtp.started_tls is True
    assert smtp.logged_in == ("u", "p")
    assert smtp.sent["To"] == "to@example.com"
    assert smtp.sent["Subject"] == "Subject line"


def test_send_via_smtp_skips_login_with_no_username(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    cfg = mailer.EmailConfig(host="h", port=25, username="", password="",
                             from_addr="a@b.c", use_tls=False)
    mailer.send_via_smtp(cfg, "to@example.com", "S", "B")
    [smtp] = _FakeSMTP.instances
    assert smtp.logged_in is None and smtp.started_tls is False


def test_send_via_smtp_never_raises_on_failure(monkeypatch):
    class _Boom:
        def __init__(self, *a, **k):
            raise OSError("connection refused")
    monkeypatch.setattr(smtplib, "SMTP", _Boom)
    cfg = mailer.EmailConfig(host="h", port=25, username="", password="",
                             from_addr="a@b.c", use_tls=False)
    assert mailer.send_via_smtp(cfg, "to@example.com", "S", "B") is False
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/suite/unit/auth/test_mailer.py -q`
Expected: `ModuleNotFoundError: No module named 'reportbuilder.auth.mailer'`.

- [ ] **Step 3: Write `mailer.py`**

```python
# src/reportbuilder/auth/mailer.py
"""Sending nSight's own mail -- today, just an invitation link (spec §6).

No mail-provider dependency: smtplib is the standard library, and this is
the ONE kind of email nSight sends. Configuration lives in datahive
(`settings/email.json`, spec §9) rather than an environment variable, so
moving hive moves the mail setup with it (spec §2). If a second kind of
email is ever needed, an API-provider transport is a second function next
to send_via_smtp, not a rewrite of this module's shape.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable

log = logging.getLogger(__name__)

EMAIL_KEY = "email.json"


@dataclass(frozen=True)
class EmailConfig:
    host: str
    port: int
    username: str
    password: str
    from_addr: str
    use_tls: bool = True


def config_from_settings(stored: dict | None) -> "EmailConfig | None":
    """*stored* is whatever `Repository.get_setting(auth, EMAIL_KEY)`
    returns. None when unconfigured -- a caller with no config must send
    nothing, not raise (spec §6: "delivery may fail without failing the
    invitation")."""
    if not stored or not stored.get("host") or not stored.get("from_addr"):
        return None
    return EmailConfig(
        host=stored["host"],
        port=int(stored.get("port") or 587),
        username=stored.get("username", ""),
        password=stored.get("password", ""),
        from_addr=stored["from_addr"],
        use_tls=bool(stored.get("use_tls", True)),
    )


#: (config, to, subject, body) -> True if the message was handed to the
#: server successfully. Injected everywhere email is sent, so a test never
#: opens a real socket -- see auth/invites.py.
Sender = Callable[[EmailConfig, str, str, str], bool]


def send_via_smtp(config: EmailConfig, to: str, subject: str, body: str) -> bool:
    """The real transport. Never raises -- a delivery failure must not
    fail the invitation it was sent for (spec §6); the caller decides what
    False means for the UI (`emailed: false` plus the link to copy)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.from_addr
    msg["To"] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP(config.host, config.port, timeout=10) as smtp:
            if config.use_tls:
                smtp.starttls(context=ssl.create_default_context())
            if config.username:
                smtp.login(config.username, config.password)
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        log.warning("invitation email to '%s' could not be sent: %s", to, exc)
        return False
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/auth/test_mailer.py -q`
Expected: 8 passed.

- [ ] **Step 5: Write the failing settings-route tests**

```python
# tests/suite/integration/api/test_settings_email.py
"""GET/PUT /settings/email -- where the SMTP transport for invitations
(spec §6) is configured."""
import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext
from suite._helpers import sign_in_override

pytestmark = pytest.mark.integration


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def admin_client(repo, auth):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(repo, auth, admin=True)
    return TestClient(app)


@pytest.fixture
def viewer_client(repo, auth):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(repo, auth, admin=False)
    return TestClient(app)


def test_defaults_to_unconfigured(admin_client):
    r = admin_client.get("/settings/email")
    assert r.status_code == 200
    assert r.json()["configured"] is False


def test_admin_can_set_it(admin_client):
    body = {"host": "smtp.example.com", "port": 2525, "username": "u",
           "password": "s3cr3t", "from_addr": "nsight@example.com", "use_tls": True}
    r = admin_client.put("/settings/email", json=body)
    assert r.status_code == 200
    got = r.json()
    assert got["configured"] is True
    assert "password" not in got  # never echoed back


def test_saving_again_with_no_password_keeps_the_stored_one(admin_client):
    admin_client.put("/settings/email", json={
        "host": "smtp.example.com", "from_addr": "nsight@example.com", "password": "s3cr3t"})
    admin_client.put("/settings/email", json={
        "host": "smtp.example.com", "from_addr": "nsight@example.com", "port": 465})
    assert admin_client.get("/settings/email").json()["configured"] is True


def test_missing_host_is_rejected(admin_client):
    r = admin_client.put("/settings/email", json={"from_addr": "a@b.c"})
    assert r.status_code == 422


def test_a_non_admin_cannot_read_or_write_it(viewer_client):
    assert viewer_client.get("/settings/email").status_code == 403
    assert viewer_client.put("/settings/email", json={}).status_code == 403
```

- [ ] **Step 6: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_settings_email.py -q`
Expected: 404s — the routes do not exist yet.

- [ ] **Step 7: Add the routes**

In `src/reportbuilder/api/routes_settings.py`, add the import
`from reportbuilder.auth import mailer` and, near `ACCESS_KEY`:

```python
@settings_router.get("/settings/email")
def get_email_settings(auth: AuthContext = Depends(get_auth),
                       repo: Repository = Depends(get_repository),
                       user: User = Depends(require_admin)) -> dict:
    """Whether and how nSight sends invitation email (spec §6). Never
    echoes the password -- see get_oidc's identical rule for client
    secrets."""
    stored = repo.get_setting(auth, mailer.EMAIL_KEY) or {}
    return {"host": stored.get("host", ""), "port": stored.get("port", 587),
            "username": stored.get("username", ""), "from_addr": stored.get("from_addr", ""),
            "use_tls": stored.get("use_tls", True),
            "configured": mailer.config_from_settings(stored) is not None}


@settings_router.put("/settings/email")
def put_email_settings(payload: dict = Body(...),
                       auth: AuthContext = Depends(get_auth),
                       repo: Repository = Depends(get_repository),
                       user: User = Depends(require_admin)) -> dict:
    host = (payload.get("host") or "").strip()
    from_addr = (payload.get("from_addr") or "").strip()
    if not host or not from_addr:
        raise HTTPException(422, "host and from_addr are required")
    stored = repo.get_setting(auth, mailer.EMAIL_KEY) or {}
    value = {"host": host, "port": int(payload.get("port") or 587),
            "username": payload.get("username", ""),
            # An empty password in the payload means "leave the stored one
            # alone" -- the GET above never echoes it back, so a save that
            # round-trips the form would otherwise blank it out.
            "password": payload.get("password") or stored.get("password", ""),
            "from_addr": from_addr, "use_tls": bool(payload.get("use_tls", True))}
    repo.set_setting(auth, mailer.EMAIL_KEY, value)
    return {**{k: v for k, v in value.items() if k != "password"},
            "configured": mailer.config_from_settings(value) is not None}
```

- [ ] **Step 8: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_settings_email.py -q`
Expected: 5 passed.

- [ ] **Step 9: Run the whole suite**

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures.

- [ ] **Step 10: Commit**

```bash
git add src/reportbuilder/auth/mailer.py src/reportbuilder/api/routes_settings.py tests/suite/unit/auth/test_mailer.py tests/suite/integration/api/test_settings_email.py
git commit -m "feat(auth): an injectable SMTP transport, configured in settings/email.json"
```

---

### Task 5: `auth/invites.py` — creating and revoking an invitation, and consuming one at sign-in

**Files:**
- Create: `src/reportbuilder/auth/invites.py`
- Modify: `src/reportbuilder/auth/identity.py`
- Test: `tests/suite/unit/auth/test_invites.py`
- Test: `tests/suite/unit/auth/test_identity.py` (add a class)

**Interfaces:**
- Consumes: `Repository.create_invite`/`get_invite`/`find_pending_invite_by_email`/
  `mark_invite_accepted`/`delete_invite` (Task 3); `mailer.config_from_settings`/`send_via_smtp` (Task 4);
  `users.remove_user`/`LastAdminRefused` (Task 2).
- Produces: `Invitation(invite, link, emailed)`, `create_invitation(repo, auth, *, email, grants, invited_by, login_url, sender=send_via_smtp) -> Invitation`,
  `revoke_invitation(repo, auth, invite_id) -> LastAdminRefused | None`.

- [ ] **Step 1: Write the failing tests for `invites.py`**

```python
# tests/suite/unit/auth/test_invites.py
"""Creating and revoking an invitation (spec §6): the record, the email
attempt, and what revoking an ACCEPTED one does differently.
"""
import pytest

from reportbuilder.auth import invites, users
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
def admin(repo, auth):
    return repo.save_user(auth, User(id="", email="admin@egoiq.com", name="Admin", is_admin=True))


def _fake_sender(calls):
    def _sender(config, to, subject, body):
        calls.append((config, to, subject, body))
        return True
    return _sender


class TestCreateInvitation:
    def test_records_the_invite_with_its_grants(self, repo, auth, admin):
        result = invites.create_invitation(
            repo, auth, email="new@egoiq.com", grants=(Grant("attendo", "view"),),
            invited_by=admin, login_url="https://studio.example.com/login",
            sender=_fake_sender([]))
        assert result.invite.email == "new@egoiq.com"
        assert result.invite.grants == (Grant("attendo", "view"),)
        assert repo.get_invite(auth, result.invite.id) is not None

    def test_emails_when_a_transport_is_configured(self, repo, auth, admin):
        repo.set_setting(auth, "email.json",
                         {"host": "smtp.example.com", "from_addr": "nsight@example.com"})
        calls = []
        result = invites.create_invitation(
            repo, auth, email="new@egoiq.com", grants=(), invited_by=admin,
            login_url="https://studio.example.com/login", sender=_fake_sender(calls))
        assert result.emailed is True
        assert calls[0][1] == "new@egoiq.com"
        assert "https://studio.example.com/login" in calls[0][3]

    def test_the_link_is_studios_own_login_never_datahives(self, repo, auth, admin):
        """The task's own words: "the link to nSight Studio login," not a
        datahive link (spec D5)."""
        result = invites.create_invitation(
            repo, auth, email="new@egoiq.com", grants=(), invited_by=admin,
            login_url="https://studio.example.com/login", sender=_fake_sender([]))
        assert result.link == "https://studio.example.com/login"

    def test_no_transport_configured_is_recorded_but_not_emailed(self, repo, auth, admin):
        """Spec §6: "delivery may fail without failing the invitation" --
        the record exists either way."""
        result = invites.create_invitation(
            repo, auth, email="new@egoiq.com", grants=(), invited_by=admin,
            login_url="https://studio.example.com/login", sender=_fake_sender([]))
        assert result.emailed is False
        assert repo.get_invite(auth, result.invite.id) is not None

    def test_a_failed_send_is_also_not_a_failed_invitation(self, repo, auth, admin):
        repo.set_setting(auth, "email.json",
                         {"host": "smtp.example.com", "from_addr": "nsight@example.com"})
        result = invites.create_invitation(
            repo, auth, email="new@egoiq.com", grants=(), invited_by=admin,
            login_url="https://studio.example.com/login", sender=lambda *a: False)
        assert result.emailed is False
        assert repo.get_invite(auth, result.invite.id) is not None


class TestRevokeInvitation:
    def test_revoking_a_pending_invite_deletes_it(self, repo, auth, admin):
        inv = repo.create_invite(auth, "new@egoiq.com", (), admin.id, lifetime_seconds=3600)
        assert invites.revoke_invitation(repo, auth, inv.id) is None
        assert repo.get_invite(auth, inv.id) is None

    def test_revoking_an_unknown_invite_is_a_no_op(self, repo, auth):
        assert invites.revoke_invitation(repo, auth, "inv-nope") is None

    def test_revoking_an_accepted_invite_removes_the_user_too(self, repo, auth, admin):
        inv = repo.create_invite(auth, "new@egoiq.com", (Grant("attendo", "edit"),),
                                 admin.id, lifetime_seconds=3600)
        accepted = repo.save_user(auth, User(id="", email="new@egoiq.com",
                                             grants=(Grant("attendo", "edit"),)))
        repo.mark_invite_accepted(auth, inv.id, accepted.id)
        result = invites.revoke_invitation(repo, auth, inv.id)
        assert result is None
        assert repo.get_invite(auth, inv.id) is None
        assert repo.get_user(auth, accepted.id) is None

    def test_revoking_an_accepted_invite_still_obeys_the_last_admin_rule(self, repo, auth):
        """Composed from users.remove_user, not reimplemented -- so this
        rule cannot be bypassed by going through "revoke" instead of
        "remove"."""
        inviter = repo.save_user(auth, User(id="", email="inviter@egoiq.com", is_admin=True))
        inv = repo.create_invite(auth, "onlyadmin@egoiq.com", (), inviter.id, lifetime_seconds=3600)
        accepted = repo.save_user(auth, User(id="", email="onlyadmin@egoiq.com", is_admin=True))
        repo.mark_invite_accepted(auth, inv.id, accepted.id)
        repo.delete_user(auth, inviter.id)  # now `accepted` is the ONLY admin

        result = invites.revoke_invitation(repo, auth, inv.id)
        assert isinstance(result, users.LastAdminRefused)
        assert repo.get_user(auth, accepted.id) is not None
        assert repo.get_invite(auth, inv.id) is not None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/suite/unit/auth/test_invites.py -q`
Expected: `ModuleNotFoundError: No module named 'reportbuilder.auth.invites'`.

- [ ] **Step 3: Write `invites.py`**

```python
# src/reportbuilder/auth/invites.py
"""Inviting someone to nSight Studio by email, and consuming that
invitation on their first sign-in (spec §6).

Every step after create_invitation runs through identity.py: an
invitation only ever gets APPLIED when the invited address itself signs
in and its verified email matches -- see resolve_signed_in_user's
consumption branch, added alongside this module.
"""
from __future__ import annotations

from dataclasses import dataclass

from reportbuilder.auth import mailer, users
from reportbuilder.auth.mailer import Sender, send_via_smtp
from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store.repository import Invite, Repository
from reportbuilder.store.seam import AuthContext

DEFAULT_LIFETIME_SECONDS = 14 * 24 * 3600  # spec §6: "default 14 days"

_SUBJECT = "You've been invited to nSight Studio"


def _body(invited_by_email: str, link: str) -> str:
    return (
        f"{invited_by_email} has invited you to nSight Studio.\n\n"
        f"Sign in here: {link}\n\n"
        "This link is not a password -- sign in with your own Google or "
        "Microsoft account, or a password you set for this address, and "
        "your access is ready.\n"
    )


@dataclass(frozen=True)
class Invitation:
    invite: Invite
    link: str
    emailed: bool


def create_invitation(repo: Repository, auth: AuthContext, *, email: str,
                      grants: tuple[Grant, ...], invited_by: User,
                      login_url: str, sender: Sender = send_via_smtp) -> Invitation:
    """Record the invitation, then try to send it. Spec §6: "delivery may
    fail without failing the invitation" -- the record exists either way;
    only `emailed` says whether the admin also needs to copy the link by
    hand."""
    invite = repo.create_invite(auth, email, grants, invited_by.id,
                                lifetime_seconds=DEFAULT_LIFETIME_SECONDS)
    config = mailer.config_from_settings(repo.get_setting(auth, mailer.EMAIL_KEY) or {})
    emailed = (config is not None
              and sender(config, invite.email, _SUBJECT, _body(invited_by.email, login_url)))
    return Invitation(invite=invite, link=login_url, emailed=emailed)


def revoke_invitation(repo: Repository, auth: AuthContext,
                      invite_id: str) -> "users.LastAdminRefused | None":
    """Delete a pending invite outright. For an ACCEPTED one, spec §6:
    "revoking an accepted invitation removes the user" -- routed through
    users.remove_user so the last-admin rule applies here too, not just on
    the Users list's own remove button."""
    invite = repo.get_invite(auth, invite_id)
    if invite is None:
        return None
    if invite.accepted_user_id:
        refused = users.remove_user(repo, auth, invite.accepted_user_id)
        if refused is not None:
            return refused
    repo.delete_invite(auth, invite_id)
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/auth/test_invites.py -q`
Expected: 9 passed.

- [ ] **Step 5: Wire consumption into `identity.py`**

`identity.py` already carries a note, left by Plan 2, marking exactly where
this goes. Read the file before editing — the note is still there.

Replace:

```python
    existing = repo.find_user_by_email(auth, normalized)
    if existing is not None:
        return existing

    # NOTE for whoever implements Plan 3 (pending invitations): consuming an
    # invitation belongs ABOVE this guard, not below it. Fulfilling an
    # invitation an admin already issued for this exact email is not "minting
    # an account from an unproven claim" the way bootstrap-admin/domain
    # auto-join below are -- it is closer to "matches an existing record",
    # same as the `existing` check above, and the task spec for xms_edov
    # explicitly allows it.
    if not email_domain_proven:
```

with:

```python
    existing = repo.find_user_by_email(auth, normalized)
    if existing is not None:
        return existing

    # A pending invitation is fulfilled here, ABOVE the email_domain_proven
    # guard below -- consuming one an admin already issued for this exact
    # address is not "minting an account from an unproven claim" the way
    # bootstrap-admin/domain auto-join further down are; it is closer to
    # "matches an existing record", same as the `existing` check just
    # above, and this is exactly the carve-out the xms_edov design allowed
    # for (see oidc.py's module docstring).
    pending = repo.find_pending_invite_by_email(auth, normalized)
    if pending is not None:
        user = repo.save_user(auth, User(id="", email=normalized,
                                         name=normalized.split("@", 1)[0],
                                         is_admin=False, grants=pending.grants))
        repo.mark_invite_accepted(auth, pending.id, user.id)
        log.info("sign-in: '%s' accepted its invitation (%s)", normalized, pending.id)
        return user

    if not email_domain_proven:
```

Also update the module docstring — replace:

```
Invitations (spec §4's middle branch, "a pending invitation -- consume it")
are Plan 3: no settings/invite/* record exists yet, so there is nothing for
that branch to consume. Until then, a new user's only way in is the
bootstrap admin or an allowed domain.
```

with:

```
Invitations (spec §4's middle branch, "a pending invitation -- consume it")
are handled below, right after the `existing`-user check: an admin-issued
invite for this exact address is fulfilled before bootstrap-admin or
domain auto-join ever get a look, and email_domain_proven never gates it
(see the comment at that branch).
```

- [ ] **Step 6: Add the invitation-consumption tests**

Append to `tests/suite/unit/auth/test_identity.py`:

```python
class TestInvitationConsumption:
    def test_a_pending_invite_creates_the_user_with_its_grants(self, repo, auth):
        repo.create_invite(auth, "new@egoiq.com", (Grant("attendo", "edit"),),
                           "usr-admin", lifetime_seconds=3600)
        got = resolve_signed_in_user(repo, auth, "new@egoiq.com", frozenset())
        assert isinstance(got, User)
        assert got.is_admin is False
        assert got.grants == (Grant("attendo", "edit"),)

    def test_consuming_marks_the_invite_accepted(self, repo, auth):
        inv = repo.create_invite(auth, "new@egoiq.com", (), "usr-admin", lifetime_seconds=3600)
        got = resolve_signed_in_user(repo, auth, "new@egoiq.com", frozenset())
        stored = repo.get_invite(auth, inv.id)
        assert stored.accepted_user_id == got.id

    def test_an_expired_invite_is_not_consumed(self, repo, auth):
        repo.create_invite(auth, "new@egoiq.com", (), "usr-admin", lifetime_seconds=-1)
        got = resolve_signed_in_user(repo, auth, "new@egoiq.com", frozenset())
        assert isinstance(got, SignInRefused)

    def test_an_invite_is_consumed_even_when_the_email_domain_is_unproven(self, repo, auth):
        """The xms_edov carve-out this branch was written for: an admin
        already vetted this exact address by inviting it."""
        repo.create_invite(auth, "new@egoiq.com", (Grant("attendo", "view"),),
                           "usr-admin", lifetime_seconds=3600)
        got = resolve_signed_in_user(repo, auth, "new@egoiq.com", frozenset(),
                                     email_domain_proven=False)
        assert isinstance(got, User)
```

- [ ] **Step 7: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/auth/test_identity.py -q`
Expected: 21 passed (17 from Task 1, plus 4 new).

- [ ] **Step 8: Run the whole suite**

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures.

- [ ] **Step 9: Commit**

```bash
git add src/reportbuilder/auth/invites.py src/reportbuilder/auth/identity.py tests/suite/unit/auth/test_invites.py tests/suite/unit/auth/test_identity.py
git commit -m "feat(auth): create and revoke invitations, and consume one at sign-in"
```

---

### Task 6: `routes_users.py` — the Users and Invitations HTTP surface

**Files:**
- Modify: `src/reportbuilder/api/routes_auth.py` (factor out `public_origin`)
- Create: `src/reportbuilder/api/routes_users.py`
- Modify: `src/reportbuilder/api/app.py`
- Test: `tests/suite/integration/api/test_users_api.py`

**Interfaces:**
- Consumes: `users.remove_user`/`set_admin`/`LastAdminRefused` (Task 2);
  `invites.create_invitation`/`revoke_invitation` (Task 5);
  `Repository.list_users`/`get_user`/`set_grants`/`list_invites`/`find_user_by_email`/`find_pending_invite_by_email`/`find_customer`/`find_case` (exist).
- Produces: `GET /users`, `PUT /users/{user_id}/grants`, `PATCH /users/{user_id}`,
  `DELETE /users/{user_id}`, `POST /users/invite`, `GET /invites`, `DELETE /invites/{invite_id}`.

**Why `public_origin` needs factoring out first:** the invitation link
points at `/login`, a client-side React Router route with no FastAPI
`url_for` name — `routes_auth.py`'s existing `_callback_url` already solved
"what origin is the browser actually using, behind Vite/nginx" for the OIDC
redirect; this task reuses that logic rather than re-deriving it.

- [ ] **Step 1: Factor `public_origin` out of `_callback_url`**

In `src/reportbuilder/api/routes_auth.py`, read the existing
`_callback_url` function, then replace it with:

```python
def public_origin(request: Request) -> str:
    """The browser-facing origin (scheme://host) -- see the three-way
    preference order this used to live inside _callback_url alone.
    Factored out for routes_users.py's invitation link, which points at
    /login, a client-side React Router route with no FastAPI url_for name
    to hang a path off.
    """
    public = os.environ.get("NSIGHT_PUBLIC_URL")
    if public:
        return public.rstrip("/")

    if _trust_forwarded_headers(request):
        proto = request.headers.get("x-forwarded-proto")
        host = request.headers.get("x-forwarded-host")
        if proto and host:
            return f"{proto}://{host}"

    return f"{request.url.scheme}://{request.url.netloc}"


def _callback_url(request: Request, provider: str) -> str:
    """The browser-facing URL Google/Microsoft must redirect back to.

    This has to be the origin the BROWSER is using, not the one the
    backend received the request on: Vite (dev) and nginx (prod) sit in
    front of the backend and proxy /auth to it, so request.url_for alone
    builds a backend-only URL that was never registered with the provider.
    See public_origin for the preference order that fixes it.
    """
    path = request.url_for("oidc_callback", provider=provider)
    return public_origin(request) + path.path
```

Run the existing OIDC tests to confirm this refactor changes nothing:
`.venv/bin/python -m pytest tests/suite/integration/api/test_auth_oidc_flow.py tests/suite/integration/api/test_oidc_failure_modes.py -q`
Expected: unchanged pass count from before this edit.

- [ ] **Step 2: Write the failing integration tests**

```python
# tests/suite/integration/api/test_users_api.py
"""GET/PUT/PATCH/DELETE /users, POST /users/invite, GET/DELETE /invites --
the Users screen's HTTP surface (spec §5, §6)."""
import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext
from suite._helpers import sign_in_override

pytestmark = pytest.mark.integration


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def admin_client(repo, auth):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(repo, auth, admin=True)
    return TestClient(app)


@pytest.fixture
def viewer_client(repo, auth):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(repo, auth, admin=False)
    return TestClient(app)


class TestListUsers:
    def test_lists_every_user_with_grant_names(self, admin_client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        repo.save_user(auth, User(id="", email="a@x.c", grants=(Grant(cid, "edit"),)))
        rows = admin_client.get("/users").json()
        row = next(r for r in rows if r["email"] == "a@x.c")
        assert row["grants"] == [{"scope": cid, "mode": "edit",
                                  "customer_name": "Attendo", "case_name": None}]

    def test_a_non_admin_cannot_list_users(self, viewer_client):
        assert viewer_client.get("/users").status_code == 403


class TestGrants:
    def test_admin_replaces_a_users_grants(self, admin_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="a@x.c"))
        r = admin_client.put(f"/users/{u.id}/grants",
                             json={"grants": [{"scope": "attendo", "mode": "view"}]})
        assert r.status_code == 200
        assert repo.get_user(auth, u.id).grants == (Grant("attendo", "view"),)

    def test_an_invalid_mode_is_rejected(self, admin_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="a@x.c"))
        r = admin_client.put(f"/users/{u.id}/grants",
                             json={"grants": [{"scope": "attendo", "mode": "delete"}]})
        assert r.status_code == 422

    def test_an_unknown_user_is_404(self, admin_client):
        assert admin_client.put("/users/usr-nope/grants", json={"grants": []}).status_code == 404


class TestAdminToggle:
    def test_promotes_a_user(self, admin_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="a@x.c"))
        r = admin_client.patch(f"/users/{u.id}", json={"is_admin": True})
        assert r.status_code == 200 and r.json()["is_admin"] is True

    def test_refuses_to_demote_the_last_admin(self, admin_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="only@x.c", is_admin=True))
        r = admin_client.patch(f"/users/{u.id}", json={"is_admin": False})
        assert r.status_code == 409
        assert repo.get_user(auth, u.id).is_admin is True


class TestRemoveUser:
    def test_removes_an_ordinary_user(self, admin_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="a@x.c"))
        r = admin_client.delete(f"/users/{u.id}")
        assert r.status_code == 204
        assert repo.get_user(auth, u.id) is None

    def test_refuses_to_remove_the_last_admin(self, admin_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="only@x.c", is_admin=True))
        r = admin_client.delete(f"/users/{u.id}")
        assert r.status_code == 409
        assert repo.get_user(auth, u.id) is not None

    def test_removing_an_unknown_user_is_404(self, admin_client):
        assert admin_client.delete("/users/usr-nope").status_code == 404

    def test_a_non_admin_cannot_remove_anyone(self, viewer_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="a@x.c"))
        assert viewer_client.delete(f"/users/{u.id}").status_code == 403


class TestInvite:
    def test_invites_a_new_email(self, admin_client):
        r = admin_client.post("/users/invite",
                              json={"email": "new@egoiq.com",
                                   "grants": [{"scope": "attendo", "mode": "view"}]})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["email"] == "new@egoiq.com"
        assert body["link"].endswith("/login")
        assert body["emailed"] is False  # no settings/email.json configured in this test
        assert body["status"] == "pending"

    def test_cannot_invite_an_existing_user(self, admin_client, repo, auth):
        repo.save_user(auth, User(id="", email="existing@egoiq.com"))
        r = admin_client.post("/users/invite", json={"email": "existing@egoiq.com", "grants": []})
        assert r.status_code == 409

    def test_cannot_invite_the_same_email_twice_while_pending(self, admin_client):
        admin_client.post("/users/invite", json={"email": "new@egoiq.com", "grants": []})
        r = admin_client.post("/users/invite", json={"email": "new@egoiq.com", "grants": []})
        assert r.status_code == 409

    def test_a_non_admin_cannot_invite(self, viewer_client):
        r = viewer_client.post("/users/invite", json={"email": "a@x.c", "grants": []})
        assert r.status_code == 403


class TestInviteConsumption:
    def test_accepting_an_invite_over_password_registration_gets_its_grants(self, admin_client):
        """The other half of the flow: /auth/register (already built) ends
        at identity.resolve_signed_in_user, which now consumes a pending
        invite (Task 5) -- proven here over the real HTTP surface."""
        admin_client.post("/users/invite",
                          json={"email": "invited@egoiq.com",
                               "grants": [{"scope": "attendo", "mode": "edit"}]})
        r = admin_client.post("/auth/register",
                              json={"email": "invited@egoiq.com",
                                   "password": "correct horse battery staple"})
        assert r.status_code == 201, r.text
        [row] = [u for u in admin_client.get("/users").json() if u["email"] == "invited@egoiq.com"]
        assert row["grants"][0]["scope"] == "attendo"
        [inv] = [i for i in admin_client.get("/invites").json() if i["email"] == "invited@egoiq.com"]
        assert inv["status"] == "accepted"


class TestRevokeInvite:
    def test_revoking_a_pending_invite_removes_it(self, admin_client):
        invite_id = admin_client.post("/users/invite",
                                      json={"email": "a@x.c", "grants": []}).json()["id"]
        r = admin_client.delete(f"/invites/{invite_id}")
        assert r.status_code == 204
        assert admin_client.get("/invites").json() == []

    def test_revoking_an_accepted_invite_removes_the_user(self, admin_client, repo, auth):
        invite_id = admin_client.post("/users/invite",
                                      json={"email": "a@x.c", "grants": []}).json()["id"]
        admin_client.post("/auth/register",
                          json={"email": "a@x.c", "password": "correct horse battery staple"})
        [row] = [u for u in admin_client.get("/users").json() if u["email"] == "a@x.c"]
        r = admin_client.delete(f"/invites/{invite_id}")
        assert r.status_code == 204
        assert repo.get_user(auth, row["id"]) is None
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_users_api.py -q`
Expected: 404s — the router does not exist yet.

- [ ] **Step 4: Write `routes_users.py`**

```python
# src/reportbuilder/api/routes_users.py
"""The Users and Invitations HTTP surface: everything an admin does from
the Settings > Users screen (spec §5, §6). Every route here is
require_admin -- administering access is not itself a data grant (spec
§5), so nobody without the admin flag reaches this file at all.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from reportbuilder.api.deps_auth import require_admin
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.api.routes_auth import public_origin
from reportbuilder.auth import invites, users
from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store.repository import Invite, Repository
from reportbuilder.store.seam import AuthContext, ConsentRequired

users_router = APIRouter(tags=["users"])


def _parse_grants(raw) -> tuple[Grant, ...]:
    if not isinstance(raw, list):
        raise HTTPException(422, "grants must be a list")
    try:
        return tuple(Grant(g["scope"], g.get("mode", "view")) for g in raw if g.get("scope"))
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


def _grant_out(repo: Repository, auth: AuthContext, g: Grant) -> dict:
    """A grant plus the name it stands for, so the Users screen can show
    "Attendo" rather than a bare id. Spec §5: a grant naming a customer or
    case that no longer exists is IGNORED for access -- here it is still
    SHOWN, with no name, so an admin can find and remove it."""
    parts = [s for s in g.scope.split("/") if s]
    customer = repo.find_customer(auth, parts[0]) if parts else None
    out = {"scope": g.scope, "mode": g.mode,
          "customer_name": customer.name if customer else None, "case_name": None}
    if customer is not None and len(parts) > 1:
        case = repo.find_case(auth, parts[1])
        out["case_name"] = case.name if case is not None else None
    return out


def _user_row(repo: Repository, auth: AuthContext, u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "is_admin": u.is_admin,
           "grants": [_grant_out(repo, auth, g) for g in u.grants]}


@users_router.get("/users")
def list_users(auth: AuthContext = Depends(get_auth), repo: Repository = Depends(get_repository),
              admin: User = Depends(require_admin)) -> list[dict]:
    return [_user_row(repo, auth, u) for u in repo.list_users(auth)]


@users_router.put("/users/{user_id}/grants")
def put_user_grants(user_id: str, body: dict = Body(...),
                    auth: AuthContext = Depends(get_auth), repo: Repository = Depends(get_repository),
                    admin: User = Depends(require_admin)) -> dict:
    if repo.get_user(auth, user_id) is None:
        raise HTTPException(404, f"User '{user_id}' not found")
    grants = _parse_grants(body.get("grants") or [])
    repo.set_grants(auth, user_id, grants)
    return _user_row(repo, auth, repo.get_user(auth, user_id))


@users_router.patch("/users/{user_id}")
def patch_user(user_id: str, body: dict = Body(...),
              auth: AuthContext = Depends(get_auth), repo: Repository = Depends(get_repository),
              admin: User = Depends(require_admin)) -> dict:
    """Today this only ever changes `is_admin` -- the promote/demote
    control. Anything else in the body is refused rather than silently
    ignored, so a frontend typo fails loudly instead of doing nothing."""
    if "is_admin" not in body:
        raise HTTPException(422, "is_admin is the only field this route changes")
    if repo.get_user(auth, user_id) is None:
        raise HTTPException(404, f"User '{user_id}' not found")
    result = users.set_admin(repo, auth, user_id, bool(body["is_admin"]))
    if isinstance(result, users.LastAdminRefused):
        raise HTTPException(409, result.reason)
    return _user_row(repo, auth, result)


@users_router.delete("/users/{user_id}", status_code=204)
def remove_user_route(user_id: str, auth: AuthContext = Depends(get_auth),
                      repo: Repository = Depends(get_repository),
                      admin: User = Depends(require_admin)) -> None:
    if repo.get_user(auth, user_id) is None:
        raise HTTPException(404, f"User '{user_id}' not found")
    try:
        result = users.remove_user(repo, auth, user_id)
    except ConsentRequired as exc:
        # datahive gates destructive operations -- surfaced with its
        # approval envelope, same shape as delete_font (routes_settings.py).
        raise HTTPException(409, {
            "error": "consent_required",
            "message": "Removing this user needs approval in datahive.",
            "request_id": exc.request_id, "target": exc.target,
            "approve": exc.envelope.get("approval_urls", {}),
        }) from exc
    if isinstance(result, users.LastAdminRefused):
        raise HTTPException(409, result.reason)


def _invite_out(i: Invite) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if i.accepted_user_id:
        status = "accepted"
    elif i.expires <= now:
        status = "expired"
    else:
        status = "pending"
    return {"id": i.id, "email": i.email, "invited_by": i.invited_by,
           "invited_at": i.invited_at, "expires": i.expires, "status": status,
           "grants": [{"scope": g.scope, "mode": g.mode} for g in i.grants]}


@users_router.post("/users/invite", status_code=201)
def invite_user(request: Request, body: dict = Body(...),
               auth: AuthContext = Depends(get_auth), repo: Repository = Depends(get_repository),
               admin: User = Depends(require_admin)) -> dict:
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(422, "a valid email is required")
    if repo.find_user_by_email(auth, email) is not None:
        raise HTTPException(409, f"'{email}' is already a user")
    if repo.find_pending_invite_by_email(auth, email) is not None:
        raise HTTPException(409, f"an invitation is already pending for '{email}'")
    grants = _parse_grants(body.get("grants") or [])
    login_url = f"{public_origin(request)}/login"
    invitation = invites.create_invitation(repo, auth, email=email, grants=grants,
                                           invited_by=admin, login_url=login_url)
    return {**_invite_out(invitation.invite), "link": invitation.link,
           "emailed": invitation.emailed}


@users_router.get("/invites")
def list_invites(auth: AuthContext = Depends(get_auth), repo: Repository = Depends(get_repository),
                 admin: User = Depends(require_admin)) -> list[dict]:
    return [_invite_out(i) for i in repo.list_invites(auth)]


@users_router.delete("/invites/{invite_id}", status_code=204)
def revoke_invite_route(invite_id: str, auth: AuthContext = Depends(get_auth),
                        repo: Repository = Depends(get_repository),
                        admin: User = Depends(require_admin)) -> None:
    result = invites.revoke_invitation(repo, auth, invite_id)
    if isinstance(result, users.LastAdminRefused):
        raise HTTPException(409, result.reason)


__all__ = ["users_router"]
```

- [ ] **Step 5: Register the router**

In `src/reportbuilder/api/app.py`:

```python
from reportbuilder.api.routes_users import users_router
...
    app.include_router(users_router)
```

- [ ] **Step 6: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_users_api.py -q`
Expected: 18 passed.

- [ ] **Step 7: Run the route census and the whole suite**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_route_census.py -q`
Expected: 2 passed — every new route carries `require_admin`, already in
`GUARD_NAMES`; `PUBLIC_ROUTES` is untouched.

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures.

- [ ] **Step 8: Commit**

```bash
git add src/reportbuilder/api/routes_auth.py src/reportbuilder/api/routes_users.py src/reportbuilder/api/app.py tests/suite/integration/api/test_users_api.py
git commit -m "feat(api): the Users and Invitations HTTP surface"
```

---

### Task 7: §8 — the workspace moves to datahive (backend)

**Files:**
- Modify: `src/reportbuilder/store/paths.py`
- Modify: `src/reportbuilder/store/repository.py`
- Modify: `src/reportbuilder/api/routes_settings.py`
- Test: `tests/suite/unit/store/test_repository_workspace.py`
- Test: `tests/suite/integration/api/test_settings_workspace.py`

**Interfaces:**
- Produces: `Repository.get_workspace(auth, user_id) -> dict`,
  `.set_case_workspace(auth, user_id, case_id, state) -> dict`;
  `GET /settings/workspace`, `PUT /settings/workspace/{case_id}`.

Spec §8: `web/src/lib/workspace.ts` keeps a per-case workspace in
`localStorage` — the material pointer and report timestamps — and "under §2
that must move to `settings/user/{id}.workspace` in datahive." One JSON
object per user, keyed by case inside it, because it is small, per-user, and
read/written as a whole every time a case is opened.

- [ ] **Step 1: Write the failing repository tests**

```python
# tests/suite/unit/store/test_repository_workspace.py
"""Per-user, per-case UI state (spec §8) -- the material pointer and
report list that used to live in the browser's localStorage.
"""
import pytest

from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


def test_an_unset_workspace_is_empty(repo, auth):
    assert repo.get_workspace(auth, "usr-1") == {}


def test_setting_one_cases_state_is_readable_back(repo, auth):
    repo.set_case_workspace(auth, "usr-1", "case-a", {"materialId": "mat-1", "reports": []})
    assert repo.get_workspace(auth, "usr-1") == {
        "case-a": {"materialId": "mat-1", "reports": []}}


def test_setting_a_second_case_does_not_disturb_the_first(repo, auth):
    repo.set_case_workspace(auth, "usr-1", "case-a", {"materialId": "mat-1", "reports": []})
    repo.set_case_workspace(auth, "usr-1", "case-b", {"materialId": "mat-2", "reports": []})
    ws = repo.get_workspace(auth, "usr-1")
    assert ws["case-a"]["materialId"] == "mat-1"
    assert ws["case-b"]["materialId"] == "mat-2"


def test_workspaces_are_isolated_per_user(repo, auth):
    repo.set_case_workspace(auth, "usr-1", "case-a", {"materialId": "mat-1", "reports": []})
    assert repo.get_workspace(auth, "usr-2") == {}


def test_overwriting_a_case_replaces_its_state_wholesale(repo, auth):
    repo.set_case_workspace(auth, "usr-1", "case-a", {"materialId": "mat-1", "reports": ["r1"]})
    repo.set_case_workspace(auth, "usr-1", "case-a", {"materialId": "mat-2", "reports": []})
    assert repo.get_workspace(auth, "usr-1")["case-a"] == {"materialId": "mat-2", "reports": []}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/suite/unit/store/test_repository_workspace.py -q`
Expected: `AttributeError: 'Repository' object has no attribute 'get_workspace'`.

- [ ] **Step 3: Add the path**

In `src/reportbuilder/store/paths.py`, add:

```python
LABEL_WORKSPACE = "nsight:workspace"
```

and after `user_password_path`:

```python
def user_workspace_path(user_id: str) -> str:
    """Per-case UI state -- the material pointer and report timestamps
    that used to live in the browser's localStorage (spec §8). A sibling
    of the user record, like grants and password."""
    return f"{user_path(user_id)}.workspace"
```

and to the module docstring's map, beneath `settings/user/{user_id}.password`:

```
    settings/user/{user_id}.workspace                 nsight:workspace
```

- [ ] **Step 4: Add the repository methods**

In `src/reportbuilder/store/repository.py`, immediately after the passwords
section:

```python
    # --- per-user workspace state --------------------------------------------
    #
    # spec §8: the material pointer and report timestamps that used to live
    # in web/src/lib/workspace.ts's localStorage. Moved here so attaching a
    # different hive brings a user's UI state with it (spec §2: nSight
    # keeps nothing of its own it cannot rebuild). One JSON object per
    # user, keyed by case inside it -- small, per-user, read/written whole
    # every time a case is opened.

    def get_workspace(self, auth: AuthContext, user_id: str) -> dict:
        try:
            d = self._read_json(auth, P.user_workspace_path(user_id))
        except (NotFound, ValueError, UnicodeDecodeError):
            return {}
        return d if isinstance(d, dict) else {}

    def set_case_workspace(self, auth: AuthContext, user_id: str, case_id: str,
                           state: dict) -> dict:
        """Replace the state for ONE case, leaving every other case's
        entry in this user's workspace untouched."""
        whole = self.get_workspace(auth, user_id)
        whole[case_id] = state
        self._write_json(auth, P.user_workspace_path(user_id), whole, [P.LABEL_WORKSPACE])
        return state
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/store/test_repository_workspace.py -q`
Expected: 5 passed.

- [ ] **Step 6: Write the failing route tests**

```python
# tests/suite/integration/api/test_settings_workspace.py
"""GET/PUT /settings/workspace -- per-user UI state moved out of
localStorage (spec §8)."""
import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.integration


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def client(repo, auth):
    u = repo.save_user(auth, User(id="", email="a@x.c"))
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = lambda: u
    return TestClient(app)


def test_defaults_to_empty(client):
    assert client.get("/settings/workspace").json() == {}


def test_a_case_can_be_set_and_read_back(client):
    r = client.put("/settings/workspace/case-a", json={"materialId": "mat-1", "reports": []})
    assert r.status_code == 200
    assert client.get("/settings/workspace").json() == {
        "case-a": {"materialId": "mat-1", "reports": []}}


def test_a_second_user_does_not_see_the_firsts_workspace(repo, auth):
    ua = repo.save_user(auth, User(id="", email="a@x.c"))
    ub = repo.save_user(auth, User(id="", email="b@x.c"))
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth

    app.dependency_overrides[current_user] = lambda: ua
    TestClient(app).put("/settings/workspace/case-a", json={"materialId": "mat-1", "reports": []})

    app.dependency_overrides[current_user] = lambda: ub
    assert TestClient(app).get("/settings/workspace").json() == {}
```

- [ ] **Step 7: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_settings_workspace.py -q`
Expected: 404s.

- [ ] **Step 8: Add the routes**

In `src/reportbuilder/api/routes_settings.py`, near `list_fonts`:

```python
@settings_router.get("/settings/workspace")
def get_workspace_route(auth: AuthContext = Depends(get_auth),
                        repo: Repository = Depends(get_repository),
                        user: User = Depends(current_user)) -> dict:
    """This signed-in user's own per-case UI state (spec §8) -- never
    another user's; there is no user_id parameter to spoof."""
    return repo.get_workspace(auth, user.id)


@settings_router.put("/settings/workspace/{case_id}")
def put_case_workspace_route(case_id: str, payload: dict = Body(...),
                             auth: AuthContext = Depends(get_auth),
                             repo: Repository = Depends(get_repository),
                             user: User = Depends(current_user)) -> dict:
    """Replace this user's state for ONE case. Deliberately NOT gated by
    require_case: this is private UI preference data keyed by a case id,
    not a view of the case itself, so a user with no grant on `case_id`
    setting one here leaks nothing -- there is nothing here to read back
    except their own record."""
    return repo.set_case_workspace(auth, user.id, case_id, payload)
```

- [ ] **Step 9: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_settings_workspace.py -q`
Expected: 3 passed.

- [ ] **Step 10: Run the census and the whole suite**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_route_census.py -q`
Expected: 2 passed.

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures.

- [ ] **Step 11: Commit**

```bash
git add src/reportbuilder/store/paths.py src/reportbuilder/store/repository.py src/reportbuilder/api/routes_settings.py tests/suite/unit/store/test_repository_workspace.py tests/suite/integration/api/test_settings_workspace.py
git commit -m "feat(store): per-user workspace state moves to datahive (spec §8)"
```

---

### Task 8: §8 — the workspace moves to datahive (frontend)

**Files:**
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/lib/workspace.ts`
- Modify: `web/src/components/NewCaseDialog.tsx`
- Modify: `web/src/pages/CaseDetailPage.tsx`

**No frontend test runner exists in this repo** — verified with `cat
web/package.json`'s scripts and devDependencies: `test` is not a script,
Playwright is installed but has no config. This task is verified with
`tsc -b` and a manual walkthrough, matching Plan 2's Task 8 precedent.

- [ ] **Step 1: Add the API surface**

In `web/src/lib/api.ts`, add types near `FontsSettings`:

```typescript
export interface WorkspaceReport {
  id: string;
  name: string;
  materialId?: string;
  createdAt?: string;
}

export interface WorkspaceCaseState {
  materialId: string | null;
  reports: WorkspaceReport[];
}
```

and, inside the `settings` object (after `deleteFont`):

```typescript
    workspace: (): Promise<Record<string, WorkspaceCaseState>> =>
      fetch(`${API_BASE}/settings/workspace`).then((r) =>
        json<Record<string, WorkspaceCaseState>>(r)
      ),

    setCaseWorkspace: (
      caseId: string,
      state: WorkspaceCaseState
    ): Promise<WorkspaceCaseState> =>
      fetch(`${API_BASE}/settings/workspace/${caseId}`, jsonPut(state)).then((r) =>
        json<WorkspaceCaseState>(r)
      ),
```

- [ ] **Step 2: Rewrite `workspace.ts`**

```typescript
// web/src/lib/workspace.ts
import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { WorkspaceCaseState, WorkspaceReport } from "./api";

// Per-case workspace, persisted through the API (spec §8) -- moved out of
// localStorage so attaching a different hive brings a user's UI state with
// it. One query key for the WHOLE per-user blob (GET /settings/workspace
// returns every case at once): a case page and the report list both read
// it, and fetching per-case would mean a request per case in the sidebar.

export type { WorkspaceCaseState, WorkspaceReport };

const EMPTY: WorkspaceCaseState = { materialId: null, reports: [] };
const KEY = ["settings", "workspace"] as const;

function caseState(
  all: Record<string, WorkspaceCaseState> | undefined,
  caseId: string
): WorkspaceCaseState {
  const found = all?.[caseId];
  return found
    ? { materialId: found.materialId ?? null, reports: found.reports ?? [] }
    : { ...EMPTY };
}

export function useWorkspace(caseId: string) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: api.settings.workspace });
  const workspace = caseState(query.data, caseId);

  const write = useMutation({
    mutationFn: (state: WorkspaceCaseState) => api.settings.setCaseWorkspace(caseId, state),
    // Applied before the round trip returns -- a case page reads this
    // synchronously (materialId drives which questions/preview show), and
    // waiting for the network would flash the OLD material back in.
    onMutate: async (state) => {
      await qc.cancelQueries({ queryKey: KEY });
      const previous = qc.getQueryData<Record<string, WorkspaceCaseState>>(KEY);
      qc.setQueryData<Record<string, WorkspaceCaseState>>(KEY, (old) => ({
        ...old,
        [caseId]: state,
      }));
      return { previous };
    },
    onError: (_e, _state, ctx) => {
      if (ctx?.previous) qc.setQueryData(KEY, ctx.previous);
    },
  });

  const setMaterial = useCallback(
    (materialId: string | null) => write.mutate({ ...workspace, materialId }),
    [write, workspace]
  );
  const addReport = useCallback(
    (report: WorkspaceReport) => {
      if (workspace.reports.some((r) => r.id === report.id)) return;
      write.mutate({ ...workspace, reports: [...workspace.reports, report] });
    },
    [write, workspace]
  );
  const removeReport = useCallback(
    (id: string) =>
      write.mutate({ ...workspace, reports: workspace.reports.filter((r) => r.id !== id) }),
    [write, workspace]
  );
  const renameReport = useCallback(
    (id: string, name: string) =>
      write.mutate({
        ...workspace,
        reports: workspace.reports.map((r) => (r.id === id ? { ...r, name } : r)),
      }),
    [write, workspace]
  );

  return { workspace, setMaterial, addReport, removeReport, renameReport };
}

/** Drop this user's state for one case -- e.g. when a case is deleted. */
export function useClearWorkspace() {
  const qc = useQueryClient();
  return useCallback(
    (caseId: string) => {
      qc.setQueryData<Record<string, WorkspaceCaseState>>(KEY, (old) => {
        if (!old) return old;
        const { [caseId]: _drop, ...rest } = old;
        return rest;
      });
      // The empty write both persists the clear and matches what
      // set_case_workspace already does for "no state" -- there is no
      // DELETE route to add for a case this rarely goes empty.
      return api.settings.setCaseWorkspace(caseId, { ...EMPTY });
    },
    [qc]
  );
}
```

- [ ] **Step 3: Update `NewCaseDialog.tsx`'s one bare workspace write**

Replace:

```typescript
import { setMaterial } from "@/lib/workspace";
```

with nothing (drop the import — `useQueryClient` is already imported), and
replace:

```typescript
      setMaterial(case_id, res.material_id);
```

with:

```typescript
      qc.setQueryData<Record<string, import("@/lib/workspace").WorkspaceCaseState>>(
        ["settings", "workspace"],
        (old) => ({ ...old, [case_id]: { materialId: res.material_id, reports: [] } })
      );
      void api.settings.setCaseWorkspace(case_id, {
        materialId: res.material_id,
        reports: [],
      });
```

(`qc` is the component's existing `useQueryClient()` result; `api` is
already imported.)

- [ ] **Step 4: Update `CaseDetailPage.tsx`'s `clearWorkspace` call**

Replace:

```typescript
import { useWorkspace, clearWorkspace } from "@/lib/workspace";
```

with:

```typescript
import { useWorkspace, useClearWorkspace } from "@/lib/workspace";
```

Inside the component, alongside the existing `useWorkspace(id ?? "")` call:

```typescript
  const clearWorkspace = useClearWorkspace();
```

and leave every call site (`clearWorkspace(id)`) unchanged — the hook
returns a function with the same signature the bare export had.

- [ ] **Step 5: Typecheck**

Run: `cd web && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 6: Manual verification**

Run: `docker compose -f docker-compose.dev.yml up` (or the project's usual
dev-stack script), sign in, open a case, pick a material — confirm the
Network tab shows `PUT /settings/workspace/{case_id}` rather than a
`localStorage` write (check Application > Local Storage in devtools: no
`nsight.ws.*` key appears). Reload the page — the same material stays
selected, now served from `GET /settings/workspace`. Create a new case from
a `.sav` upload — confirm it opens with that upload already selected as its
material.

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/api.ts web/src/lib/workspace.ts web/src/components/NewCaseDialog.tsx web/src/pages/CaseDetailPage.tsx
git commit -m "feat(web): the per-case workspace moves out of localStorage (spec §8)"
```

---

### Task 9: The Users section in Settings

**Files:**
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/lib/queries.ts`
- Modify: `web/src/pages/SettingsPage.tsx`

**Interfaces:**
- Produces: `api.users.list/setGrants/setAdmin/remove/invite/listInvites/revokeInvite`;
  `useUsers`, `useInvites`, `useUserActions`.

- [ ] **Step 1: Add the API surface**

In `web/src/lib/api.ts`, add near `json`:

```typescript
/** Like json(), but on failure prefers the server's `detail` string over a
 *  bare status line -- the reason ("the last admin cannot be removed") IS
 *  the message the toast should show. */
async function detailedJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // not JSON — keep status text
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

async function detailedVoid(res: Response): Promise<void> {
  if (res.ok) return;
  let detail = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    // not JSON — keep status text
  }
  throw new Error(detail);
}
```

Add types near `FontsSettings`:

```typescript
export interface UserGrantInput {
  scope: string;
  mode: "view" | "edit";
}

export interface UserGrant extends UserGrantInput {
  customer_name: string | null;
  case_name: string | null;
}

export interface StudioUser {
  id: string;
  email: string;
  name: string;
  is_admin: boolean;
  grants: UserGrant[];
}

export interface Invite {
  id: string;
  email: string;
  invited_by: string;
  invited_at: string;
  expires: string;
  status: "pending" | "accepted" | "expired";
  grants: UserGrantInput[];
}

export interface InvitationResult extends Invite {
  link: string;
  emailed: boolean;
}
```

Add a `users` block to the `api` object, after `settings`:

```typescript
  users: {
    list: (): Promise<StudioUser[]> =>
      fetch(`${API_BASE}/users`).then((r) => json<StudioUser[]>(r)),

    setGrants: (userId: string, grants: UserGrantInput[]): Promise<StudioUser> =>
      fetch(`${API_BASE}/users/${userId}/grants`, jsonPut({ grants })).then(detailedJson),

    setAdmin: (userId: string, isAdmin: boolean): Promise<StudioUser> =>
      fetch(`${API_BASE}/users/${userId}`, jsonPatch({ is_admin: isAdmin })).then(detailedJson),

    remove: (userId: string): Promise<void> =>
      fetch(`${API_BASE}/users/${userId}`, { method: "DELETE" }).then(detailedVoid),

    invite: (email: string, grants: UserGrantInput[]): Promise<InvitationResult> =>
      fetch(`${API_BASE}/users/invite`, jsonPost({ email, grants })).then(detailedJson),

    listInvites: (): Promise<Invite[]> =>
      fetch(`${API_BASE}/invites`).then((r) => json<Invite[]>(r)),

    revokeInvite: (inviteId: string): Promise<void> =>
      fetch(`${API_BASE}/invites/${inviteId}`, { method: "DELETE" }).then(detailedVoid),
  },
```

- [ ] **Step 2: Add the query hooks**

In `web/src/lib/queries.ts`:

```typescript
export function useUsers() {
  return useQuery({ queryKey: ["users"], queryFn: api.users.list });
}

export function useInvites() {
  return useQuery({ queryKey: ["invites"], queryFn: api.users.listInvites });
}

export function useUserActions() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["users"] });
    qc.invalidateQueries({ queryKey: ["invites"] });
  };
  return {
    setGrants: useMutation({
      mutationFn: ({ userId, grants }: { userId: string; grants: UserGrantInput[] }) =>
        api.users.setGrants(userId, grants),
      onSuccess: invalidate,
    }),
    setAdmin: useMutation({
      mutationFn: ({ userId, isAdmin }: { userId: string; isAdmin: boolean }) =>
        api.users.setAdmin(userId, isAdmin),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: api.users.remove, onSuccess: invalidate }),
    invite: useMutation({
      mutationFn: ({ email, grants }: { email: string; grants: UserGrantInput[] }) =>
        api.users.invite(email, grants),
      onSuccess: invalidate,
    }),
    revokeInvite: useMutation({ mutationFn: api.users.revokeInvite, onSuccess: invalidate }),
  };
}
```

Add the import `UserGrantInput` to the file's existing `import type { ... } from "./api"` block.

- [ ] **Step 3: Build the Users tab**

In `web/src/pages/SettingsPage.tsx`, extend the existing surfaces import —
replace:

```typescript
import { EMPTY, PAGE, PAGE_TITLE, PANEL, PANEL_TITLE, ROW } from "@/lib/surfaces";
```

with:

```typescript
import { EMPTY, PAGE, PAGE_TITLE, PANEL, PANEL_TITLE, ROW, SECTION_HEADER } from "@/lib/surfaces";
```

and add these new imports:

```typescript
import { Trash2Icon, MailIcon, CopyIcon, PlusIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import {
  useUsers, useInvites, useUserActions, useCustomers,
} from "@/lib/queries";
import type { StudioUser, Invite, UserGrantInput } from "@/lib/api";
```

Add a grant-picker used inside the invite dialog:

```typescript
function GrantPicker({
  grants,
  onChange,
}: {
  grants: UserGrantInput[];
  onChange: (grants: UserGrantInput[]) => void;
}) {
  const { data: customers } = useCustomers();
  const [customerId, setCustomerId] = useState("");
  const [mode, setMode] = useState<"view" | "edit">("view");

  function add() {
    if (!customerId || grants.some((g) => g.scope === customerId)) return;
    onChange([...grants, { scope: customerId, mode }]);
    setCustomerId("");
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <select
          className="h-8 min-w-0 flex-1 rounded-lg border border-input bg-surface px-2.5 text-sm"
          value={customerId}
          onChange={(e) => setCustomerId(e.target.value)}
        >
          <option value="">Choose a customer…</option>
          {(customers ?? [])
            .filter((c) => !grants.some((g) => g.scope === c.id))
            .map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
        </select>
        <select
          className="h-8 w-24 rounded-lg border border-input bg-surface px-2.5 text-sm"
          value={mode}
          onChange={(e) => setMode(e.target.value as "view" | "edit")}
        >
          <option value="view">View</option>
          <option value="edit">Edit</option>
        </select>
        <Button size="sm" variant="outline" disabled={!customerId} onClick={add}>
          <PlusIcon className="size-4" />
        </Button>
      </div>
      {grants.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {grants.map((g) => {
            const name = (customers ?? []).find((c) => c.id === g.scope)?.name ?? g.scope;
            return (
              <Badge key={g.scope} variant="secondary" className="gap-1">
                {name} · {g.mode}
                <button
                  type="button"
                  className="ml-1 opacity-60 hover:opacity-100"
                  onClick={() => onChange(grants.filter((x) => x.scope !== g.scope))}
                >
                  ×
                </button>
              </Badge>
            );
          })}
        </div>
      )}
    </div>
  );
}

function InviteDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const actions = useUserActions();
  const [email, setEmail] = useState("");
  const [grants, setGrants] = useState<UserGrantInput[]>([]);
  const [result, setResult] = useState<{ link: string; emailed: boolean } | null>(null);

  function reset() {
    setEmail("");
    setGrants([]);
    setResult(null);
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite someone to nSight Studio</DialogTitle>
          <DialogDescription>
            They'll get an email with a link to sign in. Access is granted the moment they accept.
          </DialogDescription>
        </DialogHeader>
        {result ? (
          <div className="space-y-3 text-sm">
            {result.emailed ? (
              <p className="flex items-center gap-2 text-primary">
                <MailIcon className="size-4" /> Invitation sent.
              </p>
            ) : (
              <p className="text-amber-600">
                Email could not be sent — copy the link below and share it yourself.
              </p>
            )}
            <div className="flex items-center gap-2 rounded-lg border bg-surface p-2">
              <code className="min-w-0 flex-1 truncate text-xs">{result.link}</code>
              <Button
                size="icon-sm"
                variant="ghost"
                onClick={() => navigator.clipboard.writeText(result.link)}
              >
                <CopyIcon className="size-4" />
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <Input
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
            />
            <GrantPicker grants={grants} onChange={setGrants} />
          </div>
        )}
        <DialogFooter>
          {result ? (
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          ) : (
            <Button
              disabled={!email || actions.invite.isPending}
              onClick={() =>
                actions.invite.mutate(
                  { email, grants },
                  {
                    onSuccess: (r) => setResult({ link: r.link, emailed: r.emailed }),
                    onError: (e) => toast.error(e.message),
                  }
                )
              }
            >
              Send invite
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function UserRow({ user, isSelf }: { user: StudioUser; isSelf: boolean }) {
  const actions = useUserActions();
  return (
    <div className={`${ROW} items-start gap-3`}>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{user.email}</p>
        {user.grants.length === 0 ? (
          <p className="mt-1 text-xs text-muted-foreground">No customers granted yet</p>
        ) : (
          <div className="mt-1 flex flex-wrap gap-1">
            {user.grants.map((g) => (
              <Badge key={g.scope} variant={g.customer_name ? "secondary" : "destructive"}>
                {g.customer_name ?? "deleted"}
                {g.case_name ? ` / ${g.case_name}` : ""} · {g.mode}
                <button
                  type="button"
                  className="ml-1 opacity-60 hover:opacity-100"
                  onClick={() =>
                    actions.setGrants.mutate({
                      userId: user.id,
                      grants: user.grants
                        .filter((x) => x.scope !== g.scope)
                        .map((x) => ({ scope: x.scope, mode: x.mode })),
                    })
                  }
                >
                  ×
                </button>
              </Badge>
            ))}
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          Admin
          <Switch
            size="sm"
            checked={user.is_admin}
            disabled={actions.setAdmin.isPending}
            onCheckedChange={(checked) =>
              actions.setAdmin.mutate(
                { userId: user.id, isAdmin: checked },
                { onError: (e) => toast.error(e.message) }
              )
            }
          />
        </div>
        <Button
          size="icon-sm"
          variant="ghost"
          disabled={actions.remove.isPending}
          title={isSelf ? "You cannot remove yourself" : "Remove user"}
          onClick={() =>
            actions.remove.mutate(user.id, {
              onSuccess: () => toast.success(`${user.email} removed`),
              onError: (e) => toast.error(e.message),
            })
          }
        >
          <Trash2Icon className="size-4" />
        </Button>
      </div>
    </div>
  );
}

function InviteRow({ invite }: { invite: Invite }) {
  const actions = useUserActions();
  return (
    <div className={`${ROW} gap-3`}>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{invite.email}</p>
        <p className="text-xs text-muted-foreground">
          Invited {new Date(invite.invited_at).toLocaleDateString()} ·{" "}
          <Badge variant={invite.status === "pending" ? "secondary" : invite.status === "accepted" ? "default" : "destructive"}>
            {invite.status}
          </Badge>
        </p>
      </div>
      <Button
        size="icon-sm"
        variant="ghost"
        disabled={actions.revokeInvite.isPending}
        title={invite.status === "accepted" ? "Revoke and remove this user" : "Revoke invitation"}
        onClick={() =>
          actions.revokeInvite.mutate(invite.id, {
            onError: (e) => toast.error(e.message),
          })
        }
      >
        <Trash2Icon className="size-4" />
      </Button>
    </div>
  );
}

function UsersTab() {
  const { data: users, isLoading } = useUsers();
  const { data: invites } = useInvites();
  const [inviting, setInviting] = useState(false);

  return (
    <div className="space-y-6">
      <div className={SECTION_HEADER}>
        <h3 className={PANEL_TITLE}>Users</h3>
        <Button size="sm" onClick={() => setInviting(true)}>Invite</Button>
      </div>
      <div className="space-y-2">
        {isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}
        {users?.length === 0 && !isLoading && (
          <p className={`${EMPTY} text-sm text-muted-foreground`}>No users yet.</p>
        )}
        {users?.map((u) => <UserRow key={u.id} user={u} isSelf={false} />)}
      </div>

      {invites && invites.length > 0 && (
        <div>
          <h3 className={PANEL_TITLE}>Invitations</h3>
          <div className="mt-2 space-y-2">
            {invites.map((i) => <InviteRow key={i.id} invite={i} />)}
          </div>
        </div>
      )}

      <InviteDialog open={inviting} onOpenChange={setInviting} />
    </div>
  );
}
```

Add a `Users` tab to the page's `Tabs`:

```typescript
export default function SettingsPage() {
  return (
    <div className={PAGE}>
      <h1 className={PAGE_TITLE}>Settings</h1>

      <Tabs defaultValue="fonts" className="mt-6">
        <TabsList>
          <TabsTrigger value="fonts">Fonts</TabsTrigger>
          <TabsTrigger value="users">Users</TabsTrigger>
        </TabsList>
        <TabsContent value="fonts" className="mt-4">
          <FontsTab />
        </TabsContent>
        <TabsContent value="users" className="mt-4">
          <UsersTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
```

This tab is reachable by anyone who opens Settings; the backend enforces
`require_admin` on every one of its calls, so a non-admin sees the tab load
into a wall of 403 toasts rather than seeing any data — acceptable for a
first cut, but worth a follow-up: gate the tab's visibility with
`useSession().data?.is_admin` so a non-admin never sees it at all. Adding
that check now:

```typescript
import { useSession } from "@/lib/session";
```

and, inside `SettingsPage`:

```typescript
  const { data: me } = useSession();
```

and the `TabsTrigger`/`TabsContent` pair for `"users"` wrapped in
`{me?.is_admin && (...)}`.

- [ ] **Step 4: Typecheck**

Run: `cd web && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 5: Manual verification**

Sign in as the bootstrap admin. Open Settings > Users. Invite a second
address you control (or, with no `settings/email.json` configured, confirm
`emailed: false` and copy the link). Grant it a customer with `view`.
Open the copied link in a private window, register/sign in as that address,
confirm the granted customer — and only that one — appears. Back as the
admin, toggle that user to admin, then demote yourself and confirm the UI
surfaces "the last admin cannot be demoted" if you are the only one; add a
second admin first to confirm demotion succeeds once it is not the last
one. Remove the invited user and confirm their session stops working.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/api.ts web/src/lib/queries.ts web/src/pages/SettingsPage.tsx
git commit -m "feat(web): a Users section in Settings — invite, grant, promote, remove"
```

---

### Task 10: `updateChartByRef` collides two slides that share a `question_ref`

**Files:**
- Modify: `web/src/components/wizard/ReportWizard.tsx`
- Modify: `web/src/components/wizard/StepConfigure.tsx`

**Diagnosis, read from the actual code:** `ChartSpec.slide_id` already
exists specifically for this — its own comment in `web/src/lib/api.ts`
reads "Per-chart identity. `question_ref` says WHICH QUESTION a chart shows
and is no longer unique: a comparison section adds a second slide for a
question that already has a total-level one," and `newSlideId()`'s comment
in `web/src/lib/charts.ts` repeats it. `addComparisonSection` (ReportWizard.tsx)
creates a "Compare groups" slide via `makeComparisonSlide(c, classifyingVar)`,
which keeps the SAME `question_ref` as the question's total-level slide and
sets `compare_group`/`classifying_var` instead. `slide_id` is already used
correctly for slide SELECTION (`active`), but four other places still
address a chart by `question_ref` alone:

1. `updateChartByRef(ref, patch)` does
   `d.charts.map(c => c.question_ref === ref ? {...c, ...patch} : c)` —
   this patches EVERY chart sharing that ref, so an AI title generated for
   the total-level slide overwrites the Compare-groups slide's title too
   (and vice versa).
2. `runTitle(ref)` resolves the chart to generate a title FOR via
   `draftRef.current?.charts.find(c => c.question_ref === ref)` — always
   the FIRST chart with that ref, so the second slide's own
   `classifying_var` never even reaches the AI title endpoint.
3. `ensureTitles(refs)` is called from `StepConfigure.tsx` with
   `charts.map(c => c.question_ref)` — one ref PER CHART INSTANCE, so a
   question with both a total and a Compare-groups slide pushes the SAME
   ref twice; combined with (2) always resolving the same first chart, the
   second slide is never separately queued at all.
4. `aiPending`, the "Generating title…" indicator, is also keyed by
   `question_ref` (`setAiPending`'s calls, and `StepConfigure.tsx`'s three
   reads off `activeChart.question_ref`), so both slides show the same
   pending state.

The fix threads `slide_id` through all four instead.

- [ ] **Step 1: Rename `updateChartByRef` to `updateChartById`, keyed on `slide_id`**

In `web/src/components/wizard/ReportWizard.tsx`, replace:

```typescript
  // Update a chart found by its question_ref (indices can shift while async
  // AI work is in flight, so the auto-formatter addresses charts by ref).
  const updateChartByRef = useCallback(
    (ref: string, patch: Partial<ChartSpec>) => {
      mutate((d) => ({
        ...d,
        charts: d.charts.map((c) =>
          c.question_ref === ref ? { ...c, ...patch } : c
        ),
      }));
    },
    [mutate]
  );
```

with:

```typescript
  // Update ONE chart, found by its slide_id (indices can shift while async
  // AI work is in flight, so the auto-formatter addresses charts by id, not
  // position). question_ref is NOT unique enough for this: a "Compare
  // groups" slide shares its question_ref with the question's total-level
  // slide (see newSlideId's comment in lib/charts.ts), so matching on
  // question_ref here used to patch BOTH slides with whichever one's AI
  // title happened to resolve last.
  const updateChartById = useCallback(
    (slideId: string, patch: Partial<ChartSpec>) => {
      mutate((d) => ({
        ...d,
        charts: d.charts.map((c) =>
          c.slide_id === slideId ? { ...c, ...patch } : c
        ),
      }));
    },
    [mutate]
  );
```

- [ ] **Step 2: Rewrite `runTitle` to resolve and address by `slide_id`**

Replace the whole `runTitle` callback with:

```typescript
  const runTitle = useCallback(
    async (slideId: string) => {
      const chart = draftRef.current?.charts.find((c) => c.slide_id === slideId);
      if (!chart) return;
      const ref = chart.question_ref;
      // Recomputed here (not just trusted from the caller) because runTitle is
      // also reached for a themes chart's bullets alone — the title half of the
      // work below still needs its own up-to-date needs-it check.
      const resolved = questionByRef.get(ref);
      const currentKey = titleDataKey(chart, resolved);
      const keyStale =
        !!chart.slide_title_key && chart.slide_title_key !== currentKey;
      const needsTitleNow = !chart.slide_title || keyStale;
      if (isThemes(chart)) {
        const hasBullets = !!(chart.options?.bullets as string[] | undefined)
          ?.length;
        const bulletsP = hasBullets
          ? Promise.resolve()
          : api.materials
              .aiThemes(materialId, { question_ref: ref })
              .then(({ bullets }) =>
                updateChartById(slideId, {
                  options: { ...(chart.options ?? {}), bullets },
                })
              )
              .catch(() => {
                /* graceful: leave empty */
              })
              .finally(() =>
                setAiPending((prev) => ({
                  ...prev,
                  [slideId]: { ...prev[slideId], bulletsPending: false },
                }))
              );
        const titleP = !needsTitleNow
          ? Promise.resolve()
          : api.materials
              .aiSlideTitle(materialId, {
                question_ref: ref,
                statistic: chart.statistic,
                grouping: draftRef.current?.grouping,
              })
              .then(({ title }) => {
                if (title)
                  updateChartById(slideId, {
                    slide_title: title,
                    slide_title_key: currentKey,
                  });
              })
              .catch(() => {
                /* graceful: fall back to the question text */
              })
              .finally(() =>
                setAiPending((prev) => ({
                  ...prev,
                  [slideId]: { ...prev[slideId], titlePending: false },
                }))
              );
        await Promise.all([bulletsP, titleP]);
        return;
      }
      try {
        // Only the headline (slide_title) is AI-generated. The subtitle is left to
        // default to the MATERIAL question text (deterministic), not an AI line.
        const { title } = await api.materials.aiSlideTitle(materialId, {
          question_ref: ref,
          statistic: chart.statistic,
          classifying_var: chart.classifying_var,
          show_not_answered: chart.show_not_answered,
          not_answered_codes: chart.not_answered_codes,
          grouping: draftRef.current?.grouping,
        });
        const patch: Partial<ChartSpec> = {};
        if (title) {
          patch.slide_title = title;
          patch.slide_title_key = currentKey;
        }
        if (Object.keys(patch).length) updateChartById(slideId, patch);
      } catch {
        /* graceful: fall back to the question text */
      } finally {
        setAiPending((prev) => ({
          ...prev,
          [slideId]: { ...prev[slideId], titlePending: false },
        }));
      }
    },
    [materialId, updateChartById, questionByRef]
  );
```

- [ ] **Step 3: Rewrite `ensureTitles` to iterate and dedupe by `slide_id`**

Replace the whole `ensureTitles` callback with:

```typescript
  const ensureTitles = useCallback(
    (slideIds: string[]) => {
      let added = false;
      for (const id of slideIds) {
        if (!id) continue;
        const chart = draftRef.current?.charts.find((c) => c.slide_id === id);
        if (!chart) continue;
        if (isSpecialSlide(chart)) continue; // special slides carry bullets, not a title
        const resolved = questionByRef.get(chart.question_ref);
        if (!resolved) continue;
        const themes = isThemes(chart);
        const needsBullets =
          themes && !((chart.options?.bullets as string[] | undefined)?.length);
        const currentKey = titleDataKey(chart, resolved);
        const keyStale =
          !!chart.slide_title_key && chart.slide_title_key !== currentKey;
        const needsTitle = !chart.slide_title || keyStale;
        if (themes ? !needsBullets && !needsTitle : !needsTitle) continue;
        // One attempt per (slide, data key) per session.
        const attemptToken = `${id}${currentKey}`;
        if (titlesAttempted.current.has(attemptToken)) continue;
        titlesAttempted.current.add(attemptToken);
        titleQueue.current.push(id);
        added = true;
        setAiPending((prev) => ({
          ...prev,
          [id]: themes
            ? {
                titlePending: needsTitle,
                labelsPending: prev[id]?.labelsPending ?? false,
                bulletsPending: needsBullets,
              }
            : {
                titlePending: true,
                labelsPending: prev[id]?.labelsPending ?? false,
              },
        }));
      }
      if (added) pumpTitles();
    },
    [pumpTitles, questionByRef]
  );
```

- [ ] **Step 4: Fix `regenerateSpecial`'s themes branch**

Replace:

```typescript
      if (isThemes(chart)) {
        const ref = chart.question_ref;
        setBulletsPending(ref, true);
        try {
          const { bullets } = await api.materials.aiThemes(materialId, {
            question_ref: ref,
          });
          updateChartByRef(ref, { options: { ...(chart.options ?? {}), bullets } });
        } catch (e) {
          toast.error(`Could not regenerate themes: ${errMsg(e)}`);
        } finally {
          setBulletsPending(ref, false);
          setAiSaveTick((t) => t + 1);
        }
        return;
```

with:

```typescript
      if (isThemes(chart)) {
        const ref = chart.question_ref;
        const slideId = chart.slide_id ?? ref;
        setBulletsPending(slideId, true);
        try {
          const { bullets } = await api.materials.aiThemes(materialId, {
            question_ref: ref,
          });
          updateChartById(slideId, { options: { ...(chart.options ?? {}), bullets } });
        } catch (e) {
          toast.error(`Could not regenerate themes: ${errMsg(e)}`);
        } finally {
          setBulletsPending(slideId, false);
          setAiSaveTick((t) => t + 1);
        }
        return;
```

- [ ] **Step 5: Address `StepConfigure.tsx` by `slide_id` too**

Replace:

```typescript
  onEnsureTitles?: (refs: string[]) => void;
```

with:

```typescript
  onEnsureTitles?: (slideIds: string[]) => void;
```

Replace:

```typescript
  useEffect(() => {
    if (charts.length) onEnsureTitles?.(charts.map((c) => c.question_ref));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [titleFingerprint, onEnsureTitles]);
```

with:

```typescript
  useEffect(() => {
    if (charts.length)
      onEnsureTitles?.(charts.map((c) => c.slide_id ?? c.question_ref));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [titleFingerprint, onEnsureTitles]);
```

Replace the three `aiPending` reads:

```typescript
    aiPending?.[activeChart?.question_ref ?? ""]?.bulletsPending ?? false;
```

with:

```typescript
    aiPending?.[activeChart?.slide_id ?? ""]?.bulletsPending ?? false;
```

and:

```typescript
                  aiPending?.[activeChart.question_ref]?.titlePending ?? false
```
```typescript
                  aiPending?.[activeChart.question_ref]?.labelsPending ?? false
```

with:

```typescript
                  aiPending?.[activeChart.slide_id ?? ""]?.titlePending ?? false
```
```typescript
                  aiPending?.[activeChart.slide_id ?? ""]?.labelsPending ?? false
```

- [ ] **Step 6: Typecheck**

Run: `cd web && npx tsc -b --noEmit`
Expected: no errors. (`updateChartByRef` no longer exists anywhere — a
leftover reference would fail here.)

- [ ] **Step 7: Manual verification**

Open a report with at least one categorical question. In Select, tick that
question. In Design, use "Compare groups" to add a split-by-group variant
of it, so the deck now holds two slides for the same question. Open Design
— watch BOTH slides generate their own AI title independently (the
placeholder dashes clear on each on its own schedule, not simultaneously
tied together). Confirm the two titles differ (the Compare-groups one
mentions the classifying variable; the total one does not). Hand-edit one
slide's title, then trigger a regeneration on the other (e.g. change its
classifying variable) — confirm the hand-edited slide's title is
untouched.

- [ ] **Step 8: Run the whole backend suite as a smoke check**

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: no new failures (this task touches no backend code, but confirms
nothing upstream broke while this plan was being executed).

- [ ] **Step 9: Commit**

```bash
git add web/src/components/wizard/ReportWizard.tsx web/src/components/wizard/StepConfigure.tsx
git commit -m "fix(web): a Compare-groups slide no longer shares its AI title with the total slide"
```

---

## Not in this plan

* **Sign-in itself** (OIDC, sessions, the login page) — Plan 2, already
  landed on this branch.
* **The permission model, route guards, the census** — Plan 1, already
  landed on this branch.
* **API-provider email delivery** (SendGrid, SES, Postmark) — spec §6 names
  it as an option; SMTP is the smallest thing that works and the transport
  is injectable, so adding a provider later is a second `Sender` function,
  not a rewrite.
* **Per-field or per-report permissions, groups, SCIM, audit UI** — spec
  §13, unchanged.
* **Gating the Users tab's visibility more thoroughly than a single
  `useSession().data?.is_admin` check** — noted in Task 9 as a first cut;
  the backend enforcement (`require_admin` on every route) is what
  actually matters and does not depend on this.
* **Rate-limiting `POST /users/invite`** — not asked for by the spec or the
  task brief; an admin-only route behind a session is not an anonymous
  attack surface the way `/auth/register` is.

## Self-review

**Spec coverage.**

* §5, "the last admin cannot be removed or demoted" — Task 2
  (`auth/users.py`), exercised over HTTP in Task 6, and reused by Task 5's
  `revoke_invitation` so the rule holds on that path too.
* §5, "a grant naming a customer or case that no longer exists is ignored"
  — already enforced by Plan 1's `_admits`/`may_read`; Task 6's
  `_grant_out` additionally SHOWS such a grant (with no name) so an admin
  can find and clear it, rather than hiding it from the list entirely.
* §6, invitations end to end — the record and its expiry (Task 3), the
  email attempt with an injectable transport (Task 4), creation and
  revocation including "revoking an accepted invitation removes the user"
  (Task 5), consumption at sign-in matched by verified email (Task 5), the
  HTTP surface (Task 6), and the Users screen's invite flow (Task 9).
  "The link to nSight Studio login, not a datahive link" — Task 5's
  `create_invitation` takes `login_url` from Task 6's `public_origin(request) + "/login"`,
  never anything datahive-shaped; asserted directly by
  `test_the_link_is_studios_own_login_never_datahives`.
* §8, the workspace move — Task 7 (backend) and Task 8 (frontend); the two
  nginx/Vite deployment changes §8 also lists were Plan 2's Task 8, already
  landed.
* The two controller-flagged fixes — the break-glass condition (Task 1) and
  `updateChartByRef` (Task 10), both diagnosed from the actual code before
  any fix was proposed.

**Placeholder scan.** Every task's code is concrete and specific to that
task; no "similar to Task N" stands in for logic. The one place this plan
names something as a judgement call rather than a spec-mandated fact is
Task 9's Step 3 closing note (gating the Users tab's own visibility with
`useSession`), which is stated as exactly that — a first cut, with the
actual security boundary (`require_admin`) already in place regardless.

**Type consistency.** `LastAdminRefused` (Task 2) is returned — never
raised — by both `users.remove_user`/`set_admin` and, via composition,
`invites.revoke_invitation` (Task 5); every route that can produce it
(Task 6) checks `isinstance(result, users.LastAdminRefused)` the same way
Plan 2's `SignInRefused` is checked everywhere it can appear.
`Invitation`/`Invite` are used consistently: `Invite` is the datahive
record (Task 3), `Invitation` (Task 5) is that record plus `link`/`emailed`
— routes never conflate the two. `ChartSpec.slide_id` (Task 10) is threaded
through every function this plan touches with the same name and the same
"identifies one chart instance" meaning it already carried at its
definition.

**Codebase claims re-verified while writing:** `email.json`/`oidc.json`
naming and the "never echo a secret" rule (read `routes_settings.py`
directly); no SMTP/mail library anywhere in `src/` or `pyproject.toml`
(checked with `python3`-driven `grep`, not raw `grep`, per this task's own
warning about silent false negatives); `slide_id`'s existing definition and
its three current call sites (`ReportWizard.tsx` lines 183–211); `Session`,
`Repository._write_json`/`_read_json`, `find_case`/`find_customer` taking
`user=None` by default (Plan 1, already landed); `identity.py`'s literal
"NOTE for whoever implements Plan 3" comment, still present in the file at
the time of writing, quoted exactly in Task 5 rather than paraphrased; the
current baseline test count (1735 passed, 1 known failure, 2 skipped),
obtained by actually running the suite, not assumed from Plan 1's
now-stale figure.

**Gap this plan could not fully close:** the Users screen's grant editor
(Task 9) only offers customer-level grants, not case-level ones — the task
brief's own words ("Granting access — per customer") match this scope, and
the backend (`PUT /users/{id}/grants`) accepts either shape regardless, so
a case-level grant set some other way (a script, a future admin tool) still
displays correctly (Task 6's `_grant_out` resolves `case_name` too) even
though this plan's UI cannot create one.
