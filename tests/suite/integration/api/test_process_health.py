"""GET /admin/process, and the watch that warns before the kernel acts.

Staging's backend was killed for memory on 2026-09-29 and nobody knew for three
weeks: it restarted, /readyz said ok, and the only trace was a line in dmesg.
What the process holds — memory, threads, DuckDB connections, unreaped children
— is now something an admin can ask for, and crossing a threshold is logged as
a warning at the time rather than discovered later.

Admin-only, unlike /readyz: process internals are for whoever runs the box.
"""
import logging
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api import process_health
from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.integration


def _client(*, admin: bool) -> TestClient:
    actor = User(id="usr-1", email="a@example.com", name="A", is_admin=admin)
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: Repository(InMemoryObjectStore())
    app.dependency_overrides[get_auth] = lambda: AuthContext(token="t")
    app.dependency_overrides[current_user] = lambda: actor
    return TestClient(app)


def test_a_non_admin_may_not_look():
    assert _client(admin=False).get("/admin/process").status_code == 403


def test_an_admin_sees_what_the_process_holds():
    body = _client(admin=True).get("/admin/process").json()

    assert body["rss_mb"] > 0
    assert body["peak_rss_mb"] >= body["rss_mb"]
    assert body["threads"] >= 1
    assert body["duckdb_connections"] >= 0
    assert body["uptime_seconds"] >= 0
    assert "memory_limit_mb" in body


def test_an_unreaped_child_is_counted():
    before = process_health.snapshot()["zombies"]
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        for _ in range(100):
            if process_health.snapshot()["zombies"] > before:
                break
            import time
            time.sleep(0.05)
        assert process_health.snapshot()["zombies"] == before + 1
    finally:
        child.wait()


def test_crossing_the_threshold_is_logged_as_a_warning(caplog):
    with caplog.at_level(logging.WARNING, logger=process_health.__name__):
        process_health.check(warn_rss_mb=1)

    assert any("memory" in r.getMessage() and r.levelno == logging.WARNING
               for r in caplog.records)


def test_below_the_threshold_nothing_is_logged(caplog):
    with caplog.at_level(logging.WARNING, logger=process_health.__name__):
        process_health.check(warn_rss_mb=10**9)

    assert not caplog.records


def test_the_running_app_checks_on_its_own(monkeypatch, caplog):
    """The warning is worth nothing if something has to ask for it."""
    monkeypatch.setenv("NSIGHT_PROCESS_WATCH_SECONDS", "0.05")
    monkeypatch.setenv("NSIGHT_RSS_WARN_MB", "1")
    import time

    with caplog.at_level(logging.WARNING, logger=process_health.__name__):
        with _client(admin=True):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not caplog.records:
                time.sleep(0.05)

    assert any("memory" in r.getMessage() for r in caplog.records)


def test_a_malformed_setting_neither_stops_the_app_nor_its_shutdown(monkeypatch, caplog):
    monkeypatch.setenv("NSIGHT_PROCESS_WATCH_SECONDS", "sixty")
    monkeypatch.setenv("NSIGHT_RSS_WARN_MB", "3G")

    with _client(admin=True) as c:
        assert c.get("/admin/process").status_code == 200
    # Leaving the block ran the shutdown; reaching here is the assertion.
