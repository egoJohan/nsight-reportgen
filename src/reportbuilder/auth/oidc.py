"""Google and Microsoft as OIDC identity providers (spec §4, D1, D2).

nSight is the relying party: it redirects to the provider, exchanges the
authorization code for an id_token, and verifies that token ITSELF —
signature, issuer, audience, expiry, nonce — against the provider's own
published keys, then takes the VERIFIED email. Nothing here ever trusts an
email the browser hands us directly; the only email that counts is the one
inside a token that survives every check below.

Why Authlib but not its Starlette integration: `OAuth.authorize_redirect` /
`authorize_access_token` store state and nonce in `request.session`, which
needs Starlette's `SessionMiddleware` and its own secret wired in at
app-construction time — before any per-request `Depends(get_repository)`
exists, and before a test fixture gets a chance to inject an in-memory
store. Calling the lower-level `AsyncOAuth2Client` methods directly
(`create_authorization_url`, `fetch_token`) sidesteps that: state and nonce
travel in nSight's own short-lived signed cookie instead (Task 12), read
the same way everything else in this module reads its secret — through
`get_or_create_signing_key(repo, auth)`, inside a normal request.

Why joserfc and not authlib.jose: `authlib.jose` is deprecated as of
Authlib 2.0 in favour of joserfc (confirmed by reading the installed
authlib 1.7.2 package: `authlib/jose/__init__.py` emits that deprecation,
and Authlib's own `async_openid.py` already imports joserfc internally).

Microsoft is pinned to a SINGLE tenant, not discovered against `organizations`
or `common` (Task 12 addition, over Task 11's original design — read this
before "helpfully" widening it back):

`organizations` accepts a work/school account from ANY Entra tenant on
earth, including one an attacker spins up for free. Microsoft's
`/organizations` v2.0 id_tokens never carry `email_verified` (see
`_EMAIL_VERIFIED_REQUIRED` below) — so with multi-tenant discovery, nothing
stops an attacker from creating their own throwaway tenant, setting a
user's `mail` attribute in THAT tenant's directory to an address at the
victim's real domain, signing in, and handing nSight a token whose `email`
claim is genuine (correctly signed, right audience, right issuer for
`/organizations`) but utterly unverified as to WHO controls that address.
Since users are resolved by email (`identity.resolve_signed_in_user`),
that token would be handed the victim's account.

Pinning discovery to `https://login.microsoftonline.com/<tenant_id>/v2.0/...`
closes this: the issuer check in `complete()` already pins `iss` to
whatever THIS discovery document claims (Task 11), and a tenant-scoped
discovery document's issuer only accepts tokens minted by that one tenant's
STS. An attacker's own tenant can never produce a token that verifies
against a discovery document scoped to nSight's customer's tenant — full
stop, no reliance on Microsoft to have verified the email itself.

Widening this later without reopening the hole above requires ONE of:
  - an explicit `tid` (tenant id) claim allow-list checked in `complete()`,
    kept in sync with which tenants are actually trusted, or
  - Microsoft's `xms_edov` claim ("email domain owner verified"), which (per
    Microsoft's docs) is only asserted when `email_verified`-equivalent
    proof exists for that specific email/tenant pairing.
Neither exists in this codebase today. Do not switch back to
`/organizations` or `/common` discovery without adding one of them first.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from authlib.integrations.httpx_client import AsyncOAuth2Client
from joserfc import jwt as joserfc_jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

_METADATA_URL = {
    "google": "https://accounts.google.com/.well-known/openid-configuration",
    # {tenant_id} is substituted per-config in `_discovery_url` — there is
    # no un-pinned fallback ("organizations" or "common"); see the module
    # docstring for why. `.format(tenant_id=...)` is a no-op on a URL with
    # no placeholder (e.g. google's, above), which is what keeps existing
    # tests that monkeypatch this entry with a plain URL working unchanged.
    "microsoft": "https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration",
}

_SETTINGS_KEY = "oidc.json"
_SCOPE = "openid email"

# Only asymmetric signing algorithms are ever acceptable for an id_token we
# verify against a provider's published JWKS. "none" is never in this list,
# and neither is any HMAC alg ("HS*") — accepting one would let an attacker
# sign their own token with a secret they can plausibly guess or already
# know (our own client_secret, for instance), turning verification into a
# rubber stamp. See test_an_alg_none_token_is_rejected and
# test_a_symmetric_hs256_token_is_rejected.
_ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]

# Small allowance for clock skew between us and the provider, per spec §4
# step 2 ("only a small clock-skew allowance"). Applied to exp/iat/nbf.
# Deliberately much smaller than AsyncOAuth2Client's own default `leeway`
# of 60s (that one governs ITS OWN access-token-refresh bookkeeping, not
# id_token verification, and is unrelated to this constant): a token that
# expired 10 seconds ago is still an expired token, not clock skew.
_CLOCK_SKEW_LEEWAY_SECONDS = 5

# Per-provider proof that the email claim can be trusted, beyond the
# universal set (iss/aud/exp/iat) that JWTClaimsRegistry already checks:
#
# - Google puts `email_verified` in every id_token, and a token CAN carry an
#   unverified email (e.g. a Gmail alias someone typed but never confirmed)
#   -- spec §4 step 2 requires this to be exactly True for Google.
# - Microsoft's tenant-pinned v2.0 endpoint (see module docstring) does not
#   send an `email_verified` claim on ordinary id_tokens at all -- the
#   equivalent guarantee there is structural, not a claim: only accounts in
#   the ONE tenant `_config` pins discovery to can produce a token that
#   verifies at all (no other tenant's STS shares that issuer), and that
#   tenant's email addresses are provisioned and controlled by its own
#   directory admin, not self-asserted by the end user. So Microsoft is not
#   in this set: requiring a claim it does not send would refuse every real
#   Microsoft sign-in, and there is no equivalent per-token claim to check.
#   If Microsoft ever DOES send `email_verified: false` explicitly, that is
#   still honoured -- see the unconditional check below.
_EMAIL_VERIFIED_REQUIRED = {"google"}


class ProviderNotConfigured(Exception):
    def __init__(self, provider: str, detail: str | None = None):
        message = f"{provider} sign-in is not configured"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)
        self.provider = provider


class InvalidIdentityToken(Exception):
    """Signature, issuer, audience, expiry, nonce, or email_verified failed.

    Deliberately a single exception type for every failure mode: the caller
    (routes_auth.py) never needs to distinguish WHY a token was refused —
    spec §10 says the reason is for the log, not the browser — and a single
    type keeps a caller from accidentally treating one failure mode as safe
    to ignore while catching another.
    """


@dataclass(frozen=True)
class _Config:
    client_id: str
    client_secret: str
    # Only ever set for "microsoft" -- see module docstring. None for
    # google, which has no tenant concept.
    tenant_id: str | None = None


def _config(repo: Repository, auth: AuthContext, provider: str) -> _Config:
    stored = repo.get_setting(auth, _SETTINGS_KEY) or {}
    entry = stored.get(provider) or {}
    if not entry.get("client_id") or not entry.get("client_secret"):
        raise ProviderNotConfigured(provider)
    tenant_id = (entry.get("tenant_id") or "").strip() or None
    if provider == "microsoft" and not tenant_id:
        # Fail CLOSED, deliberately: falling back to a multi-tenant
        # discovery endpoint here is exactly the hole the module docstring
        # describes. A missing tenant_id is a misconfiguration to fix in
        # settings, not a default to paper over.
        raise ProviderNotConfigured(
            provider, "missing tenant_id (multi-tenant discovery is refused, not defaulted -- see oidc.py's module docstring)")
    return _Config(client_id=entry["client_id"], client_secret=entry["client_secret"],
                  tenant_id=tenant_id)


def _client(config: _Config, redirect_uri: str, transport) -> AsyncOAuth2Client:
    kwargs = {"transport": transport} if transport is not None else {}
    return AsyncOAuth2Client(config.client_id, config.client_secret,
                            scope=_SCOPE, redirect_uri=redirect_uri, **kwargs)


def _discovery_url(provider: str, config: _Config) -> str:
    """`_METADATA_URL[provider]` with `{tenant_id}` substituted in, if it has
    one. A no-op on google's URL (no placeholder present) and on any test
    fixture that monkeypatches the entry with a plain URL -- see
    `_METADATA_URL`'s comment.
    """
    return _METADATA_URL[provider].format(tenant_id=config.tenant_id)


async def _discover(client: AsyncOAuth2Client, provider: str, config: _Config) -> dict:
    # auth=None (not the "use client default" sentinel `.get()` normally
    # applies): AsyncOAuth2Client otherwise insists on attaching an OAuth
    # bearer token to every request, and raises MissingTokenError before we
    # have ever fetched one -- discovery is a plain, unauthenticated GET.
    resp = await client.get(_discovery_url(provider, config), auth=None)
    resp.raise_for_status()
    return resp.json()


async def begin(repo: Repository, auth: AuthContext, provider: str,
                redirect_uri: str, *, transport=None) -> tuple[str, str, str]:
    """Start a sign-in: (authorization_url, state, nonce).

    The caller is responsible for storing state and nonce somewhere it can
    check them again on the callback (a short-lived signed cookie — see
    routes_auth.py) — both are single-use, provider-request-scoped secrets,
    not something this module can persist itself since it is not tied to a
    particular request/response cycle.
    """
    config = _config(repo, auth, provider)
    async with _client(config, redirect_uri, transport) as client:
        metadata = await _discover(client, provider, config)
        nonce = secrets.token_urlsafe(20)
        state = secrets.token_urlsafe(20)
        url, state = client.create_authorization_url(
            metadata["authorization_endpoint"], state=state, nonce=nonce)
    return url, state, nonce


async def complete(repo: Repository, auth: AuthContext, provider: str,
                   redirect_uri: str, code: str, nonce: str,
                   *, transport=None) -> str:
    """Exchange *code* for a token, verify the id_token against the
    provider's own published keys, and return the VERIFIED email.

    Every check from spec §4 step 2 happens here, in this order:

    1. signature — against a key fetched from the provider's OWN discovery
       document's jwks_uri, never a key merely named in the token's `kid`
       header (KeySet.import_key_set carries several keys; joserfc picks
       among THOSE by kid, so an attacker cannot point us at their own key).
    2. alg — restricted to `_ALLOWED_ALGORITHMS`, so `none` and symmetric
       (`HS*`) algorithms are never accepted, closing the classic
       algorithm-confusion attack.
    3. iss / aud / exp / iat — via JWTClaimsRegistry, aud pinned to OUR
       client_id and iss pinned to the issuer THIS discovery document
       claims (not merely "whatever the token says").
    4. nonce — matched against the one the caller generated for this
       authorization request, so a captured token cannot be replayed later.
    5. provider-specific proof the email is verified (Google: the token's
       own `email_verified` claim; see `_EMAIL_VERIFIED_REQUIRED`).

    Raises InvalidIdentityToken for anything that fails any of the above.
    Raises ProviderNotConfigured if *provider* has no stored credentials.
    """
    config = _config(repo, auth, provider)
    async with _client(config, redirect_uri, transport) as client:
        metadata = await _discover(client, provider, config)

        token = await client.fetch_token(url=metadata["token_endpoint"],
                                         code=code, redirect_uri=redirect_uri)
        id_token = token.get("id_token")
        if not id_token:
            raise InvalidIdentityToken("provider returned no id_token")

        jwks_resp = await client.get(metadata["jwks_uri"], auth=None)
        jwks_resp.raise_for_status()
        key_set = KeySet.import_key_set(jwks_resp.json())

        try:
            decoded = joserfc_jwt.decode(id_token, key=key_set, algorithms=_ALLOWED_ALGORITHMS)
        except JoseError as exc:
            raise InvalidIdentityToken(f"signature verification failed: {exc}") from exc

        registry = JWTClaimsRegistry(
            leeway=_CLOCK_SKEW_LEEWAY_SECONDS,
            iss={"essential": True, "value": metadata["issuer"]},
            aud={"essential": True, "value": config.client_id},
            exp={"essential": True},
            iat={"essential": True},
        )
        try:
            registry.validate(decoded.claims)
        except JoseError as exc:
            raise InvalidIdentityToken(f"claim validation failed: {exc}") from exc

        if not nonce or decoded.claims.get("nonce") != nonce:
            raise InvalidIdentityToken("nonce mismatch")

        email_verified = decoded.claims.get("email_verified")
        if provider in _EMAIL_VERIFIED_REQUIRED and email_verified is not True:
            raise InvalidIdentityToken("email not verified by the provider")
        # Defense in depth for every provider, Microsoft included: an
        # explicit False is never ignored just because that provider is not
        # in _EMAIL_VERIFIED_REQUIRED -- absence of the claim is what the
        # tenant-restriction argument above covers, not an explicit denial.
        if email_verified is False:
            raise InvalidIdentityToken("email not verified by the provider")

        email = decoded.claims.get("email")
        if not email:
            raise InvalidIdentityToken("id_token carried no email claim")
        return email
