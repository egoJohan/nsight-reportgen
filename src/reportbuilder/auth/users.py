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
    """Delete *user_id*, their grants, their password hash if they had one,
    and every live session of theirs (spec §7: "deleting a user...ends it"
    -- sessions are dropped here too, rather than left to the ordinary idle
    timeout, so revocation does not wait on the 30s resolution cache the
    way a plain sign-out would). `Repository.delete_user` owns the grants
    and password cleanup, so an orphaned password hash cannot outlive the
    account it belonged to. A user already gone is a no-op, not an error --
    the route this backs is naturally idempotent under a double-click.

    `delete_user` does not swallow `ConsentRequired` -- it is a deliberate,
    attended deletion of an account, unlike sign-out, so the gate (floor rule
    4) is left to propagate here too, the same as every other destructive
    delete in this codebase (`routes_cases.py`, `routes_materials.py`,
    `routes_reports.py`, `routes_settings.py`). It reaches production only in
    theory: nSight's own admin bearer already carries that authority, so the
    call just succeeds there. The caller that turns this into a 409 with the
    approval envelope is `routes_users.py` (Task 6), not this module.
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
