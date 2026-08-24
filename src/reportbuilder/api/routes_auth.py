"""Sign-in over HTTP: password (Part A), and Google/Microsoft SSO (Part B,
spec §4). Every route here is either in PUBLIC_ROUTES or guarded by
`current_user` like anything else — see deps_auth.py.
"""
from __future__ import annotations

import logging
import hashlib
from urllib.parse import quote
import os

import httpx
import itsdangerous
from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.api.routes_settings import OIDC_KEY
from reportbuilder.auth import identity, oidc, password, session
from reportbuilder.auth.keys import get_or_create_signing_key
from reportbuilder.auth.permissions import EDIT, User
from reportbuilder.auth.ratelimit import RateLimiter
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

log = logging.getLogger(__name__)

_OIDC_PROVIDERS = ("google", "microsoft")

# The OIDC-state cookie: carries {state, nonce, next} across the redirect to
# the provider and back. HttpOnly/Secure like the session cookie, but
# SameSite=Lax rather than Strict -- the callback is a top-level GET
# navigation arriving FROM Google/Microsoft, a cross-site request, and a
# Strict cookie is never attached to that; only Lax survives a cross-site
# top-level GET. Scoped to /auth (never sent to a data route), 10-minute
# Max-Age (long enough for a consent screen), single-use -- cleared in the
# callback whether it succeeds or fails. Signed with the same key as the
# session cookie, a different `salt` for domain separation.
_OAUTH_COOKIE = "nsight_oauth"
_OAUTH_SALT = "nsight-oauth-state-v1"
_OAUTH_MAX_AGE = 600  # 10 minutes


def _oauth_codec(key: bytes) -> itsdangerous.URLSafeTimedSerializer:
    return itsdangerous.URLSafeTimedSerializer(key, salt=_OAUTH_SALT)


def _trust_forwarded_headers(request: Request) -> bool:
    """Whether X-Forwarded-Proto / X-Forwarded-Host may be trusted for this
    request.

    A forwarded-header bug is a redirect hijack in the worst case: whoever
    can set these headers steers the OAuth `redirect_uri` -- and therefore
    where the session cookie ends up -- wherever they like. So they are
    honoured only when the request cannot have come from anyone but our own
    reverse proxy, or from someone no worse positioned than it:

    - loopback (127.0.0.1 / ::1), or Starlette's TestClient (host
      "testclient") -- true in dev, where Vite's proxy and the backend both
      run on 127.0.0.1 and nothing outside the machine can reach
      127.0.0.1:8200; and true for the test suite's in-process client. This
      does admit any OTHER process on the same machine, not only Vite --
      accepted deliberately: reaching 127.0.0.1:8200 at all already requires
      local code execution on this host, and a process with that is not
      made meaningfully more dangerous by also being able to steer an OAuth
      redirect (it can already read the session key, the datahive token, or
      the browser's cookies directly). Standard practice elsewhere for the
      same reason -- e.g. Rails' RemoteIp, Werkzeug's ProxyFix -- trusts
      loopback as the proxy hop by default.
    - NSIGHT_TRUST_FORWARDED_HEADERS=1, set only in the container
      deployments (docker-compose*.yml). There the backend `expose`s 8200 to
      the compose network and publishes no port of its own -- nginx is
      structurally the only thing that can ever open a connection to it, so
      any request that arrives has already come from the trusted proxy.

    Neither condition holds for a backend an arbitrary client can reach
    directly -- there the header is ignored and `request.url_for`'s own
    origin is used instead: wrong-but-safe (nothing attacker-controlled is
    trusted), never a hijack.
    """
    host = request.client.host if request.client else None
    if host in {"127.0.0.1", "::1", "testclient"}:
        return True
    return os.environ.get("NSIGHT_TRUST_FORWARDED_HEADERS") == "1"


