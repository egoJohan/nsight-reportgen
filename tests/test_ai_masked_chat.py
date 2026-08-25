"""The prose path must go through datahive, and must fail closed.

nSight's slide titles and themes are written from a confidential brand tracker
— the client and every competitor, named, with things said about them the
client would not publish. The one thing that must never happen is that text
reaching a vendor in clear.

The last test is the guard that matters: it fails if anyone adds a function to
`reportbuilder.ai.text` that calls a model directly instead of taking the
injectable `chat` that defaults to the masked route.
"""
from __future__ import annotations

import inspect

import httpx
import pytest

from nsight.agent.egohive_client import EgoHiveError
from reportbuilder.ai import text as ai_text
from reportbuilder.ai.masked_chat import datahive_chat


@pytest.fixture(autouse=True)
def _hive_env(monkeypatch):
    monkeypatch.setenv("NSIGHT_DATAHIVE_URL", "http://hive.test")
    monkeypatch.setenv("NSIGHT_DATAHIVE_TOKEN", "t-1")


def _reply(monkeypatch, status: int, payload: dict):
    def fake_post(url, **kw):
        return httpx.Response(status, json=payload,
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)


def test_a_masked_reply_is_returned(monkeypatch):
    _reply(monkeypatch, 200, {"text": "  Otsikko  ", "pseudonymized": True})
    assert datahive_chat("kirjoita otsikko") == "Otsikko"


def test_a_refusal_to_mask_is_not_a_reason_to_send_anyway(monkeypatch):
    """412 means the control worked. The caller degrades to a deterministic
    default; it never retries without masking."""
    _reply(monkeypatch, 412, {"detail": {
        "error": "pseudonymization_unavailable",
        "why": "pii_pseudonymize_internal_llm is off for this tenant"}})
    with pytest.raises(EgoHiveError, match="off for this tenant"):
        datahive_chat("kirjoita otsikko")


def test_a_reply_that_admits_it_was_not_masked_is_refused(monkeypatch):
    """The endpoint reports what it actually did. False here means the study's
    names went to a vendor in clear — worth failing over, not logging."""
    _reply(monkeypatch, 200, {"text": "Otsikko", "pseudonymized": False})
    with pytest.raises(EgoHiveError, match="not pseudonymised"):
        datahive_chat("kirjoita otsikko")


def test_no_hive_configured_means_no_model_at_all(monkeypatch):
    """There is no unmasked fallback route, so an unconfigured hive is a
    refusal rather than a direct call to a vendor."""
    monkeypatch.delenv("NSIGHT_DATAHIVE_URL", raising=False)
    with pytest.raises(EgoHiveError, match="no masked route"):
        datahive_chat("kirjoita otsikko")


def test_every_prose_function_defaults_to_the_masked_route():
    """The guard. A new function here that calls a model directly would send a
    confidential tracker to a vendor, and nothing else in the suite would say so.
    """
    offenders = []
    for name, fn in vars(ai_text).items():
        if name.startswith("_") or not inspect.isfunction(fn):
            continue
        if fn.__module__ != ai_text.__name__:
            continue
        params = inspect.signature(fn).parameters
        if "chat" not in params:
            continue
        if params["chat"].default is not datahive_chat:
            offenders.append(name)
    assert not offenders, (
        f"these take `chat` but do not default to the masked route: {offenders}")
