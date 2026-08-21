"""Emailing the people who can act on an access request -- the ones
`_require_decider` (api/routes_access_requests.py) would let approve or
refuse it: every admin, and anyone already holding `edit` on the customer
the request names (this model's only notion of "owns this customer" --
see auth/permissions.py).

Reuses mailer.py's transport and config exactly the way auth/invites.py
does -- no second mail path, no provider dependency, `send_via_smtp` never
raises. Filing a request must survive a mail failure the same way an
invitation survives one (spec §6's rule, extended here): SMTP is unlikely
to be configured on most installs, and `create_access_request` must not
fail, or even appear to behave differently, just because nobody's inbox
got the memo.
"""
from __future__ import annotations

from reportbuilder.auth import mailer
from reportbuilder.auth.mailer import Sender, send_via_smtp
from reportbuilder.auth.permissions import EDIT, User
from reportbuilder.store.repository import AccessRequest, Repository
from reportbuilder.store.seam import AuthContext

_SUBJECT = "A permission request is waiting for you"


def _body(request: AccessRequest, customer_name: str, settings_url: str) -> str:
    return (
        f"{request.user_email} is asking for {request.mode} access to "
        f"{customer_name}.\n\n"
        f"Decide it here: {settings_url}\n\n"
        "Sign in and open Settings → Permission requests to approve or "
        "refuse it.\n"
    )


def decision_makers(repo: Repository, auth: AuthContext, *, customer_id: str,
                    exclude_user_id: str) -> list[User]:
    """Everyone who could act on a request naming *customer_id* --
    every admin, plus every `edit` holder on that customer -- minus
    *exclude_user_id* (the requester, even an admin or owner requesting a
    DIFFERENT customer: nobody needs an email telling them what they just
    did). Deduped by id: an admin who also happens to hold edit on the
    customer is one person, one email, not two.

    Mirrors the exact set `_require_decider` would let through, on
    purpose -- this list is "who CAN decide it", not a separate, looser
    notion of "who might be interested".
    """
    seen: dict[str, User] = {}
    for u in repo.list_users(auth):
        if u.id == exclude_user_id:
            continue
        if u.is_admin or any(g.scope == customer_id and g.mode == EDIT for g in u.grants):
            seen[u.id] = u
    return list(seen.values())


def notify_decision_makers(repo: Repository, auth: AuthContext, *,
                           request: AccessRequest, customer_name: str,
                           settings_url: str, sender: Sender = send_via_smtp) -> int:
    """Best-effort, same shape as `invites.create_invitation`: unconfigured
    or failed delivery is not an error, just nothing sent. The return value
    (how many sends the transport reported as successful) is for a log
    line, not for the requester -- they are not a recipient, and the route
    that calls this never surfaces "we told them" to them, so nothing here
    should tempt it into implying otherwise when SMTP is not configured
    (it usually is not, and `send_via_smtp` then returns False for every
    recipient without raising).

    One email PER recipient, deliberately not one message fanned out over
    To/Cc/Bcc: a customer's several owners should not learn each other's
    addresses just because they all hold edit on the same customer. That
    does mean a customer with many owners sends many small emails per
    request rather than one -- worth watching if that ever becomes real
    volume (a digest, a rate limit), but not worth building against a
    volume nobody has seen yet.
    """
    config = mailer.config_from_settings(repo.get_setting(auth, mailer.EMAIL_KEY))
    if config is None:
        return 0
    recipients = decision_makers(repo, auth, customer_id=request.customer_id,
                                 exclude_user_id=request.user_id)
    body = _body(request, customer_name, settings_url)
    return sum(1 for u in recipients if sender(config, u.email, _SUBJECT, body))


__all__ = ["decision_makers", "notify_decision_makers"]
