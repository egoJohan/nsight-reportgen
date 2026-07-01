"""Unit tests for ``nsight.agent.egohive_client`` with ``urllib.request.urlopen``
monkeypatched — NO real network. Covers the two-call chat flow, header wiring,
error translation, ``load_creds`` precedence, and the pure ``_clean`` /
``_build_prompt`` helpers."""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from nsight.agent import egohive_client as C
from nsight.agent.egohive_client import EgoHiveError


# --------------------------------------------------------------------------- #
# Fake urlopen plumbing
# --------------------------------------------------------------------------- #
class _FakeResp:
    """Context-manager response whose .read() yields canned JSON bytes."""

    def __init__(self, payload):
        self._raw = payload if isinstance(payload, (bytes, bytearray)) \
            else json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _install_urlopen(monkeypatch, responses, requests=None):
    """Patch urlopen to return ``responses`` in order and record Request objects."""
    it = iter(responses)

    def fake(req, timeout=None):
        if requests is not None:
            requests.append(req)
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return _FakeResp(item)

    monkeypatch.setattr(C.urllib.request, "urlopen", fake)


def _header_value(req, name):
    """Case-insensitive header lookup on a urllib Request."""
    low = name.lower()
    for k, v in req.header_items():
        if k.lower() == low:
            return v
    return None


@pytest.fixture
def env_creds(monkeypatch):
    """Configure egoHive purely from env vars (no creds file, no endpoint key)."""
    monkeypatch.setenv("EGOHIVE_BASE_URL", "http://egohive.test/api/v1")
    monkeypatch.setenv("EGOHIVE_ENDPOINT_ID", "ep-123")
    monkeypatch.delenv("EGOHIVE_ENDPOINT_KEY", raising=False)


# --------------------------------------------------------------------------- #
# egohive_chat — happy path (two POSTs)
# --------------------------------------------------------------------------- #
def test_egohive_chat_two_call_flow_and_urls(env_creds, monkeypatch):
    reqs = []
    _install_urlopen(monkeypatch,
                     [{"session_id": "sess-9"}, {"content": "Vastaus"}],
                     requests=reqs)
    out = C.egohive_chat("Kysymys?")
    assert out == "Vastaus"
    assert len(reqs) == 2
    assert reqs[0].full_url == "http://egohive.test/api/v1/session/ep-123"
    assert reqs[0].method == "POST"
    assert reqs[1].full_url == "http://egohive.test/api/v1/chat/sess-9"
    # The chat POST body carries the prompt as {"content": ...}.
    assert json.loads(reqs[1].data.decode()) == {"content": "Kysymys?"}


def test_egohive_chat_strips_markdown_and_quotes_preserves_newlines(env_creds, monkeypatch):
    _install_urlopen(monkeypatch,
                     [{"session_id": "s"}, {"content": '"**Rivi 1**\nRivi 2"'}])
    out = C.egohive_chat("p")
    # ** stripped, wrapping quotes stripped, internal newline preserved.
    assert out == "Rivi 1\nRivi 2"


def test_egohive_chat_empty_prompt_raises():
    with pytest.raises(EgoHiveError):
        C.egohive_chat("   ")


# --------------------------------------------------------------------------- #
# _create_session — X-Endpoint-Key header wiring + Origin
# --------------------------------------------------------------------------- #
def test_create_session_includes_endpoint_key_header(monkeypatch):
    reqs = []
    _install_urlopen(monkeypatch, [{"session_id": "abc"}], requests=reqs)
    sid = C._create_session("http://h/api", "ep1", endpoint_key="secret-key")
    assert sid == "abc"
    assert _header_value(reqs[0], "X-Endpoint-Key") == "secret-key"
    assert _header_value(reqs[0], "Origin") == "http://h/api"


def test_create_session_omits_endpoint_key_when_none(monkeypatch):
    reqs = []
    _install_urlopen(monkeypatch, [{"session_id": "abc"}], requests=reqs)
    C._create_session("http://h/api", "ep1", endpoint_key=None)
    assert _header_value(reqs[0], "X-Endpoint-Key") is None
    # Origin is ALWAYS present.
    assert _header_value(reqs[0], "Origin") == "http://h/api"


def test_create_session_no_session_id_raises(monkeypatch):
    _install_urlopen(monkeypatch, [{"unexpected": 1}])
    with pytest.raises(EgoHiveError):
        C._create_session("http://h/api", "ep1")


def test_egohive_chat_passes_endpoint_key_from_env(monkeypatch):
    monkeypatch.setenv("EGOHIVE_BASE_URL", "http://h/api")
    monkeypatch.setenv("EGOHIVE_ENDPOINT_ID", "ep1")
    monkeypatch.setenv("EGOHIVE_ENDPOINT_KEY", "envkey")
    reqs = []
    _install_urlopen(monkeypatch,
                     [{"session_id": "s"}, {"content": "ok"}], requests=reqs)
    C.egohive_chat("p")
    assert _header_value(reqs[0], "X-Endpoint-Key") == "envkey"


