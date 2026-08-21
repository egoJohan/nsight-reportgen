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

Microsoft: `tenant_id` is OPTIONAL (Task 12c, reversing Task 12's pin — read
this before re-narrowing it, and read the rest of this docstring first if
you were about to "fix" that by requiring it again).

When `tenant_id` IS set, discovery stays pinned to
`https://login.microsoftonline.com/<tenant_id>/v2.0/...`, exactly as Task 12
left it — useful for a deployment that wants to restrict sign-in to one
customer's own tenant.

When `tenant_id` is ABSENT, discovery goes to Microsoft's multi-tenant
`organizations` endpoint — deliberately `organizations`, never `common`:
`common` also admits *personal* Microsoft accounts (outlook.com, Xbox, no
employer, no directory), which is a different trust model nSight has never
signed up for. `organizations` accepts a work/school account from ANY Entra
tenant on earth, including one an attacker spins up for free — that is the
whole point (an nSight customer's contractors, partners, or a wholly
different company's employees can all sign in without nSight configuring
each one specially), but it reopens two things Task 12 closed by pinning to
a single tenant, both handled below instead:

1. **Issuer validation.** A tenant-pinned discovery document has a concrete
   `issuer`. Fetching Microsoft's real `organizations` discovery document
   (confirmed by hand: `curl
   https://login.microsoftonline.com/organizations/v2.0/.well-known/openid-configuration`)
   shows its `issuer` is the literal template string
   `https://login.microsoftonline.com/{tenantid}/v2.0` — Microsoft does not
   and cannot name a concrete issuer here, because ANY tenant's STS can mint
   a token against this document. An exact-string comparison against that
   template would reject every real token (none of them literally say
   `{tenantid}`), and skipping the check is not an option (Task 11's iss
   check exists precisely to bind a token to the endpoint that vouched for
   it). `_expected_issuer()` closes this the standard way: when the
   template contains `{tenantid}`, the tenant this SPECIFIC token claims to
   be from is its own `tid` claim, so the issuer this token must carry is
   the template with `{tenantid}` substituted for THAT token's `tid` —
   still an exact-string comparison via `JWTClaimsRegistry`, just against a
   value computed per-token instead of pinned once at config time. A token
   cannot pass by asserting a `tid` that produces some other `iss`; it can
   only pass by genuinely being signed (Microsoft's key, checked first) for
   the tenant it says it is from. `tid` is additionally required to look
   like a GUID (`_TENANT_ID_PATTERN`) before it is ever substituted in —
   defense in depth, since a well-formed `tid` is what every real Entra
   token carries and a malformed one is not a shape a legitimate issuer
   string can hide inside anyway.

2. **The email-spoofing hole Task 12 pinning was originally added to close.**
   Microsoft's `/organizations` v2.0 id_tokens never carry `email_verified`
   (see `_EMAIL_VERIFIED_REQUIRED` below — Microsoft still is not in it).
   So: an attacker creates their own free Entra tenant, sets a user's `mail`
   attribute in THAT tenant's directory to an address at a victim's real
   domain, signs in, and hands nSight a token whose `email` claim is genuine
   (correctly signed, right audience, right issuer for ITS OWN tenant per
   check 1 above) but utterly unverified as to WHO controls that address.
   Since users are resolved by email (`identity.resolve_signed_in_user`), a
   naive multi-tenant rollout would hand that token the victim's account —
   or, worse, auto-provision a brand-new account at the victim's domain if
   it happens to be on nSight's allowed-domains list.

   The defence is Microsoft's `xms_edov` optional claim ("email domain
   owner verified"): asserted `true` only when the issuing tenant has
   actually verified ownership of the email's domain (per Microsoft's own
   docs). `complete()` surfaces this as `VerifiedIdentity.email_domain_proven`
   — `xms_edov is True` exactly, so an absent claim (the common case: it
   requires an `optionalClaims` entry on the app registration that most
   tenants have never configured — see routes_settings.py / the task report
   for exactly what to add) or an explicit `false` are BOTH treated as
   unproven, fail-closed, never as proven. `email_domain_proven=False` does
   NOT refuse the sign-in outright — Microsoft is still not in
   `_EMAIL_VERIFIED_REQUIRED`, and refusing every ordinary Microsoft sign-in
   because most tenants have not opted into `xms_edov` would defeat the
   point of multi-tenant. Instead it is threaded through to
   `identity.resolve_signed_in_user`, which is the ONLY place with enough
   context to enforce the actual rule: an unproven email may resolve to an
   ALREADY-EXISTING account, never mint a new one via domain auto-join (or
   any other account-creation path) — see identity.py. That makes the
   spoofing path above useless: a forged email can never mint a new
   account, and cannot take over an existing one unless the attacker
   already knows a specific nSight account exists at that address AND its
   real owner's tenant is not asserting ownership either.
