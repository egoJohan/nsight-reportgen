"""One connection pool for every hive call, and never anyone's identity in it.

A client per call opened a fresh connection per call — a preview makes a dozen.
It was per call because the bearer IS the caller's identity: a shared client
whose auth header is mutated per request reads with the wrong user's rights the
moment one reset is missed. The shared pool therefore holds no Authorization at
all, and every request brings its own. (perf, 2026-09-19)
"""
from __future__ import annotations

import httpx

from reportbuilder.store.datahive_objects import DataHiveObjectStore
from reportbuilder.store.seam import AuthContext


def _auth(token: str) -> AuthContext:
    return AuthContext(token=token)


def _store_seeing(seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, content=b"x")

    store = DataHiveObjectStore("http://hive.test")
    store._http = httpx.Client(base_url="http://hive.test",
                               transport=httpx.MockTransport(handler))
    return store


def test_each_request_carries_its_own_callers_token():
    seen: list = []
    store = _store_seeing(seen)
    store.get(_auth("alice"), "a/b")
    store.get(_auth("bob"), "a/b")
    store.get(_auth("alice"), "a/c")
    assert seen == ["Bearer alice", "Bearer bob", "Bearer alice"]


def test_the_shared_pool_holds_no_identity():
    seen: list = []
    store = _store_seeing(seen)
    store.get(_auth("alice"), "a/b")
    assert "authorization" not in {k.lower() for k in store._pool().headers}


def test_one_pool_serves_every_call():
    store = DataHiveObjectStore("http://hive.test")
    assert store._pool() is store._pool()
    assert "authorization" not in {k.lower() for k in store._pool().headers}