# --------------------------------------------------------------------------- #
# Error translation
# --------------------------------------------------------------------------- #
def test_httperror_becomes_egohive_error_with_code(env_creds, monkeypatch):
    err = urllib.error.HTTPError(
        "http://egohive.test/api/v1/session/ep-123", 503, "Service Unavailable",
        {}, io.BytesIO(b'{"detail": "agent down"}'),
    )
    _install_urlopen(monkeypatch, [err])
    with pytest.raises(EgoHiveError) as ei:
        C.egohive_chat("p")
    assert "HTTP 503" in str(ei.value)
    assert "agent down" in str(ei.value)


def test_urlerror_becomes_unreachable_egohive_error(env_creds, monkeypatch):
    _install_urlopen(monkeypatch, [urllib.error.URLError("connection refused")])
    with pytest.raises(EgoHiveError) as ei:
        C.egohive_chat("p")
    assert "unreachable" in str(ei.value)


def test_non_json_body_raises_egohive_error(env_creds, monkeypatch):
    _install_urlopen(monkeypatch, [b"<html>not json</html>"])
    with pytest.raises(EgoHiveError) as ei:
        C.egohive_chat("p")
    assert "non-JSON" in str(ei.value)


# --------------------------------------------------------------------------- #
# egohive_narrate
# --------------------------------------------------------------------------- #
def test_egohive_narrate_happy_path(env_creds, monkeypatch):
    reqs = []
    _install_urlopen(monkeypatch,
                     [{"session_id": "s"}, {"content": "Attendo on suurin."}],
                     requests=reqs)
    out = C.egohive_narrate("Tunnettuus", {"Attendo": 86, "Esperi": 75})
    assert out == "Attendo on suurin."
    # The prompt body includes the topic.
    body = json.loads(reqs[1].data.decode())
    assert "Tunnettuus" in body["content"]


def test_egohive_narrate_requires_topic_and_numbers(env_creds):
    with pytest.raises(EgoHiveError):
        C.egohive_narrate("", {"a": 1})
    with pytest.raises(EgoHiveError):
        C.egohive_narrate("Aihe", {})


# --------------------------------------------------------------------------- #
# load_creds precedence
# --------------------------------------------------------------------------- #
def test_load_creds_env_wins_over_creds_path(monkeypatch):
    monkeypatch.setenv("EGOHIVE_BASE_URL", "http://env/api")
    monkeypatch.setenv("EGOHIVE_ENDPOINT_ID", "env-ep")
    # A bogus creds_path is IGNORED because env vars take precedence.
    creds = C.load_creds(creds_path="/nonexistent/creds.json")
    assert creds["base_url"] == "http://env/api"
    assert creds["endpoint_id"] == "env-ep"


def test_load_creds_reads_file_when_no_env(monkeypatch, tmp_path):
    monkeypatch.delenv("EGOHIVE_BASE_URL", raising=False)
    monkeypatch.delenv("EGOHIVE_ENDPOINT_ID", raising=False)
    monkeypatch.delenv("EGOHIVE_CREDS_PATH", raising=False)
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({"base_url": "http://file/api", "endpoint_id": "fep"}))
    creds = C.load_creds(creds_path=str(p))
    assert creds["base_url"] == "http://file/api"
    assert creds["endpoint_id"] == "fep"


def test_load_creds_missing_file_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("EGOHIVE_BASE_URL", raising=False)
    monkeypatch.delenv("EGOHIVE_ENDPOINT_ID", raising=False)
    monkeypatch.delenv("EGOHIVE_CREDS_PATH", raising=False)
    with pytest.raises(EgoHiveError):
        C.load_creds(creds_path=str(tmp_path / "missing.json"))


def test_load_creds_file_missing_required_keys_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("EGOHIVE_BASE_URL", raising=False)
    monkeypatch.delenv("EGOHIVE_ENDPOINT_ID", raising=False)
    monkeypatch.delenv("EGOHIVE_CREDS_PATH", raising=False)
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({"base_url": "http://x"}))  # no endpoint_id
    with pytest.raises(EgoHiveError):
        C.load_creds(creds_path=str(p))


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def test_clean_strips_markdown_and_quotes_single_line():
    assert C._clean('  "**Otsikko**"  ') == "Otsikko"


def test_clean_keeps_only_first_line():
    # ACTUAL behavior: quote-unwrap runs before the newline split, so with a
    # trailing second line the wrapping quotes survive onto the first line.
    assert C._clean('"Otsikko"\nroskarivi') == '"Otsikko"'


def test_clean_empty_and_none():
    assert C._clean("") == ""
    assert C._clean(None) == ""


def test_build_prompt_includes_topic_and_numbers():
    prompt = C._build_prompt("Tunnettuus", {"Attendo": 86})
    assert "Tunnettuus" in prompt
    assert "Attendo" in prompt
    assert "86" in prompt