def public_origin(request: Request) -> str:
    """The browser-facing origin (scheme://host).

    This has to be the origin the BROWSER is using, not the one the backend
    received the request on: Vite (dev) and nginx (prod) sit in front of the
    backend and proxy /auth to it, so `request.url_for` alone builds a
    backend-only URL (127.0.0.1:8200) that was never registered with the
    provider and that the browser never talks to. Preference order:

      1. NSIGHT_PUBLIC_URL, if set -- an explicit override for deployments
         behind a proxy this heuristic doesn't recognise, and the only way
         to pin this value deterministically in a test.
      2. X-Forwarded-Proto / X-Forwarded-Host, if the request is trusted to
         set them (see _trust_forwarded_headers) -- the normal dev/prod
         path, honouring what Vite/nginx actually forwarded.
      3. request.url's own origin -- the pre-proxy fallback: wrong (not
         browser-facing) when a proxy is in play, but safe, and still
         correct when the backend really is hit directly.

    Factored out of `_callback_url` for routes_users.py's invitation link,
    which points at /login, a client-side React Router route with no
    FastAPI url_for name to hang a path off.
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
    """The browser-facing URL Google/Microsoft must redirect back to. See
    `public_origin` for the preference order that makes this the browser's
    origin rather than the backend's own.
    """
    path = request.url_for("oidc_callback", provider=provider)
    return public_origin(request) + path.path

auth_router = APIRouter(tags=["auth"], prefix="/auth")

_REGISTER_REFUSED_MESSAGE = "Registration is not available for this email"


def _bootstrap_admins() -> frozenset[str]:
    raw = os.environ.get("NSIGHT_BOOTSTRAP_ADMINS", "")
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


#: Sign-in attempt limits. Per (address, email) so one person's fumbling never
#: bars a colleague, and per address as well so working through a list of emails
#: from one place is counted as the single campaign it is. Failures only —
#: getting your own password right is never counted against you.
_LOGIN_ATTEMPTS = RateLimiter(limit=10, window=15 * 60)
_LOGIN_ATTEMPTS_BY_ADDRESS = RateLimiter(limit=50, window=15 * 60)


#: How many proxies append to X-Forwarded-For between the browser and us. nginx
#: is one (`$proxy_add_x_forwarded_for`); staging puts Caddy in front, making
#: two. Counting from the WRONG end is not a detail — see _client_address.
_TRUSTED_PROXY_HOPS = max(1, int(os.environ.get("NSIGHT_TRUSTED_PROXY_HOPS") or 1))


def _client_address(request: Request) -> str:
    """Who is asking, for rate-limiting purposes.

    Behind nginx every request arrives from the proxy, so counting
    `request.client.host` would count the whole world as one caller and bar
    everybody the moment anybody guessed. So X-Forwarded-For it is — but read
    from the RIGHT end.

    nginx sets `X-Forwarded-For $proxy_add_x_forwarded_for`, which PREPENDS
    whatever the client sent and appends the address it saw. The leftmost entry
    is therefore whatever the caller typed. Reading it gave an attacker both
    halves of the key: rotating it made brute force unlimited (250 attempts, no
    429, every one an Argon2 pass), and setting it to somebody else's address
    locked that person out of their own account.

    Each trusted proxy appends exactly one entry, so the caller's real address
    is `_TRUSTED_PROXY_HOPS` from the right. Anything to the left of that is
    caller-supplied and is ignored.
    """
    if _trust_forwarded_headers(request):
        parts = [p.strip() for p in
                 (request.headers.get("x-forwarded-for") or "").split(",")
                 if p.strip()]
        if len(parts) >= _TRUSTED_PROXY_HOPS:
            return parts[-_TRUSTED_PROXY_HOPS]
        if parts:
            # Fewer hops than configured: the header did not come the way we
            # were told it would, so trust only what we saw ourselves.
            pass
    client = request.client
    return client.host if client else "unknown"


def _refuse_if_too_many_attempts(request: Request, email: str) -> tuple[str, str]:
    """Stop here if this caller has been guessing. Returns the two keys to
    record a failure against."""
    address = _client_address(request)
    # The email is caller-supplied and unbounded — nginx accepts a 50 MB body,
    # and a retained key held a 200 000-character address verbatim. Hash it: the
    # key only ever needs to be stable and distinct, never readable.
    by_user = f"{address}|{hashlib.sha256(email.encode('utf-8')).hexdigest()[:32]}"
    for key, limiter in ((by_user, _LOGIN_ATTEMPTS),
                         (address, _LOGIN_ATTEMPTS_BY_ADDRESS)):
        if not limiter.allows(key):
            wait = limiter.retry_after(key)
            raise HTTPException(
                429, "Too many sign-in attempts. Try again in "
                     f"{max(1, wait // 60)} minutes.",
                headers={"Retry-After": str(wait)})
    return by_user, address


def _safe_next(value: str | None) -> str:
    r"""Where to send the browser after a successful sign-in, made safe.

    `next` arrives in the query string, is signed into the state cookie, and
    was then used verbatim as a Location header. A link to our own sign-in
    with `?next=https://evil.example/` therefore walked the victim through a
    genuine Google consent screen and dropped them on the attacker's page,
    still believing they were inside nSight — the useful half of a phishing
    flow, hosted on our domain and our TLS certificate.

    Only a path within this app is allowed. `//host` and `/\host` are excluded
    because browsers read both as protocol-relative, i.e. as another origin;
    control characters because a Location header is a header. Anything else
    becomes the app root, which is where the sign-in button sends you anyway.

    Applied both when it is captured AND when it is used: state cookies signed
    before this existed are still valid for their lifetime.
    """
    v = (value or "").strip()
    if not v.startswith("/") or v.startswith("//") or v.startswith("/\\"):
        return "/"
    if any(c in v for c in "\r\n\t\x00"):
        return "/"
    # A Location header is latin-1 on the wire. A path with non-latin-1 text in
    # it — "/日本", or a stray U+2028 — raised inside the response and turned the
    # END of a real sign-in into a 500. Percent-encode rather than refuse: the
    # author of that link is usually the app itself, deep-linking to a case with
    # a Finnish name.
    try:
        v.encode("latin-1")
    except UnicodeEncodeError:
        v = quote(v, safe="/?&=#%+,;:@!$'()*~[]")
    return v


def _cookies_are_secure(request: Request) -> bool:
    """Whether our cookies may be marked Secure — i.e. whether the BROWSER
    reached us over https.

    Hardcoding it made the app unusable on plain HTTP: the browser accepts the
    Set-Cookie and then declines to send it back, so signing in appears to work
    and every subsequent request is anonymous. That is every deployment reached
    by LAN address or hostname without TLS, which includes the machines a
    product test runs on.

    Nothing is given up. A Secure cookie on http is not protection, it is a
    cookie that never arrives; and the scheme here comes from `public_origin`,
    the same value the OAuth redirect_uri is built from, under the same trust
    rules (NSIGHT_PUBLIC_URL, then forwarded headers only where they are
    trusted). Where TLS is in use this is True, exactly as before.
    """
    return public_origin(request).startswith("https://")


def _issue_session(request: Request, response: Response, repo: Repository,
                   auth: AuthContext, user_id: str) -> None:
    key = get_or_create_signing_key(repo, auth)
    session_id = session.create(repo, auth, user_id)
    response.set_cookie(
        session.COOKIE_NAME, session.cookie_value(key, session_id),
        max_age=session.IDLE_TIMEOUT_SECONDS, httponly=True,
        secure=_cookies_are_secure(request),
        samesite="strict", path="/",
    )


def _user_out(user: User) -> dict:
    """The public shape of a User. `is_owner` is synthesised from
    `user.grants` -- holds `edit` on at least one customer -- never the
    grants themselves: it is the one cheap fact SettingsPage.tsx needs to
    decide whether to show the "Permission requests" tab to someone who is
    not an admin, without fetching every grant to find out (see
    routes_access_requests.py's `list_access_requests` for the matching
    server-side rule)."""
    return {"id": user.id, "email": user.email, "name": user.name,
           "is_admin": user.is_admin,
           "is_owner": any(g.mode == EDIT for g in user.grants)}


@auth_router.post("/register", status_code=201)
def register(request: Request, response: Response, body: dict = Body(...),
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

    normalized = email.lower()
    # This route hashes a password (Argon2) and refuses most callers, so it is
    # both an amplifier and — despite the care taken above to answer refusals
    # identically — a route worth hammering. Counted the same way sign-in is.
    by_user, address = _refuse_if_too_many_attempts(request, normalized)
    if repo.find_user_by_email(auth, normalized) is not None:
        # An email that already resolves to an account -- with a password or
        # without one -- can never be claimed here. A passwordless account is
        # not an edge case: it's what domain auto-join creates today, and
        # what every Google/O365 sign-in will create once Part B lands.
        # Attaching a password to it from this anonymous, unauthenticated
        # endpoint would let anyone who knows a colleague's email address
        # sign in as them and inherit their grants. The only legitimate way
        # for a passwordless account to get a password is a route that
        # proves ownership -- an invitation (Plan 3) or an OIDC sign-in
        # (Part B) -- never a claim made through /auth/register. Do not
        # re-add a branch that sets a password here.
        #
        # The response below is deliberately identical, in status and body,
        # to the "never existed" refusal a few lines down: this route must
        # not become an oracle for "does this person have an account here",
        # the same way /auth/login/password already takes care not to be.
        log.warning("register: refused an attempt to claim the existing account for '%s'",
                   normalized)
        _LOGIN_ATTEMPTS.record_failure(by_user)
        _LOGIN_ATTEMPTS_BY_ADDRESS.record_failure(address)
        raise HTTPException(403, _REGISTER_REFUSED_MESSAGE)

    resolved = identity.resolve_signed_in_user(repo, auth, email, _bootstrap_admins())
    if isinstance(resolved, identity.SignInRefused):
        log.info("register refused: %s", resolved.reason)
        _LOGIN_ATTEMPTS.record_failure(by_user)
        _LOGIN_ATTEMPTS_BY_ADDRESS.record_failure(address)
        raise HTTPException(403, _REGISTER_REFUSED_MESSAGE)

    repo.set_password(auth, resolved.id, password.hash_password(pw))
    _LOGIN_ATTEMPTS.clear(by_user)
    _issue_session(request, response, repo, auth, resolved.id)
    return _user_out(resolved)


@auth_router.post("/login/password")
def login_password(request: Request, response: Response, body: dict = Body(...),
                   auth: AuthContext = Depends(get_auth),
                   repo: Repository = Depends(get_repository)) -> dict:
    email = (body.get("email") or "").strip().lower()
    pw = body.get("password") or ""
    # Before the Argon2 pass, not after: the verification is deliberately
    # expensive, which is exactly what makes an unlimited endpoint an amplifier.
    by_user, address = _refuse_if_too_many_attempts(request, email)
    user = repo.find_user_by_email(auth, email)
    stored_hash = repo.get_password_hash(auth, user.id) if user else None
    # Always verify against SOMETHING, so a wrong password and an unknown
    # email cost the same Argon2 pass -- no timing tell for either.
    ok = password.verify_password(stored_hash or password.DUMMY_HASH, pw)
    if not user or not stored_hash or not ok:
        _LOGIN_ATTEMPTS.record_failure(by_user)
        _LOGIN_ATTEMPTS_BY_ADDRESS.record_failure(address)
        raise HTTPException(401, "Incorrect email or password")
    _LOGIN_ATTEMPTS.clear(by_user)
    _issue_session(request, response, repo, auth, user.id)
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
            # Hand back any report this person had open, BEFORE the session
            # goes: signing out is a deliberate "I am finished", and waiting
            # out the two-minute expiry would bar those reports to everyone
            # else for no reason. Resolving the user needs the session, so the
            # order matters.
            try:
                who = session.resolve(repo, auth, session_id)
                if who is not None:
                    # THIS sign-in's editors, not every one this person has
                    # open. Signing out on a phone used to release the lock
                    # under the report being typed into on a laptop.
                    repo.release_user_locks(auth, who.id, session_id=session_id)
            except Exception:  # noqa: BLE001 — signing out must always succeed
                logging.getLogger(__name__).warning(
                    "could not release editing locks on sign-out", exc_info=True)
            session.revoke(repo, auth, session_id)
    response.delete_cookie(session.COOKIE_NAME, path="/")
    return {"ok": True}


@auth_router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return _user_out(user)


@auth_router.get("/providers")
def auth_providers(auth: AuthContext = Depends(get_auth),
                   repo: Repository = Depends(get_repository)) -> dict:
    """Which SSO providers are configured -- deliberately public: this is how
    the signed-out login page decides which of the two buttons to draw.
    `/settings/oidc` reports the same underlying fact but is admin-only (it
    also matters for /settings/oidc's own audience -- an admin deciding
    whether to configure a provider), so it cannot be the thing a signed-out
    login page calls. This mirrors routes_settings._oidc_status's
    presence-only shape -- never a client id or secret -- just flattened to
    `{provider: bool}` since that is all a login page needs to decide.
    """
    stored = repo.get_setting(auth, OIDC_KEY) or {}
    return {p: bool(stored.get(p, {}).get("client_id") and stored.get(p, {}).get("client_secret"))
            for p in _OIDC_PROVIDERS}


@auth_router.get("/login/{provider}")
async def oidc_login(provider: str, request: Request, response: Response,
                     next: str = "/",
                     auth: AuthContext = Depends(get_auth),
                     repo: Repository = Depends(get_repository)):
    """Start a Google/Microsoft sign-in: redirect to the provider, having
    generated `state`/`nonce` (via `secrets`, inside `oidc.begin`) and
    stashed them in the OAuth-state cookie so the callback can check them.
    """
    if provider not in _OIDC_PROVIDERS:
        raise HTTPException(404, "Unknown provider")
    try:
        url, state, nonce = await oidc.begin(repo, auth, provider, _callback_url(request, provider))
    except oidc.ProviderNotConfigured as exc:
        # A clean 503, not a 500 -- an unconfigured (or, for Microsoft,
        # un-tenant-pinned) provider is an operator problem, not a bug.
        raise HTTPException(503, str(exc)) from exc
    except httpx.HTTPError as exc:
        # The provider's discovery endpoint didn't answer (DNS, connection
        # refused, timeout, ...) -- a clean 502, not an unhandled exception
        # that would otherwise 500 (spec §10: "OIDC provider unreachable").
        raise HTTPException(502, f"{provider} is unreachable right now") from exc

    key = get_or_create_signing_key(repo, auth)
    payload = _oauth_codec(key).dumps(
        {"state": state, "nonce": nonce, "next": _safe_next(next)})
    redirect = Response(status_code=302, headers={"Location": url})
    redirect.set_cookie(_OAUTH_COOKIE, payload, max_age=_OAUTH_MAX_AGE,
                        httponly=True, secure=_cookies_are_secure(request),
                        samesite="lax", path="/auth")
    return redirect


@auth_router.get("/callback/{provider}", name="oidc_callback")
async def oidc_callback(provider: str, request: Request,
                        code: str = "", state: str = "", error: str = "",
                        auth: AuthContext = Depends(get_auth),
                        repo: Repository = Depends(get_repository)):
    """Verify the provider's id_token, resolve its email to a user, and mint
    a session -- or refuse, cleanly, without ever minting one.

    The OAuth-state cookie is single-use: it is cleared here on every exit
    path, success or failure, so a state/nonce pair can never be replayed
    against a second callback.
    """
    if provider not in _OIDC_PROVIDERS:
        raise HTTPException(404, "Unknown provider")

    raw = request.cookies.get(_OAUTH_COOKIE)
    if not raw:
        raise HTTPException(400, "Missing OAuth state")
    key = get_or_create_signing_key(repo, auth)
    try:
        saved = _oauth_codec(key).loads(raw, max_age=_OAUTH_MAX_AGE)
    except itsdangerous.BadData as exc:
        # Unknown, tampered, or expired (max_age) -- all the same refusal.
        raise HTTPException(400, "Invalid or expired OAuth state") from exc
    if not state or saved.get("state") != state:
        raise HTTPException(400, "OAuth state mismatch")

    if error:
        # The provider answered with an error instead of a code -- most
        # commonly `access_denied`, which is what Google/Microsoft send
        # when the user clicks Cancel on the consent screen. Caught here,
        # before ever attempting a token exchange: there is no `code` to
        # exchange in this case anyway, and letting it fall through would
        # otherwise surface as an obscure authlib.OAuthError from
        # oidc.complete. Only the (non-secret) error code is logged.
        log.info("oidc callback for %s reported a provider error: %s", provider, error)
        reason = "sign_in_cancelled" if error == "access_denied" else "sign_in_failed"
        redirect = Response(status_code=302, headers={"Location": f"/login?error={reason}"})
        redirect.delete_cookie(_OAUTH_COOKIE, path="/auth")
        return redirect

    if not code:
        # No error, but no code either -- a malformed callback, refused the
        # same way a missing/mismatched state is: a plain 400, not a 500.
        raise HTTPException(400, "Missing authorization code")

    try:
        verified = await oidc.complete(repo, auth, provider, _callback_url(request, provider),
                                       code, saved["nonce"])
    except oidc.InvalidIdentityToken as exc:
        # Never a token, secret, code, state, or nonce in this log line --
        # just the provider and the (non-secret) reason string oidc.py
        # raised.
        log.warning("oidc callback rejected for %s: %s", provider, exc)
        redirect = Response(status_code=302, headers={"Location": "/login?error=sign_in_failed"})
        redirect.delete_cookie(_OAUTH_COOKIE, path="/auth")
        return redirect
    except oidc.ProviderNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except OAuthError as exc:
        # Backstop: the token exchange itself failed in some way oidc.py
        # doesn't already turn into InvalidIdentityToken (e.g. the provider
        # rejecting the code outright). No token/code/state in this log
        # line either -- only authlib's own (non-secret) error reason.
        log.warning("oidc token exchange failed for %s: %s", provider, exc)
        redirect = Response(status_code=302, headers={"Location": "/login?error=sign_in_failed"})
        redirect.delete_cookie(_OAUTH_COOKIE, path="/auth")
        return redirect

    resolved = identity.resolve_signed_in_user(
        repo, auth, verified.email, _bootstrap_admins(),
        email_domain_proven=verified.email_domain_proven)
    if isinstance(resolved, identity.SignInRefused):
        # SignInRefused is RETURNED, not raised -- no session is minted, and
        # the user lands somewhere that explains it, not a stack trace or a
        # blank page.
        log.info("oidc sign-in refused for %s: %s", provider, resolved.reason)
        redirect = Response(status_code=302, headers={"Location": "/login?error=not_allowed"})
        redirect.delete_cookie(_OAUTH_COOKIE, path="/auth")
        return redirect

    next_path = _safe_next(saved.get("next"))
    redirect = Response(status_code=302, headers={"Location": next_path})
    redirect.delete_cookie(_OAUTH_COOKIE, path="/auth")
    _issue_session(request, redirect, repo, auth, resolved.id)
    return redirect
