"""The OIDC relying-party flow, entirely against a fake provider — no real
network call, ever (Global Constraints).

A local RSA key signs a fake "Google" id_token; an httpx MockTransport
serves the discovery document, the JWKS, and the token endpoint from that
key. This proves nSight's OWN verification (signature, issuer, audience,
expiry, nonce), not Google's server.
"""
import time

import httpx
import pytest
from joserfc import jwk as joserfc_jwk
from joserfc import jwt as joserfc_jwt

from reportbuilder.auth import oidc
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

ISSUER = "https://fake-idp.example/"
CLIENT_ID = "test-client-id"


@pytest.fixture
def repo():
    r = Repository(InMemoryObjectStore())
    return r


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def rsa_key():
    return joserfc_jwk.RSAKey.generate_key(2048, parameters={"kid": "test-1"})


def _id_token(rsa_key, *, nonce="n-1", aud=CLIENT_ID, iss=ISSUER,
             exp_offset=3600, extra=None):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": "user-123",
             "email": "maija@egoiq.com", "email_verified": True,
             "iat": now, "exp": now + exp_offset, "nonce": nonce}
    if extra:
        claims.update(extra)
    header = {"alg": "RS256", "kid": "test-1"}
    return joserfc_jwt.encode(header, claims, rsa_key)


def _transport(rsa_key, *, id_token: str):
    # rsa_key.as_dict() defaults to private=False, i.e. exactly the public
    # JWK a real provider would publish at its jwks_uri.
    jwks = {"keys": [rsa_key.as_dict()]} if rsa_key is not None else {"keys": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={
                "issuer": ISSUER,
                "authorization_endpoint": f"{ISSUER}auth",
                "token_endpoint": f"{ISSUER}token",
                "jwks_uri": f"{ISSUER}jwks",
            })
        if request.url.path == "/jwks":
            return httpx.Response(200, json=jwks)
        if request.url.path == "/token":
            return httpx.Response(200, json={
                "access_token": "at-1", "token_type": "Bearer", "id_token": id_token})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _configured(repo, auth, monkeypatch):
    repo.set_setting(auth, "oidc.json",
                     {"google": {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}})
    monkeypatch.setitem(oidc._METADATA_URL, "google", f"{ISSUER}.well-known/openid-configuration")


class TestBegin:
    async def test_returns_a_url_state_and_nonce(self, repo, auth):
        url, state, nonce = await oidc.begin(repo, auth, "google", "https://app/callback",
                                             transport=_transport(None, id_token=""))
        assert url.startswith(f"{ISSUER}auth")
        assert state and nonce
        assert f"nonce={nonce}" in url or "nonce=" in url

    async def test_an_unconfigured_provider_raises(self, repo, auth):
        with pytest.raises(oidc.ProviderNotConfigured):
            await oidc.begin(repo, auth, "microsoft", "https://app/callback")


