"""Asking for an account, having already proved who you are.

An invitation-only product has a dead end in it: somebody who belongs here but
has not been invited signs in with their work account, is refused, and has
nowhere to go but out-of-band email. These routes close that loop without
opening the thing an invitation-only product exists to avoid — a way to get in
without an admin.

Two properties do all the work.

**The identity is the provider's, not the caller's.** The email on a request
comes from a signup ticket, minted by the OIDC callback out of a token Google
or Microsoft signed (auth/signup_ticket.py). There is no field in any body
here naming who is asking. So an admin reviewing the queue is looking at
addresses their owners demonstrably control, not at anything typed into a form
— which is why this needs no CAPTCHA: the bot check already happened, at a
scale we could not match, and it happened against a real identity rather than
a puzzle.

**Approving grants nothing new.** It creates an INVITATION, the same call an
admin makes from the Users screen, which creates the account with the grants
the admin picks. There is no second account-minting path here to keep in step
with the first.

A request is not access. It is a row in a queue, and until an admin acts on it
the person who filed it can do exactly what they could before: nothing.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from reportbuilder.api.deps_auth import current_user, require_admin
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth import invites, signup_ticket
from reportbuilder.auth.keys import get_or_create_signing_key
from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store.repository import Repository, SignupRequest
from reportbuilder.store.seam import AuthContext

log = logging.getLogger(__name__)

signup_requests_router = APIRouter()


def _out(r: SignupRequest) -> dict:
    return {"id": r.id, "email": r.email, "provider": r.provider, "name": r.name,
            "requested_at": r.requested_at, "state": r.state,
            "decided_by": r.decided_by, "decided_at": r.decided_at}


def _ticket(request: Request, repo: Repository, auth: AuthContext) -> dict:
    """What the provider vouched for, or 401.

    The ONLY source of identity on this route. Nothing here reads a body field
    for an email, so there is no shape of request that files an ask on somebody
    else's behalf.
    """
    key = get_or_create_signing_key(repo, auth)
    claims = signup_ticket.read_ticket(
        key, request.cookies.get(signup_ticket.COOKIE_NAME, ""))
    if claims is None:
        raise HTTPException(401, "Sign in with Google or Microsoft first.")
    return claims


@signup_requests_router.get("/signup/me")
def who_is_asking(request: Request, auth: AuthContext = Depends(get_auth),
                  repo: Repository = Depends(get_repository)) -> dict:
    """Who the caller is, and what the page should therefore say.

    One call answering the whole decision, so the page never has to infer a
    state from the shape of an error:

    - ``has_account``  they were invited while holding this ticket; the answer
                       is "sign in again", not "ask".
    - ``pending``      they already asked and nobody has decided yet; the
                       answer is "we have it, you will get an email".
    - otherwise        they can ask.

    Needs no account — but it reveals only what the caller's own cookie already
    contains, and 401s without one.
    """
    claims = _ticket(request, repo, auth)
    return {
        **claims,
        "has_account": repo.find_user_by_email(auth, claims["email"]) is not None,
        "pending": repo.find_pending_signup_request(auth, claims["email"]) is not None,
    }


@signup_requests_router.post("/signup-requests", status_code=201)
def create_signup_request(request: Request, auth: AuthContext = Depends(get_auth),
                          repo: Repository = Depends(get_repository)) -> dict:
    """File an ask for an account, for the address on the caller's ticket."""
    claims = _ticket(request, repo, auth)
    if repo.find_user_by_email(auth, claims["email"]) is not None:
        # They already have an account and simply could not reach it — filing a
        # request would put a row in front of an admin that resolves to "they
        # already have this". Nothing is revealed: it is their own address.
        raise HTTPException(409, "That address already has an account. Try signing in again.")
    r = repo.create_signup_request(auth, claims["email"], claims["provider"],
                                   claims.get("name", ""))
    log.info("signup requested by %s (%s)", r.email, r.provider)
    return _out(r)


@signup_requests_router.get("/signup-requests")
def list_signup_requests(auth: AuthContext = Depends(get_auth),
                         repo: Repository = Depends(get_repository),
                         admin: User = Depends(require_admin)) -> list[dict]:
    """The queue: people waiting, and nobody else.

    Admin-only — these are addresses of people outside the hive, which is not
    something a customer's owner has any business reading. Only PENDING rows
    are listed: an approved request has become an account (visible on the Users
    screen, which is the better place to look at it) and a refused one is gone.
    """
    return [_out(r) for r in repo.list_signup_requests(auth) if r.state == "pending"]


class ApproveBody(BaseModel):
    grants: list[dict] = []


@signup_requests_router.post("/signup-requests/{request_id}/approve")
def approve_signup_request(request_id: str, request: Request,
                           body: ApproveBody = Body(default=ApproveBody()),
                           auth: AuthContext = Depends(get_auth),
                           repo: Repository = Depends(get_repository),
                           admin: User = Depends(require_admin)) -> dict:
    """Invite them, with the grants the admin chose.

    Deliberately the SAME call as the Users screen's invite button: the account
    and its access are created by `invites.create_invitation` and nowhere else,
    so there is one path that brings an account into being and one place to
    audit it.
    """
    r = repo.get_signup_request(auth, request_id)
    if r is None:
        raise HTTPException(404, f"Signup request '{request_id}' not found")
    if r.state != "pending":
        raise HTTPException(409, f"Already {r.state}")
    if repo.find_user_by_email(auth, r.email) is not None:
        raise HTTPException(409, f"'{r.email}' already has an account")
    try:
        grants = tuple(Grant(g["scope"], g.get("mode", "view"))
                       for g in body.grants if g.get("scope"))
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc

    from reportbuilder.api.routes_auth import public_origin

    invitation = invites.create_invitation(
        repo, auth, email=r.email, grants=grants, invited_by=admin,
        login_url=f"{public_origin(request)}/login")
    decided = repo.decide_signup_request(auth, request_id, "approved", admin.id)
    log.info("signup approved for %s by %s (emailed=%s)",
             r.email, admin.email, invitation.emailed)
    # `emailed` is reported rather than assumed: the person was told they would
    # hear by email, and an admin whose SMTP is unconfigured needs to know they
    # have to say so themselves.
    return {**_out(decided), "emailed": invitation.emailed,
            "link": invitation.link}


@signup_requests_router.delete("/signup-requests/{request_id}", status_code=204)
def refuse_signup_request(request_id: str, auth: AuthContext = Depends(get_auth),
                          repo: Repository = Depends(get_repository),
                          admin: User = Depends(require_admin)) -> None:
    """Decline: the row goes.

    Unlike a refused INVITATION — which is kept, because it records a decision
    an admin took about somebody who is in the system — this is a stranger who
    asked and was not let in. Keeping a permanent list of outsiders who once
    knocked serves nobody, and it would mean an address could never ask again
    after one refusal, which is the wrong answer when the refusal was simply
    "not yet" or a mistake.

    Deleting also means the person can ask again after signing in once more,
    which is the natural retry and costs an admin one more line in the queue.
    """
    r = repo.get_signup_request(auth, request_id)
    if r is None:
        raise HTTPException(404, f"Signup request '{request_id}' not found")
    # Marked first, removed second. The mark is what takes it out of the queue,
    # and it cannot fail; the delete is tidying and is allowed to.
    repo.decide_signup_request(auth, request_id, "refused", admin.id)
    repo.delete_signup_request(auth, request_id)
    log.info("signup refused for %s by %s", r.email, admin.email)


__all__ = ["signup_requests_router"]
