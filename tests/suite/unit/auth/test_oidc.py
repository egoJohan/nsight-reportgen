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
        email = await oidc.complete(repo, auth, "google", "https://app/callback",
                                    code="c-1", nonce="n-1",
                                    transport=_transport(rsa_key, id_token=token))
        assert email == "maija@egoiq.com"

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
    """Microsoft's `/organizations` v2.0 id_tokens do not carry an
    `email_verified` claim at all -- the equivalent guarantee is structural
    (org-tenant-only, see oidc.py's module docstring), not a per-token
    claim. Google DOES carry the claim and it must be exactly True."""

    @pytest.fixture(autouse=True)
    def _configure_microsoft(self, repo, auth, monkeypatch):
        stored = repo.get_setting(auth, "oidc.json") or {}
        stored["microsoft"] = {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}
        repo.set_setting(auth, "oidc.json", stored)
        monkeypatch.setitem(oidc._METADATA_URL, "microsoft",
                            f"{ISSUER}.well-known/openid-configuration")

    async def test_a_microsoft_token_with_no_email_verified_claim_is_accepted(
            self, repo, auth, rsa_key):
        # simulate a real Microsoft token: no email_verified claim at all
        token = _id_token(rsa_key)
        claims = joserfc_jwt.decode(token, key=rsa_key).claims
        claims.pop("email_verified", None)
        token = joserfc_jwt.encode({"alg": "RS256", "kid": "test-1"}, claims, rsa_key)
        email = await oidc.complete(repo, auth, "microsoft", "https://app/callback",
                                    code="c-1", nonce="n-1",
                                    transport=_transport(rsa_key, id_token=token))
        assert email == "maija@egoiq.com"

    async def test_a_microsoft_token_with_email_verified_false_is_still_rejected(
            self, repo, auth, rsa_key):
        token = _id_token(rsa_key, extra={"email_verified": False})
        with pytest.raises(oidc.InvalidIdentityToken):
            await oidc.complete(repo, auth, "microsoft", "https://app/callback",
                                code="c-1", nonce="n-1",
                                transport=_transport(rsa_key, id_token=token))