class TestComplete:
    async def test_a_correctly_signed_token_yields_the_email(self, repo, auth, rsa_key):
        token = _id_token(rsa_key)
        verified = await oidc.complete(repo, auth, "google", "https://app/callback",
                                       code="c-1", nonce="n-1",
                                       transport=_transport(rsa_key, id_token=token))
        assert verified.email == "maija@egoiq.com"
        assert verified.email_domain_proven is True

    async def test_a_tampered_signature_is_rejected(self, repo, auth, rsa_key):
        token = _id_token(rsa_key)[:-4] + "abcd"
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(repo, auth, "google", "https://app/callback",
                                code="c-1", nonce="n-1",
                                transport=_transport(rsa_key, id_token=token))

    async def test_a_token_signed_with_a_different_key_is_rejected(self, repo, auth, rsa_key):
        # Genuinely well-formed JWS, correctly signed — just not by the key
        # published in the provider's JWKS. Distinct from mere byte-mangling:
        # this is what an attacker with their own valid RSA keypair would
        # try, and the `kid` alone must not be trusted to pick the key.
        impostor_key = joserfc_jwk.RSAKey.generate_key(2048, parameters={"kid": "test-1"})
        token = _id_token(impostor_key)
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(repo, auth, "google", "https://app/callback",
                                code="c-1", nonce="n-1",
                                transport=_transport(rsa_key, id_token=token))

    async def test_the_wrong_audience_is_rejected(self, repo, auth, rsa_key):
        token = _id_token(rsa_key, aud="someone-elses-client-id")
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(repo, auth, "google", "https://app/callback",
                                code="c-1", nonce="n-1",
                                transport=_transport(rsa_key, id_token=token))

    async def test_the_wrong_issuer_is_rejected(self, repo, auth, rsa_key):
        token = _id_token(rsa_key, iss="https://not-the-real-idp.example/")
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(repo, auth, "google", "https://app/callback",
                                code="c-1", nonce="n-1",
                                transport=_transport(rsa_key, id_token=token))

    async def test_an_expired_token_is_rejected(self, repo, auth, rsa_key):
        token = _id_token(rsa_key, exp_offset=-10)
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(repo, auth, "google", "https://app/callback",
                                code="c-1", nonce="n-1",
                                transport=_transport(rsa_key, id_token=token))

    async def test_a_nonce_mismatch_is_rejected(self, repo, auth, rsa_key):
        token = _id_token(rsa_key, nonce="n-1")
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(repo, auth, "google", "https://app/callback",
                                code="c-1", nonce="n-DIFFERENT",
                                transport=_transport(rsa_key, id_token=token))

    async def test_an_unverified_email_is_rejected(self, repo, auth, rsa_key):
        token = _id_token(rsa_key, extra={"email_verified": False})
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(repo, auth, "google", "https://app/callback",
                                code="c-1", nonce="n-1",
                                transport=_transport(rsa_key, id_token=token))

    async def test_an_alg_none_token_is_rejected(self, repo, auth, rsa_key):
        import base64
        import json as jsonlib

        def _b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        now = int(time.time())
        header = {"alg": "none"}
        claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "user-123",
                  "email": "maija@egoiq.com", "email_verified": True,
                  "iat": now, "exp": now + 3600, "nonce": "n-1"}
        forged = ".".join([
            _b64url(jsonlib.dumps(header).encode()),
            _b64url(jsonlib.dumps(claims).encode()),
            "",
        ])
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(repo, auth, "google", "https://app/callback",
                                code="c-1", nonce="n-1",
                                transport=_transport(rsa_key, id_token=forged))

    async def test_a_symmetric_hs256_token_is_rejected(self, repo, auth, rsa_key):
        # Algorithm-confusion: sign with HS256 using the RSA public key's
        # modulus (or any bytes an attacker could plausibly know) as the
        # HMAC secret. Must never be accepted just because "it decodes".
        oct_key = joserfc_jwk.OctKey.import_key(b"whatever-bytes-an-attacker-guesses")
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "user-123",
                 "email": "maija@egoiq.com", "email_verified": True,
                 "iat": now, "exp": now + 3600, "nonce": "n-1"}
        header = {"alg": "HS256"}
        token = joserfc_jwt.encode(header, claims, oct_key)
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(repo, auth, "google", "https://app/callback",
                                code="c-1", nonce="n-1",
                                transport=_transport(rsa_key, id_token=token))


class TestMicrosoftEmailVerification:
    """Microsoft's tenant-pinned v2.0 id_tokens do not carry an
    `email_verified` claim at all -- the equivalent guarantee is structural
    (single-tenant-only, see oidc.py's module docstring), not a per-token
    claim. Google DOES carry the claim and it must be exactly True."""

    @pytest.fixture(autouse=True)
    def _configure_microsoft(self, repo, auth, monkeypatch):
        stored = repo.get_setting(auth, "oidc.json") or {}
        stored["microsoft"] = {"client_id": CLIENT_ID, "client_secret": "s3cr3t",
                               "tenant_id": "test-tenant"}
        repo.set_setting(auth, "oidc.json", stored)
        # A plain URL with no `{tenant_id}` placeholder -- `.format` is a
        # no-op on it, so this still points discovery at the fake IdP.
        monkeypatch.setitem(oidc._METADATA_URL, "microsoft",
                            f"{ISSUER}.well-known/openid-configuration")

    async def test_a_microsoft_token_with_no_email_verified_claim_is_accepted(
            self, repo, auth, rsa_key):
        # simulate a real Microsoft token: no email_verified claim at all
        token = _id_token(rsa_key)
        claims = joserfc_jwt.decode(token, key=rsa_key).claims
        claims.pop("email_verified", None)
        token = joserfc_jwt.encode({"alg": "RS256", "kid": "test-1"}, claims, rsa_key)
        verified = await oidc.complete(repo, auth, "microsoft", "https://app/callback",
                                       code="c-1", nonce="n-1",
                                       transport=_transport(rsa_key, id_token=token))
        assert verified.email == "maija@egoiq.com"
        assert verified.email_domain_proven is False

    async def test_a_microsoft_token_with_email_verified_false_is_still_rejected(
            self, repo, auth, rsa_key):
        token = _id_token(rsa_key, extra={"email_verified": False})
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(repo, auth, "microsoft", "https://app/callback",
                                code="c-1", nonce="n-1",
                                transport=_transport(rsa_key, id_token=token))


