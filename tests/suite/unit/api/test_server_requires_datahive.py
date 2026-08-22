"""A deployed server must refuse to start without a hive to store anything in.

`build_repository` degrades to an in-memory store when NSIGHT_DATAHIVE_URL is
unset. That is right for tests and catastrophic for a deployment: every
customer, case, material, report, user and grant would live until the next
restart, silently. BOTH compose files shipped in exactly that state — still
setting the NSIGHT_DEMO variables that stopped meaning anything when demo mode
was removed, and setting no datahive URL at all.

Run in a subprocess, because that is the real condition: uvicorn resolves
`reportbuilder.api.server:app` by importing the module and reading that
attribute, and the attribute is what runs the check — so an unconfigured
deployment dies before it binds a port, while an ordinary import (which the
tests use to reach `build_server_app`) stays free.
"""
from __future__ import annotations

import os
import subprocess
import sys

# Exactly what uvicorn does with "reportbuilder.api.server:app": import the
# module, then read the attribute. Importing alone is free on purpose — the
# tests reach `build_server_app` that way.
_BOOT = "from reportbuilder.api.server import app"


def _boot(**env) -> subprocess.CompletedProcess:
    clean = {k: v for k, v in os.environ.items()
             if k not in ("NSIGHT_DATAHIVE_URL", "NSIGHT_DATAHIVE_TOKEN")}
    clean.update(env)
    clean.setdefault("PYTHONPATH", "src")
    return subprocess.run([sys.executable, "-c", _BOOT], env=clean,
                          capture_output=True, text=True)


def test_refuses_to_start_with_no_datahive_configured():
    r = _boot()
    assert r.returncode != 0
    assert "NSIGHT_DATAHIVE_URL" in r.stderr


def test_refuses_to_start_with_a_url_but_no_token():
    # The half-configured case: the store would resolve, but every request
    # would 401 on the missing bearer. Fail at boot, not once per request.
    r = _boot(NSIGHT_DATAHIVE_URL="http://datahive:7891")
    assert r.returncode != 0
    assert "NSIGHT_DATAHIVE_TOKEN" in r.stderr


def test_starts_when_both_are_set():
    r = _boot(NSIGHT_DATAHIVE_URL="http://datahive:7891",
              NSIGHT_DATAHIVE_TOKEN="tok")
    assert r.returncode == 0, r.stderr[-2000:]
