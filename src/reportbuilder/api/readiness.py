"""Can this deployment serve, or is the hive away?

nSight holds no data of its own — every case, report and material lives in the
hive — so while the hive is upgrading or down, this app can render its shell
and nothing else. The browser used to learn that one failed request at a time,
which showed as a broken page or a queue of error toasts; with something to
ask, it can say "under maintenance" once and take it back when the hive
returns.

The probe is CHEAP and CACHED. The browser polls this while the screen is up,
and a readiness check that hammers a hive already struggling would be part of
the problem. It is also unauthenticated at the route: it must answer while a
session is dead, and it reveals nothing beyond "the thing behind me is up".
"""
from __future__ import annotations

import logging
import os
import threading
import time
import urllib.request

log = logging.getLogger(__name__)

#: How long one probe result stands. Short enough that a hive coming back is
#: noticed within a few seconds of the browser's next poll; long enough that a
#: page full of failing requests cannot turn into a probe storm.
CACHE_SECONDS = 5.0
PROBE_TIMEOUT_SECONDS = 3.0

_lock = threading.Lock()
_cached: tuple[float, dict] | None = None


def _hive_url() -> str:
    return (os.environ.get("NSIGHT_DATAHIVE_URL") or "").rstrip("/")


def _probe_hive() -> bool:
    """Ask the boundary whether the DEPLOYMENT is ready, not just alive.

    `/readyz`, not `/healthz`: healthz is the entrance's own liveness and
    answers "up" while the hive behind it is still booting and every object
    read returns 500. Probing that dismissed the maintenance screen a good
    fifteen seconds early, straight back onto a page that still could not load
    — measured, not theorised.
    """
    url = _hive_url()
    if not url:
        return True
    try:
        with urllib.request.urlopen(f"{url}/readyz",
                                    timeout=PROBE_TIMEOUT_SECONDS) as r:
            if not (200 <= r.status < 400):
                return False
            import json as _json
            body = _json.loads(r.read() or b"{}")
            # An older entrance answers 200 with no verdict in the body; treat
            # the status alone as the answer rather than calling it down.
            return bool(body.get("ok", True))
    except Exception as exc:  # noqa: BLE001 — any failure means "not now"
        log.info("readiness: hive probe failed (%s)", exc)
        return False


def forget() -> None:
    """Drop the cached result. For tests, and for anything that must re-probe."""
    global _cached
    with _lock:
        _cached = None


def status() -> dict:
    """``{"ok": bool, "hive": bool}`` — cached for `CACHE_SECONDS`.

    With no hive configured at all (a bare dev app) there is nothing to be
    down, and reporting trouble would be a lie.
    """
    global _cached
    now = time.monotonic()
    with _lock:
        if _cached is not None and now - _cached[0] < CACHE_SECONDS:
            return dict(_cached[1])
    hive_up = _probe_hive()
    result = {"ok": hive_up, "hive": hive_up}
    with _lock:
        _cached = (now, result)
    return dict(result)