class TestMicrosoftTenantConfig:
    """`tenant_id` is OPTIONAL (Task 12c, reversing Task 12's pin): present,
    discovery stays pinned to that one tenant; absent, discovery goes to
    Microsoft's multi-tenant `organizations` endpoint -- never `common`
    (see oidc.py's module docstring for why not, and for how issuer
    validation and `xms_edov` keep multi-tenant safe; see
    TestMicrosoftMultiTenant below for those).
    """

    def test_a_tenant_pinned_config_produces_a_discovery_url_containing_the_tenant_id(
            self, repo, auth):
        stored = repo.get_setting(auth, "oidc.json") or {}
        stored["microsoft"] = {"client_id": CLIENT_ID, "client_secret": "s3cr3t",
                               "tenant_id": "my-tenant-abc"}
        repo.set_setting(auth, "oidc.json", stored)

        config = oidc._config(repo, auth, "microsoft")
        url = oidc._discovery_url("microsoft", config)
        assert "my-tenant-abc" in url
        assert url == ("https://login.microsoftonline.com/my-tenant-abc/v2.0/"
                       ".well-known/openid-configuration")

    def test_a_config_with_no_tenant_id_produces_the_organizations_discovery_url(
            self, repo, auth):
        stored = repo.get_setting(auth, "oidc.json") or {}
        stored["microsoft"] = {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}
        repo.set_setting(auth, "oidc.json", stored)

        config = oidc._config(repo, auth, "microsoft")
        assert config.tenant_id is None
        url = oidc._discovery_url("microsoft", config)
        # Deliberately "organizations", never "common" -- "common" also
        # admits personal Microsoft accounts (outlook.com, Xbox), a
        # different trust model nSight has not signed up for.
        assert url == ("https://login.microsoftonline.com/organizations/v2.0/"
                       ".well-known/openid-configuration")
        assert "common" not in url

    async def test_a_microsoft_config_lacking_a_tenant_id_is_no_longer_refused(
            self, repo, auth, rsa_key):
        # Task 12 refused this outright; Task 12c reverses it -- absence of
        # tenant_id is a deliberate multi-tenant choice now, not a
        # misconfiguration. begin() must reach the (fake) provider rather
        # than raising ProviderNotConfigured.
        stored = repo.get_setting(auth, "oidc.json") or {}
        stored["microsoft"] = {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}
        repo.set_setting(auth, "oidc.json", stored)

        url, state, nonce = await oidc.begin(
            repo, auth, "microsoft", "https://app/callback",
            transport=_transport(rsa_key, id_token=""))
        assert url.startswith(f"{ISSUER}auth")


# Microsoft tenant ids are GUIDs; two distinct, plausible-looking ones for
# the multi-tenant tests below -- one stands in for "the real tenant that
# signed this token", the other for "some other tenant entirely" (used to
# prove a mismatched tid/iss pairing is rejected, not merely a missing one).
_ARBITRARY_TENANT_ID = "11111111-1111-1111-1111-111111111111"
_OTHER_TENANT_ID = "22222222-2222-2222-2222-222222222222"


def _multitenant_transport(rsa_key, *, id_token: str):
    """Like `_transport`, but the discovery document's `issuer` is the
    literal template Microsoft's real `organizations` endpoint publishes
    (confirmed by fetching it directly -- see oidc.py's module docstring),
    not a concrete issuer -- exercising `_expected_issuer`'s substitution,
    not just the tenant-pinned exact-match path every other fixture here
    covers.
    """
    jwks = {"keys": [rsa_key.as_dict()]}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={
                "issuer": f"{ISSUER}{{tenantid}}/v2.0",
                "authorization_endpoint": f"{ISSUER}auth",
                "token_endpoint": f"{ISSUER}token",
                "jwks_uri": f"{ISSUER}jwks",
            })
        if request.url.path == "/jwks":
            return httpx.Response(200, json=jwks)
        if request.url.path == "/token":
            return httpx.Response(200, json={
                "access_token": "at-1", "token_type": "Bearer", "id_token": id_token})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


