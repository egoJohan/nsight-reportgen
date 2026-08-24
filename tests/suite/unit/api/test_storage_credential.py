"""Which credential nSight uses to reach storage.

Its own, always. `get_auth` used to prefer an `Authorization` header from the
caller — a leftover from before there was a login, when the plan was that the
OIDC flow would supply it. It did not: sign-in is a session cookie, and nothing
in the app, the tests or the scripts ever sent this header.

What remained was a way for a request to choose which hive nSight would read
and write on its behalf, reachable by anyone who could set a header, serving no
caller at all. Who you are and what you may touch is settled by `current_user`
and `auth/permissions.py` — never by a token you hand us.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from reportbuilder.api.deps_store import get_auth


def test_it_uses_the_service_credential(monkeypatch):
    monkeypatch.setenv("NSIGHT_DATAHIVE_TOKEN", "service-token")
    assert get_auth().token == "service-token"


def test_it_takes_no_arguments_from_the_request():
    """The header is not merely ignored — it is not a parameter, so FastAPI
    never binds one and it cannot come back by someone re-adding a default."""
    import inspect

    assert list(inspect.signature(get_auth).parameters) == []


def test_a_caller_supplying_a_bearer_does_not_change_which_hive_we_reach():
    """The behaviour, not the signature.

    The two tests above would also "fail" against the old code for an
    incidental reason — the reverted default is a fastapi Header object, so
    `.lower()` raises — and neither says anything about the header being
    ignored. This drives a real route with an attacker's Authorization on it
    and looks at the credential the store was actually handed.
    """
    import os

    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from reportbuilder.api.deps_store import get_auth as dep

    seen: list[str] = []
    app = FastAPI()

    @app.get("/probe")
    def probe(auth=Depends(dep)):
        seen.append(auth.token)
        return {"ok": True}

    os.environ["NSIGHT_DATAHIVE_TOKEN"] = "the-service-token"
    try:
        client = TestClient(app)
        assert client.get("/probe").status_code == 200
        assert client.get(
            "/probe", headers={"Authorization": "Bearer attacker-token"}
        ).status_code == 200
    finally:
        os.environ.pop("NSIGHT_DATAHIVE_TOKEN", None)

    assert seen == ["the-service-token", "the-service-token"], seen
    assert "attacker-token" not in seen


def test_it_fails_closed_when_unconfigured(monkeypatch):
    """Booting without it used to mean an in-memory store that lost everything
    on restart, silently."""
    monkeypatch.delenv("NSIGHT_DATAHIVE_TOKEN", raising=False)
    with pytest.raises(HTTPException) as caught:
        get_auth()
    assert caught.value.status_code == 401
