"""Registering sensitive terms with datahive — and refusing to pretend.

The terms are stored POLICY, not a per-request argument, so a caller that
forgets everything still gets masked text. What must never happen is the
inverse: nSight recording an acceptance whose terms never reached datahive.
The report gate would open and nothing would be masked.
"""
from __future__ import annotations

import httpx
import pytest

from reportbuilder.store.datahive_pii import (
    ENTITY_TYPE, RegistrationFailed, register_sensitive_terms, registered_terms,
)


def _transport(handler):
    return httpx.MockTransport(handler)


def _echo_policy(monkeypatch, terms):
    """Stub the read-back `register_sensitive_terms` now does, answering with
    *terms* as though the PUT landed."""
    def handler(request):
        return httpx.Response(200, json={
            "policy": {"deny_terms": {ENTITY_TYPE: list(terms)}}})
    monkeypatch.setattr(httpx, "get",
                        lambda url, **kw: httpx.Client(transport=_transport(handler))
                        .get(url, **{k: v for k, v in kw.items()
                                     if k not in ("timeout", "params")}))


def test_it_sends_the_terms_as_stored_policy(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"saved": True})

    monkeypatch.setattr(httpx, "put",
                        lambda url, **kw: httpx.Client(transport=_transport(handler))
                        .put(url, **{k: v for k, v in kw.items() if k != "timeout"}))
    _echo_policy(monkeypatch, ["Attendo", "Esperi"])
    register_sensitive_terms("http://hive:7891", "tok", ["Attendo", "Esperi"])

    assert seen["url"].endswith("/api/v1/pii/policy")
    assert seen["auth"] == "Bearer tok"
    assert seen["body"]["policy"]["deny_terms"][ENTITY_TYPE] == ["Attendo", "Esperi"]
    assert ENTITY_TYPE in seen["body"]["policy"]["enabled_types"]


def test_an_unreachable_hive_raises_rather_than_returning(monkeypatch):
    """Silence here is the dangerous outcome: the caller would record an
    acceptance, the gate would open, and nothing would be masked."""
    def boom(url, **kw):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "put", boom)
    with pytest.raises(RegistrationFailed, match="could not reach"):
        register_sensitive_terms("http://hive:7891", "tok", ["Attendo"])


def test_a_refusal_raises_too(monkeypatch):
    def handler(request):
        return httpx.Response(403, text="admin required")

    monkeypatch.setattr(httpx, "put",
                        lambda url, **kw: httpx.Client(transport=_transport(handler))
                        .put(url, **{k: v for k, v in kw.items() if k != "timeout"}))
    with pytest.raises(RegistrationFailed, match="403"):
        register_sensitive_terms("http://hive:7891", "tok", ["Attendo"])


def test_registering_replaces_rather_than_merges(monkeypatch):
    """The accepted list is the whole truth. Merging would make a REMOVED term
    keep being masked for ever, with nothing showing why."""
    sent = {}

    def handler(request):
        sent["terms"] = __import__("json").loads(request.content)["policy"]["deny_terms"]
        return httpx.Response(200, json={"saved": True})

    monkeypatch.setattr(httpx, "put",
                        lambda url, **kw: httpx.Client(transport=_transport(handler))
                        .put(url, **{k: v for k, v in kw.items() if k != "timeout"}))
    _echo_policy(monkeypatch, ["Only", "These"])
    register_sensitive_terms("http://hive:7891", "tok", ["Only", "These"])
    assert sent["terms"][ENTITY_TYPE] == ["Only", "These"]


def test_it_can_read_back_what_the_hive_actually_holds(monkeypatch):
    """For showing the truth rather than what we believe we sent."""
    def handler(request):
        return httpx.Response(200, json={"policy": {
            "deny_terms": {ENTITY_TYPE: ["Attendo", "Esperi"]}}})

    monkeypatch.setattr(httpx, "get",
                        lambda url, **kw: httpx.Client(transport=_transport(handler))
                        .get(url, **{k: v for k, v in kw.items()
                                     if k not in ("timeout", "params")}))
    assert registered_terms("http://hive:7891", "tok") == ["Attendo", "Esperi"]


def test_a_write_the_hive_did_not_keep_is_a_failure(monkeypatch):
    """A 2xx says the request was accepted, not that the policy now holds the
    terms — and nothing downstream can tell the difference: `/llm/ask` answers
    `pseudonymized: true` with an EMPTY deny list, because the flag means the
    pseudonymiser ran. So the read-back is the only place the claim is checked.
    """
    monkeypatch.setattr(httpx, "put",
                        lambda url, **kw: httpx.Client(transport=_transport(
                            lambda r: httpx.Response(200, json={"saved": True})))
                        .put(url, **{k: v for k, v in kw.items() if k != "timeout"}))
    _echo_policy(monkeypatch, [])            # ...but it kept nothing

    with pytest.raises(RegistrationFailed) as exc:
        register_sensitive_terms("http://hive:7891", "tok", ["Attendo"])
    assert "not in its policy" in str(exc.value)
