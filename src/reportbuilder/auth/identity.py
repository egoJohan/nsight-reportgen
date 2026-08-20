"""Turning a VERIFIED email into a User (spec §3.1, §4 step 3, §5 domain
auto-join).

Every sign-in method — Google, Microsoft, password — ends up here with
nothing but an email that has already been proven to belong to whoever is
at the browser. What happens next is provider-agnostic, which is why it is
not in oidc.py or routes_auth.py.

Invitations (spec §4's middle branch, "a pending invitation -- consume it")
are Plan 3: no settings/invite/* record exists yet, so there is nothing for
that branch to consume. Until then, a new user's only way in is the
bootstrap admin or an allowed domain.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

log = logging.getLogger(__name__)

_ACCESS_KEY = "access.json"


@dataclass(frozen=True)
class SignInRefused:
    """Spec §10: "Verified email matches nothing" -> refused, no session, an
    audit line. `reason` is for the log, not the browser."""
    reason: str


def resolve_signed_in_user(repo: Repository, auth: AuthContext, email: str,
                           bootstrap_admins: frozenset[str]) -> User | SignInRefused:
    """*email* MUST already be verified by an identity provider — never a
    value a browser supplied directly. This function only decides what
    happens once that proof exists.
    """
    normalized = (email or "").strip().lower()
    if not normalized or "@" not in normalized:
        return SignInRefused(f"'{email}' is not an email address")

    existing = repo.find_user_by_email(auth, normalized)
    if existing is not None:
        return existing

    if not repo.list_users(auth) and normalized in bootstrap_admins:
        log.warning("sign-in: '%s' becomes the first admin (NSIGHT_BOOTSTRAP_ADMINS)",
                   normalized)
        return repo.save_user(auth, User(id="", email=normalized,
                                         name=normalized.split("@", 1)[0],
                                         is_admin=True, grants=()))

    domain = normalized.rsplit("@", 1)[-1]
    access = repo.get_setting(auth, _ACCESS_KEY) or {}
    allowed = {d.strip().lower() for d in access.get("allowed_domains", []) if d.strip()}
    if domain in allowed:
        grants = tuple(Grant(g["scope"], g.get("mode", "view"))
                       for g in access.get("default_grants", []) if g.get("scope"))
        log.info("sign-in: '%s' auto-joins via domain '%s'", normalized, domain)
        return repo.save_user(auth, User(id="", email=normalized,
                                         name=normalized.split("@", 1)[0],
                                         is_admin=False, grants=grants))

    log.warning("sign-in refused: '%s' is not a known user, admin, or allowed domain",
               normalized)
    return SignInRefused(f"'{normalized}' is not registered and its domain is not allowed")
