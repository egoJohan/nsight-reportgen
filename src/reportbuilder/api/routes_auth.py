"""Sign-in over HTTP: password today (Part A), Google and Microsoft once
Part B lands (spec §4). Every route here is either in PUBLIC_ROUTES or
guarded by `current_user` like anything else — see deps_auth.py.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth import identity, password, session
from reportbuilder.auth.keys import get_or_create_signing_key
from reportbuilder.auth.permissions import User
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

auth_router = APIRouter(tags=["auth"], prefix="/auth")


def _bootstrap_admins() -> frozenset[str]:
    raw = os.environ.get("NSIGHT_BOOTSTRAP_ADMINS", "")
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


def _issue_session(response: Response, repo: Repository, auth: AuthContext, user_id: str) -> None:
    key = get_or_create_signing_key(repo, auth)
    session_id = session.create(repo, auth, user_id)
    response.set_cookie(
        session.COOKIE_NAME, session.cookie_value(key, session_id),
        max_age=session.IDLE_TIMEOUT_SECONDS, httponly=True, secure=True,
        samesite="strict", path="/",
    )


def _user_out(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "is_admin": user.is_admin}


@auth_router.post("/register", status_code=201)
def register(response: Response, body: dict = Body(...),
            auth: AuthContext = Depends(get_auth),
            repo: Repository = Depends(get_repository)) -> dict:
    """Self-service, but gated exactly like a first OIDC sign-in (spec §3.1,
    §5 domain auto-join, Task 4): only creates an account nSight would have
    created for this email anyway. A password is not a bypass of that gate.
    """
    email = (body.get("email") or "").strip()
    pw = body.get("password") or ""
    if len(pw) < 12:
        raise HTTPException(422, "Password must be at least 12 characters")

    resolved = identity.resolve_signed_in_user(repo, auth, email, _bootstrap_admins())
    if isinstance(resolved, identity.SignInRefused):
        raise HTTPException(403, resolved.reason)
    if repo.get_password_hash(auth, resolved.id) is not None:
        raise HTTPException(409, "This account already has a password")

    repo.set_password(auth, resolved.id, password.hash_password(pw))
    _issue_session(response, repo, auth, resolved.id)
    return _user_out(resolved)


@auth_router.post("/login/password")
def login_password(response: Response, body: dict = Body(...),
                   auth: AuthContext = Depends(get_auth),
                   repo: Repository = Depends(get_repository)) -> dict:
    email = (body.get("email") or "").strip().lower()
    pw = body.get("password") or ""
    user = repo.find_user_by_email(auth, email)
    stored_hash = repo.get_password_hash(auth, user.id) if user else None
    # Always verify against SOMETHING, so a wrong password and an unknown
    # email cost the same Argon2 pass -- no timing tell for either.
    ok = password.verify_password(stored_hash or password.DUMMY_HASH, pw)
    if not user or not stored_hash or not ok:
        raise HTTPException(401, "Incorrect email or password")
    _issue_session(response, repo, auth, user.id)
    return _user_out(user)


@auth_router.post("/logout")
def logout(request: Request, response: Response,
          auth: AuthContext = Depends(get_auth),
          repo: Repository = Depends(get_repository)) -> dict:
    """Idempotent: no cookie, or an already-dead one, is still a 200."""
    raw = request.cookies.get(session.COOKIE_NAME)
    if raw:
        key = get_or_create_signing_key(repo, auth)
        session_id = session.session_id_from_cookie(key, raw)
        if session_id:
            session.revoke(repo, auth, session_id)
    response.delete_cookie(session.COOKIE_NAME, path="/")
    return {"ok": True}


@auth_router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return _user_out(user)
