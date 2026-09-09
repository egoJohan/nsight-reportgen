"""No prose is written for a study whose names are not actually being masked.

`masked_chat` asserts datahive's `pseudonymized` flag, and that flag means "the
pseudonymiser ran" — it comes back True with an EMPTY deny list, verified
against the live hive on 2026-09-09. So the assertion cannot tell "your names
were masked" from "there was nothing to mask with", and on that morning the
tenant policy was empty while thirteen studies showed terms accepted.

This guard closes that: before any AI route writes text, the study's accepted
terms are checked against the policy datahive is actually holding.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from reportbuilder.api import routes_ai
from reportbuilder.store import datahive_pii


class _Client:
    def __init__(self, accepted):
        self._accepted = accepted

    def sensitive_terms(self, material_id):
        return {"accepted": self._accepted}


class _Auth:
    token = "tok"


@pytest.fixture(autouse=True)
def _hive(monkeypatch):
    monkeypatch.setenv("NSIGHT_DATAHIVE_URL", "http://hive:7891")
    datahive_pii.forget_policy_cache()
    yield
    datahive_pii.forget_policy_cache()


def _policy(monkeypatch, terms):
    monkeypatch.setattr(datahive_pii, "registered_terms",
                        lambda *a, **kw: list(terms))


def test_it_passes_when_every_accepted_term_is_live(monkeypatch):
    _policy(monkeypatch, ["Attendo", "Esperi"])
    routes_ai.require_masking_ready("mat-1", _Client(["Attendo"]), _Auth())


def test_it_refuses_when_the_policy_lost_the_terms(monkeypatch):
    """The 2026-09-09 state: accepted here, absent there."""
    _policy(monkeypatch, [])
    with pytest.raises(HTTPException) as exc:
        routes_ai.require_masking_ready("mat-1", _Client(["Attendo"]), _Auth())
    assert exc.value.status_code == 503
    assert "not registered for masking" in str(exc.value.detail)


def test_it_refuses_when_only_some_terms_are_live(monkeypatch):
    _policy(monkeypatch, ["Attendo"])
    with pytest.raises(HTTPException):
        routes_ai.require_masking_ready("mat-1", _Client(["Attendo", "Esperi"]),
                                        _Auth())


def test_an_empty_acceptance_is_a_real_answer(monkeypatch):
    """"I looked; this study names no companies" has nothing to check."""
    _policy(monkeypatch, [])
    routes_ai.require_masking_ready("mat-1", _Client([]), _Auth())


def test_a_study_nobody_reviewed_is_left_to_the_report_gate(monkeypatch):
    _policy(monkeypatch, [])
    routes_ai.require_masking_ready("mat-1", _Client(None), _Auth())


def test_no_hive_configured_is_silent(monkeypatch):
    """There is no model to reach either — `masked_chat` refuses outright."""
    monkeypatch.delenv("NSIGHT_DATAHIVE_URL", raising=False)
    routes_ai.require_masking_ready("mat-1", _Client(["Attendo"]), _Auth())


def test_a_store_that_cannot_be_read_refuses_rather_than_assumes(monkeypatch):
    def _boom(*a, **kw):
        raise datahive_pii.RegistrationFailed("unreachable")
    monkeypatch.setattr(datahive_pii, "registered_terms", _boom)
    with pytest.raises(HTTPException) as exc:
        routes_ai.require_masking_ready("mat-1", _Client(["Attendo"]), _Auth())
    assert exc.value.status_code == 503


def test_every_route_that_writes_prose_carries_the_guard():
    """Every POST on this router asks a model — including `/chat`, whose path
    says nothing about AI. Enumerated rather than listed, so an eighth route
    cannot be added without it."""
    checked = 0
    for route in routes_ai.ai_router.routes:
        if "POST" not in getattr(route, "methods", set()):
            continue
        names = {d.call.__name__
                 for d in getattr(getattr(route, "dependant", None), "dependencies", [])
                 if getattr(d, "call", None)}
        assert "require_masking_ready" in names, f"{route.path} is unguarded"
        checked += 1
    assert checked >= 7, f"only {checked} prose routes found"
