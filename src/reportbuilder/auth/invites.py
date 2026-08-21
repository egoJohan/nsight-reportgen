"""Inviting someone to nSight Studio by email, and consuming that
invitation on their first sign-in (spec §6).

Every step after create_invitation runs through identity.py: an
invitation only ever gets APPLIED when the invited address itself signs
in and its verified email matches -- see resolve_signed_in_user's
consumption branch, added alongside this module. This module owns only
the two admin-facing halves: creating the record (and best-effort
emailing it), and revoking it -- whether it is still pending or has
already turned into a user.
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
    """What `create_invitation` hands back to the route: the stored
    record, the link the admin can copy by hand, and whether email
    delivery actually happened -- so the UI can show "emailed" or fall
    back to "copy this link" (Task 4's design, spec §6) without a second
    round trip."""
    invite: Invite
    link: str
    emailed: bool


def create_invitation(repo: Repository, auth: AuthContext, *, email: str,
                      grants: tuple[Grant, ...], invited_by: User,
                      login_url: str, sender: Sender = send_via_smtp) -> Invitation:
    """Record the invitation, then try to send it. Spec §6: "delivery may
    fail without failing the invitation" -- the record exists either way;
    only `emailed` says whether the admin also needs to copy the link by
    hand.

    *login_url* is nSight Studio's own sign-in page (spec D5) -- never a
    datahive link -- and it is *link*, unmodified, on the returned
    `Invitation`; the invite id/token is never appended to it, so nothing
    downstream can rely on the URL to look this invitation up. The
    invited person is identified only by the verified email they sign in
    with, matched at consumption time (see identity.py).

    Whether *email* already belongs to an account is deliberately not
    checked here -- see identity.py's consumption branch for why: an
    existing account always wins over a pending invite, so recording one
    for an already-registered address cannot escalate anyone's access.
    """
    invite = repo.create_invite(auth, email, grants, invited_by.id,
                                lifetime_seconds=DEFAULT_LIFETIME_SECONDS)
    config = mailer.config_from_settings(repo.get_setting(auth, mailer.EMAIL_KEY))
    emailed = (config is not None
              and sender(config, invite.email, _SUBJECT, _body(invited_by.email, login_url)))
    return Invitation(invite=invite, link=login_url, emailed=bool(emailed))


def revoke_invitation(repo: Repository, auth: AuthContext,
                      invite_id: str) -> "users.LastAdminRefused | None":
    """Delete a pending invite outright. For an ACCEPTED one, spec §6:
    "revoking an accepted invitation removes the user" -- routed through
    `users.remove_user` so the last-admin rule applies here too, not just
    on the Users list's own remove button, and so the sessions/last-admin
    handling those two share never has to be duplicated.

    An unknown invite id is a no-op, the same idempotent-under-a-double-
    click shape `users.remove_user` gives an unknown user id.
    """
    invite = repo.get_invite(auth, invite_id)
    if invite is None:
        return None
    if invite.accepted_user_id:
        refused = users.remove_user(repo, auth, invite.accepted_user_id)
        if refused is not None:
            return refused
    repo.delete_invite(auth, invite_id)
    return None
