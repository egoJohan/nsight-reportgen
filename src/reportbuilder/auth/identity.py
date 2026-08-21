"""Turning a VERIFIED email into a User (spec §3.1, §4 step 3, §5 domain
auto-join).

Every sign-in method — Google, Microsoft, password — ends up here with
nothing but an email that has already been proven to belong to whoever is
at the browser. What happens next is provider-agnostic, which is why it is
not in oidc.py or routes_auth.py.

Invitations (spec §4's middle branch, "a pending invitation -- consume it")
are handled below, right after the `existing`-admin short-circuit: an
admin-issued invite for this exact address is fulfilled before the
email_domain_proven gate, bootstrap-admin or domain auto-join ever get a
look, and it only fires when no account for that address exists yet --
see the comment at that branch for why an existing account always wins
over a pending invite instead of silently absorbing its grants.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

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


def _any_admin(repo: Repository, auth: AuthContext) -> bool:
    """Whether the hive already has at least one admin -- the actual
    condition spec §3.1 promises recovery from ("a hive with no ADMIN
    exists," not "no users at all"). A hive can easily have users with
    none of them admin: every domain-auto-joined user is created with
    is_admin=False (see the branch below), so a colleague joining first
    must never block the break-glass path an operator needs after losing
    every admin."""
    return any(u.is_admin for u in repo.list_users(auth))


def resolve_signed_in_user(repo: Repository, auth: AuthContext, email: str,
                           bootstrap_admins: frozenset[str], *,
                           email_domain_proven: bool = True) -> User | SignInRefused:
    """*email* MUST already be verified by an identity provider — never a
    value a browser supplied directly. This function only decides what
    happens once that proof exists.

    *email_domain_proven* is a SEPARATE, weaker-by-default promise than
    "verified": whether whoever vouched for *email* also proved they
    control its DOMAIN, not merely that the token carrying it was
    authentic. Password sign-in and Google OIDC have no gap here (Google's
    `email_verified` is required True or `oidc.complete` never returns),
    so both default this to True. Microsoft's `organizations` (multi-tenant)
    discovery is the one caller that can pass False — see oidc.py's module
    docstring for `xms_edov` and exactly why: an attacker's own free Entra
    tenant can mint a token with a genuine signature and a genuine `email`
    claim set to ANYONE'S address, so an unproven email must never be trusted to
    MINT a new account (bootstrap admin or domain auto-join, below) the way
    a proven one is. It may still resolve to an account that already
    exists — see the guard right below — because that requires the
    attacker to have already guessed a real nSight user's exact email, and
    even then only takes over that account if the real owner's tenant is
    *also* not asserting ownership. Fail closed: only `True` counts as
    proven, so callers that don't know any better (and every caller other
    than the Microsoft OIDC path) get the safe default.
    """
    normalized = (email or "").strip().lower()
    if not normalized or "@" not in normalized:
        return SignInRefused(f"'{email}' is not an email address")

    existing = repo.find_user_by_email(auth, normalized)
    if existing is not None and existing.is_admin:
        # Already an admin: nothing for break-glass to do, ordinary sign-in.
        return existing

    # A pending invitation is fulfilled here, ABOVE the email_domain_proven
    # guard below and gated on `existing is None` -- consuming one an admin
    # already issued for this exact address is not "minting an account from
    # an unproven claim" the way bootstrap-admin/domain auto-join further
    # down are; it is closer to "matches an existing record", same as the
    # `existing` check above, and this is exactly the carve-out the
    # xms_edov design allowed for (see oidc.py's module docstring).
    #
    # The `existing is None` gate matters on its own: if this exact email
    # already has an account -- e.g. it auto-joined via an allowed domain
    # after the invite was sent, or someone guessed/collided with an
    # invited address -- a pending invite must never silently graft its
    # grants onto that account. An existing account always wins; the
    # invite is simply left pending (an admin can still see and revoke it
    # explicitly) rather than becoming a way to escalate an account's
    # access just by matching its email.
    if existing is None:
        pending = repo.find_pending_invite_by_email(auth, normalized)
        if pending is not None:
            user = repo.save_user(auth, User(id="", email=normalized,
                                             name=normalized.split("@", 1)[0],
                                             is_admin=False, grants=pending.grants))
            repo.mark_invite_accepted(auth, pending.id, user.id)
            log.info("sign-in: '%s' accepted its invitation (%s)", normalized, pending.id)
            return user

    if not email_domain_proven:
        if existing is not None:
            return existing
        log.warning(
            "sign-in refused: '%s' has no proven domain ownership and is not a known user "
            "(new-account creation is refused for an unproven email; see oidc.py's module "
            "docstring on xms_edov)", normalized)
        return SignInRefused(f"'{normalized}' is not a known user and its domain ownership is unproven")

    # Break-glass: spec §3.1 promises recovery whenever the hive has NO ADMIN
    # (see _any_admin), not merely when it has no users at all -- a hive can
    # easily have only non-admin users (every domain-auto-joined colleague is
    # one). This is deliberately wide open to anyone NSIGHT_BOOTSTRAP_ADMINS
    # names, with no other check, because it costs an attacker nothing they
    # don't already have: setting that variable requires control of the
    # server's environment, which is already full control of the machine.
    # Don't narrow this back thinking it tightens security -- it doesn't.
    if not _any_admin(repo, auth) and normalized in bootstrap_admins:
        if existing is not None:
            # The bootstrap email may already have an account -- e.g. domain
            # auto-join created it before any admin existed. Promote that
            # record in place rather than mint a colliding second one.
            log.warning("sign-in: '%s' is promoted to admin in place (NSIGHT_BOOTSTRAP_ADMINS)",
                       normalized)
            return repo.save_user(auth, replace(existing, is_admin=True))
        log.warning("sign-in: '%s' becomes the first admin (NSIGHT_BOOTSTRAP_ADMINS)",
                   normalized)
        return repo.save_user(auth, User(id="", email=normalized,
                                         name=normalized.split("@", 1)[0],
                                         is_admin=True, grants=()))

    if existing is not None:
        return existing

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
