"""Readiness: can this deployment actually serve, or is the hive away?

nSight holds no data of its own — every case, report and material lives in the
hive — so while the hive is upgrading or down, the app can render its shell and
nothing else. Without something to ask, the browser learned that one failed
request at a time and showed a broken page or a queue of error toasts.

Deliberately UNAUTHENTICATED and cheap: it has to answer while a session is
dead, and the browser polls it to know when to take the maintenance screen
away, so it must not itself become load on a hive that is already struggling.
"""
import time

from reportbuilder.api import readiness


def test_it_reports_the_hive_as_up_when_the_probe_succeeds(monkeypatch):
    monkeypatch.setattr(readiness, "_probe_hive", lambda: True)
    readiness.forget()
    assert readiness.status() == {"ok": True, "hive": True}


def test_it_reports_the_hive_as_down_when_the_probe_fails(monkeypatch):
    monkeypatch.setattr(readiness, "_probe_hive", lambda: False)
    readiness.forget()
    assert readiness.status() == {"ok": False, "hive": False}


def test_the_probe_is_cached_so_polling_cannot_hammer_a_sick_hive(monkeypatch):
    calls = []

    def probe():
        calls.append(1)
        return True

    monkeypatch.setattr(readiness, "_probe_hive", probe)
    readiness.forget()
    for _ in range(20):
        readiness.status()
    assert len(calls) == 1, f"probed {len(calls)} times; the browser polls this"


def test_the_cache_expires_so_recovery_is_noticed(monkeypatch):
    state = {"up": False}
    monkeypatch.setattr(readiness, "_probe_hive", lambda: state["up"])
    monkeypatch.setattr(readiness, "CACHE_SECONDS", 0.0)
    readiness.forget()
    assert readiness.status()["hive"] is False
    state["up"] = True
    assert readiness.status()["hive"] is True


def test_a_configless_deployment_is_not_reported_as_broken(monkeypatch):
    """With no hive configured at all (a bare dev app), there is nothing to be
    down — the shell is all there is, and a maintenance screen would be a lie."""
    monkeypatch.delenv("NSIGHT_DATAHIVE_URL", raising=False)
    readiness.forget()
    assert readiness.status() == {"ok": True, "hive": True}


# --------------------------------------------------------------- the route ---
def test_the_route_answers_without_a_session(monkeypatch):
    """It has to work while the session is dead — that is one of the moments it
    exists for."""
    from fastapi.testclient import TestClient

    from reportbuilder.api.app import create_app

    monkeypatch.setattr(readiness, "_probe_hive", lambda: True)
    readiness.forget()
    r = TestClient(create_app()).get("/readyz")
    assert r.status_code == 200
    assert r.json()["hive"] is True


def test_the_route_says_503_when_the_hive_is_away(monkeypatch):
    """A status code a proxy or an uptime check can read, not just a body."""
    from fastapi.testclient import TestClient

    from reportbuilder.api.app import create_app

    monkeypatch.setattr(readiness, "_probe_hive", lambda: False)
    readiness.forget()
    r = TestClient(create_app()).get("/readyz")
    assert r.status_code == 503
    assert r.json()["hive"] is False


def test_a_hive_that_cannot_be_reached_is_a_503_not_a_500(monkeypatch):
    """"Connection refused" to the hive is not a bug in this app.

    It surfaced as an unhandled httpx.ConnectError -> 500, which tells a client
    "I broke" when the truth is "come back shortly" — and a browser cannot tell
    that apart from a genuine fault in one endpoint.
    """
    import httpx
    from fastapi.testclient import TestClient

    from reportbuilder.api.app import create_app

    app = create_app()

    @app.get("/_boom_transport")
    def _boom():
        raise httpx.ConnectError("[Errno 111] Connection refused")

    r = TestClient(app, raise_server_exceptions=False).get("/_boom_transport")
    assert r.status_code == 503, r.text
    assert "detail" in r.json()


def test_an_upstream_5xx_from_the_hive_is_also_a_503():
    """While the hive boots, its entrance answers but object reads return 500.

    Wrapped as a StoreError and left unhandled, that reached the browser as a
    500 — indistinguishable from a fault in nSight — during the exact window
    the maintenance screen exists for. It carries the upstream status now.
    """
    from fastapi.testclient import TestClient

    from reportbuilder.api.app import create_app
    from reportbuilder.store.seam import StoreError

    app = create_app()

    @app.get("/_boom_upstream")
    def _boom():
        raise StoreError("500 on settings/security.json: Internal Server Error",
                         status_code=500)

    r = TestClient(app, raise_server_exceptions=False).get("/_boom_upstream")
    assert r.status_code == 503, r.text


def test_a_store_error_that_is_not_upstream_still_surfaces_as_a_fault():
    """A bug in our own handling must not hide behind a maintenance screen."""
    from fastapi.testclient import TestClient

    from reportbuilder.api.app import create_app
    from reportbuilder.store.seam import StoreError

    app = create_app()

    @app.get("/_boom_ours")
    def _boom():
        raise StoreError("something we got wrong")

    r = TestClient(app, raise_server_exceptions=False).get("/_boom_ours")
    assert r.status_code == 500, r.text