"""
from __future__ import annotations

import re
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
    # Used when a Microsoft config PINS a tenant. {tenant_id} is substituted
    # per-config in `_discovery_url`. `.format(tenant_id=...)` is a no-op on
    # a URL with no placeholder (e.g. google's, above), which is what keeps
    # existing tests that monkeypatch this entry with a plain URL working
    # unchanged.
    "microsoft": "https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration",
}

# Used for Microsoft when NO tenant_id is configured — see the module
# docstring for why this is `organizations` and never `common`.
_MICROSOFT_MULTITENANT_METADATA_URL = (
    "https://login.microsoftonline.com/organizations/v2.0/.well-known/openid-configuration"
)

# Entra tenant ids are GUIDs. Required of a token's `tid` claim before it is
# ever substituted into an issuer template — see `_expected_issuer`.
_TENANT_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

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
# - Microsoft's v2.0 endpoint (tenant-pinned OR multi-tenant) does not send
#   an `email_verified` claim on ordinary id_tokens at all, so requiring one
#   would refuse every real Microsoft sign-in. The nearest equivalent is the
#   OPTIONAL `xms_edov` claim, surfaced separately as
#   `VerifiedIdentity.email_domain_proven` (see `_email_domain_proven` and
#   the module docstring) rather than folded in here: unlike Google's
#   requirement, an unproven Microsoft email does not refuse the sign-in
#   outright, it only refuses to MINT A NEW ACCOUNT for it --
#   `identity.resolve_signed_in_user` is where that distinction is enforced.
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
class VerifiedIdentity:
    """What `complete()` proves about the id_token, and no more.

    `email` is genuinely the provider's own claim: signature, issuer,
    audience, expiry, and nonce all checked before this is ever
    constructed. `email_domain_proven` is a SEPARATE, weaker-by-default
    promise -- that whoever issued the token has actually verified they own
    that email's domain, not merely that the token itself is authentic. See
    `_email_domain_proven` and the module docstring for exactly what backs
    it per provider, and `identity.resolve_signed_in_user`'s
    `email_domain_proven` parameter for what an unproven email is (and is
    not) allowed to do.
    """
    email: str
    email_domain_proven: bool


@dataclass(frozen=True)
class _Config:
    client_id: str
    client_secret: str
    # Only ever set for "microsoft" -- see module docstring. None for
    # google, which has no tenant concept, and for a Microsoft config that
    # deliberately wants multi-tenant discovery.
    tenant_id: str | None = None


def _config(repo: Repository, auth: AuthContext, provider: str) -> _Config:
    stored = repo.get_setting(auth, _SETTINGS_KEY) or {}
    entry = stored.get(provider) or {}
    if not entry.get("client_id") or not entry.get("client_secret"):
        raise ProviderNotConfigured(provider)
    tenant_id = (entry.get("tenant_id") or "").strip() or None
    # tenant_id is OPTIONAL for microsoft (Task 12c) -- an absent one is a
    # deliberate choice (multi-tenant `organizations` discovery, see the
    # module docstring), never a misconfiguration to refuse.
    return _Config(client_id=entry["client_id"], client_secret=entry["client_secret"],
                  tenant_id=tenant_id)


def _client(config: _Config, redirect_uri: str, transport) -> AsyncOAuth2Client:
    kwargs = {"transport": transport} if transport is not None else {}
    return AsyncOAuth2Client(config.client_id, config.client_secret,
                            scope=_SCOPE, redirect_uri=redirect_uri, **kwargs)


def _discovery_url(provider: str, config: _Config) -> str:
    """microsoft with no `tenant_id` goes to `_MICROSOFT_MULTITENANT_METADATA_URL`
    (see module docstring). Otherwise, `_METADATA_URL[provider]` with
    `{tenant_id}` substituted in, if it has one -- a no-op on google's URL
    (no placeholder present) and on any test fixture that monkeypatches the
    entry with a plain URL -- see `_METADATA_URL`'s comment.
    """
    if provider == "microsoft" and not config.tenant_id:
        return _MICROSOFT_MULTITENANT_METADATA_URL
    return _METADATA_URL[provider].format(tenant_id=config.tenant_id)


def _expected_issuer(metadata: dict, claims: dict) -> str:
    """The exact `iss` this specific token must carry.

    For a tenant-pinned config (or google), `metadata["issuer"]` is already
    a concrete string and is used as-is -- unchanged from Task 11/12.

    For multi-tenant Microsoft discovery, `metadata["issuer"]` is the
    template `https://login.microsoftonline.com/{tenantid}/v2.0` (confirmed
    against Microsoft's real `organizations` discovery document -- see the
    module docstring). The concrete issuer for THIS token is that template
    with `{tenantid}` substituted for the token's OWN `tid` claim: a forged
    token cannot pick a `tid` that produces a false match, because the
    resulting `iss` must still equal what Microsoft itself signed into the
    token, and Microsoft only signs a token with `iss` matching the `tid` of
    the tenant that actually issued it.

    Raises InvalidIdentityToken if the template requires a `tid` and the
    token doesn't carry one that looks like a genuine Entra tenant id.
    """
    template = metadata["issuer"]
    if "{tenantid}" not in template:
        return template
    tid = claims.get("tid")
    if not isinstance(tid, str) or not _TENANT_ID_PATTERN.match(tid):
        raise InvalidIdentityToken("id_token missing a valid tenant id (tid) claim")
    return template.replace("{tenantid}", tid)


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


def _email_domain_proven(provider: str, claims: dict) -> bool:
    """See `VerifiedIdentity.email_domain_proven`.

    Google: always True here -- `complete()` already required
    `email_verified is True` above, or raised before ever reaching this
    call.

    Microsoft: `xms_edov is True`, exactly. Fail CLOSED on everything else
    -- an absent claim (the common case: it requires an `optionalClaims`
    entry on the app registration; see the module docstring for exactly
    what to configure) or an explicit `false` are BOTH unproven. Never
    inferred from `True`-ish values or any other claim.
    """
    if provider in _EMAIL_VERIFIED_REQUIRED:
        return True
    if provider == "microsoft":
        return claims.get("xms_edov") is True
    return False


async def complete(repo: Repository, auth: AuthContext, provider: str,
                   redirect_uri: str, code: str, nonce: str,
                   *, transport=None) -> VerifiedIdentity:
    """Exchange *code* for a token, verify the id_token against the
    provider's own published keys, and return a VerifiedIdentity.

    Every check from spec §4 step 2 happens here, in this order:

    1. signature — against a key fetched from the provider's OWN discovery
       document's jwks_uri, never a key merely named in the token's `kid`
       header (KeySet.import_key_set carries several keys; joserfc picks
       among THOSE by kid, so an attacker cannot point us at their own key).
    2. alg — restricted to `_ALLOWED_ALGORITHMS`, so `none` and symmetric
       (`HS*`) algorithms are never accepted, closing the classic
       algorithm-confusion attack.
    3. iss / aud / exp / iat — via JWTClaimsRegistry, aud pinned to OUR
       client_id and iss pinned to what `_expected_issuer` computes for
       THIS token (not merely "whatever the token says") — see that
       function and the module docstring for the multi-tenant Microsoft
       case, where the discovery document names a template, not a value.
    4. nonce — matched against the one the caller generated for this
       authorization request, so a captured token cannot be replayed later.
    5. `email_verified` (Google only — see `_EMAIL_VERIFIED_REQUIRED`) must
       be exactly True, or the sign-in is refused outright.

    `VerifiedIdentity.email_domain_proven` (`_email_domain_proven`) is a
    SEPARATE, weaker signal that does not by itself refuse anything here —
    see the module docstring and `identity.resolve_signed_in_user`.

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

        expected_issuer = _expected_issuer(metadata, decoded.claims)

        registry = JWTClaimsRegistry(
            leeway=_CLOCK_SKEW_LEEWAY_SECONDS,
            iss={"essential": True, "value": expected_issuer},
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
        return VerifiedIdentity(email=email,
                                email_domain_proven=_email_domain_proven(provider, decoded.claims))