class TestMicrosoftMultiTenant:
    """`organizations` discovery: a genuine token from ANY tenant is
    accepted (issuer validated via the token's own `tid`, not an exact
    pinned string), and `xms_edov` is the only thing that proves the
    email's DOMAIN, not merely the token, is trustworthy -- see oidc.py's
    module docstring and identity.py's `email_domain_proven` parameter.
    """

    @pytest.fixture(autouse=True)
    def _configure_microsoft_multitenant(self, repo, auth, monkeypatch):
        stored = repo.get_setting(auth, "oidc.json") or {}
        stored["microsoft"] = {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}
        repo.set_setting(auth, "oidc.json", stored)
        monkeypatch.setattr(oidc, "_MICROSOFT_MULTITENANT_METADATA_URL",
                            f"{ISSUER}.well-known/openid-configuration")

    def _token(self, rsa_key, *, tid=_ARBITRARY_TENANT_ID, iss=None, extra=None):
        claims = {"tid": tid}
        if extra:
            claims.update(extra)
        iss = iss if iss is not None else f"{ISSUER}{tid}/v2.0"
        return _id_token(rsa_key, iss=iss, extra=claims)

    async def test_a_genuine_token_from_an_arbitrary_tenant_with_xms_edov_true_is_accepted(
            self, repo, auth, rsa_key):
        token = self._token(rsa_key, extra={"xms_edov": True})
        verified = await oidc.complete(
            repo, auth, "microsoft", "https://app/callback", code="c-1", nonce="n-1",
            transport=_multitenant_transport(rsa_key, id_token=token))
        assert verified.email == "maija@egoiq.com"
        assert verified.email_domain_proven is True

    async def test_xms_edov_absent_is_accepted_but_unproven(self, repo, auth, rsa_key):
        token = self._token(rsa_key)  # no xms_edov claim at all
        verified = await oidc.complete(
            repo, auth, "microsoft", "https://app/callback", code="c-1", nonce="n-1",
            transport=_multitenant_transport(rsa_key, id_token=token))
        assert verified.email == "maija@egoiq.com"
        assert verified.email_domain_proven is False

    async def test_xms_edov_false_behaves_the_same_as_absent(self, repo, auth, rsa_key):
        token = self._token(rsa_key, extra={"xms_edov": False})
        verified = await oidc.complete(
            repo, auth, "microsoft", "https://app/callback", code="c-1", nonce="n-1",
            transport=_multitenant_transport(rsa_key, id_token=token))
        assert verified.email == "maija@egoiq.com"
        assert verified.email_domain_proven is False

    async def test_a_forged_issuer_is_still_refused(self, repo, auth, rsa_key):
        # `tid` says one tenant; `iss` claims to be signed for a DIFFERENT
        # one. Genuinely signed by the right key (Microsoft's shared
        # multi-tenant JWKS), but the iss/tid pairing is exactly what an
        # attacker would need to forge and can't: `iss` must equal the
        # template with THIS token's own `tid` substituted in, not any
        # tenant-shaped string.
        token = self._token(rsa_key, tid=_ARBITRARY_TENANT_ID,
                            iss=f"{ISSUER}{_OTHER_TENANT_ID}/v2.0")
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(
                repo, auth, "microsoft", "https://app/callback", code="c-1", nonce="n-1",
                transport=_multitenant_transport(rsa_key, id_token=token))

    async def test_an_issuer_from_a_wholly_different_authority_is_refused(
            self, repo, auth, rsa_key):
        token = self._token(rsa_key, iss="https://not-microsoft.example/evil/v2.0")
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(
                repo, auth, "microsoft", "https://app/callback", code="c-1", nonce="n-1",
                transport=_multitenant_transport(rsa_key, id_token=token))

    async def test_a_missing_tid_claim_is_refused(self, repo, auth, rsa_key):
        token = _id_token(rsa_key, iss=f"{ISSUER}{_ARBITRARY_TENANT_ID}/v2.0")  # no tid claim
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(
                repo, auth, "microsoft", "https://app/callback", code="c-1", nonce="n-1",
                transport=_multitenant_transport(rsa_key, id_token=token))

    async def test_a_malformed_tid_claim_is_refused(self, repo, auth, rsa_key):
        # Not GUID-shaped -- rejected before it is ever substituted into an
        # issuer comparison (_TENANT_ID_PATTERN, defense in depth).
        bad_tid = "'; DROP TABLE users; --"
        token = self._token(rsa_key, tid=bad_tid, iss=f"{ISSUER}{bad_tid}/v2.0")
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(
                repo, auth, "microsoft", "https://app/callback", code="c-1", nonce="n-1",
                transport=_multitenant_transport(rsa_key, id_token=token))
