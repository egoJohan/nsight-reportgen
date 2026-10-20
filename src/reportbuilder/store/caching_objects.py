"""The few hive reads a request repeats, held in this process.

In the hour before staging's backend was killed for memory (2026-09-29) it
fetched one material's .config from the hive 4,476 times and the whole .sav
1,003 times, for sixty-odd requests from one author; right after the restart a
burst of those reads timed the hive out. Three kinds of object are read far
more often than they change:

  * a material's .sav — never rewritten after upload (`attach_material` mints a
    new id for new bytes), so it is held until deleted. Only a few at once: a
    study is megabytes and the access pattern is one material at a time.
  * a material's .config — written only through this process, and every write
    passes through here and drops the held copy. Held briefly all the same, so
    a write from outside (the second backend a deploy runs) is seen.
  * the two access settings, asked on every request. A change made in the
    studio applies at once (its write drops the held copy); one made any other
    way applies within ACCESS_SECONDS.

Everything else passes straight through. A failed read and an absent object are
never remembered: the hive being briefly away must not be cached as an answer.

One process, one cache — as the material-config locks in repository.py assume.
With more than one uvicorn worker, a write in one would leave the others' copy
stale for up to the expiry, and this wants revisiting with them.
(tests/suite/unit/store/test_caching_store.py)
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable, Sequence

from reportbuilder.store import paths as P
from reportbuilder.store.seam import AuthContext, ObjectInfo, ObjectStore

_ACCESS_PATHS = frozenset({P.settings_path("access.json"),
                           P.settings_path("customer-access.json")})


def _kind(path: str) -> str | None:
    """'material', 'config', 'access' or None for a path that is not cached."""
    if path in _ACCESS_PATHS:
        return "access"
    parts = path.split("/")
    if len(parts) == 4 and parts[2] == "material":
        name = parts[3]
        if "." not in name:
            return "material"
        if name.endswith(".config") and name.count(".") == 1:
            return "config"
    return None


class CachingObjectStore:
    """An ObjectStore that answers the hot reads from memory."""

    MAX_MATERIALS = 4
    CONFIG_SECONDS = 60.0
    ACCESS_SECONDS = 5.0
    #: Material configs are a few KB; this only bounds a pathological tenant.
    MAX_SMALL = 512

    def __init__(self, inner: ObjectStore, *,
                 clock: Callable[[], float] = time.monotonic):
        self.inner = inner
        self._clock = clock
        self._lock = threading.Lock()
        self._materials: OrderedDict[str, bytes] = OrderedDict()
        # path -> (bytes, expires at)
        self._small: OrderedDict[str, tuple[bytes, float]] = OrderedDict()
        # Bumped by every write or delete of a cached kind, so a read that went
        # to the hive before one cannot store what it brings back over it. One
        # counter, not one per path: a write anywhere costs a concurrent read
        # its chance to be kept, which is rare and only a miss.
        self._writes = 0

    # -- the seam -----------------------------------------------------------

    def get(self, auth: AuthContext, path: str) -> bytes:
        kind = _kind(path)
        if kind is None:
            return self.inner.get(auth, path)
        with self._lock:
            hit = self._lookup(kind, path)
            if hit is not None:
                return hit
            writes = self._writes
        data = self.inner.get(auth, path)
        with self._lock:
            if self._writes == writes:
                self._store(kind, path, data)
        return data

    def get_fresh(self, auth: AuthContext, path: str) -> bytes:
        """From the hive whatever is held — for a read that is about to be
        modified and written back, where a held copy would undo a change made
        behind it (the second backend a deploy runs, a restore)."""
        kind = _kind(path)
        with self._lock:
            writes = self._writes
        data = self.inner.get(auth, path)
        if kind is not None:
            with self._lock:
                if self._writes == writes:
                    self._store(kind, path, data)
        return data

    def put(self, auth: AuthContext, path: str, data: bytes,
            content_type: str, labels: Sequence[str] = ()) -> str:
        # Dropped, not replaced, and whether or not the hive accepted it: with
        # two writes at once the hive keeps whichever LANDED last, which is not
        # knowable here, and a write that timed out may have landed anyway. The
        # next read asks the hive — one read per write, against the many reads
        # per write this exists for.
        try:
            return self.inner.put(auth, path, data, content_type, labels)
        finally:
            if _kind(path) is not None:
                self._forget(path)

    def delete(self, auth: AuthContext, path: str) -> None:
        try:
            self.inner.delete(auth, path)
        finally:
            # Even when the hive refuses (consent pending): a miss is harmless.
            self._forget(path)

    def list(self, auth: AuthContext, path_prefix: str = "",
             labels: Sequence[str] = ()) -> list[ObjectInfo]:
        return self.inner.list(auth, path_prefix, labels)

    def __getattr__(self, name):
        # Anything beyond the seam (approve, for the in-memory double) is the
        # wrapped store's own.
        return getattr(self.inner, name)

    # -- bookkeeping (call with self._lock held unless noted) ----------------

    def _lookup(self, kind: str, path: str) -> bytes | None:
        if kind == "material":
            data = self._materials.get(path)
            if data is not None:
                self._materials.move_to_end(path)
            return data
        entry = self._small.get(path)
        if entry is None:
            return None
        data, expires = entry
        if self._clock() >= expires:
            del self._small[path]
            return None
        return data

    def _store(self, kind: str, path: str, data: bytes) -> None:
        if kind == "material":
            self._materials[path] = data
            self._materials.move_to_end(path)
            while len(self._materials) > self.MAX_MATERIALS:
                self._materials.popitem(last=False)
            return
        ttl = self.ACCESS_SECONDS if kind == "access" else self.CONFIG_SECONDS
        self._small[path] = (data, self._clock() + ttl)
        self._small.move_to_end(path)
        while len(self._small) > self.MAX_SMALL:
            self._small.popitem(last=False)

    def _forget(self, path: str) -> None:
        """Takes the lock itself."""
        with self._lock:
            self._forget_locked(path)

    def _forget_locked(self, path: str) -> None:
        self._materials.pop(path, None)
        self._small.pop(path, None)
        self._writes += 1
