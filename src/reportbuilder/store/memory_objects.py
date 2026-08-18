"""The seam, in memory. The test double, and the offline dev backend.

Deliberately mirrors datahive's *awkward* behaviours rather than its convenient
ones — a double that is nicer than production teaches tests to expect things
production will not do:

  * `NotFound` for both absent and forbidden, so no caller learns to infer
    existence from the error.
  * `delete` raises `ConsentRequired` on first call and only succeeds after the
    request is approved, because that is what datahive does to every
    destructive operation.
  * path caveats are enforced, so an over-broad path in a test fails here
    rather than in production.

This is what replaces InMemoryDataHiveClient once the call sites move; unlike
that store it is a few dozen lines, because the seam it implements is four
methods instead of twelve.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Sequence

from reportbuilder.store.seam import (
    AccessDenied, AuthContext, ConsentRequired, NotFound, ObjectInfo,
)


def _expand(labels: Sequence[str]) -> tuple[str, ...]:
    """Mirror datahive's hierarchical labels: "a:b" stores {"a", "a:b"}."""
    out: set[str] = set()
    for label in labels:
        parts = label.split(":")
        acc = ""
        for part in parts:
            acc = f"{acc}:{part}" if acc else part
            out.add(acc)
    return tuple(sorted(out))


@dataclass
class _Stored:
    data: bytes
    content_type: str
    labels: tuple[str, ...]
    object_id: str


@dataclass
class InMemoryObjectStore:
    """An object store in a dict.

    `caveats` maps a token to the path prefixes it may touch; an empty list
    means unrestricted, matching `datahive auth grant --paths ""`.
    """
    objects: dict[str, _Stored] = field(default_factory=dict)
    caveats: dict[str, list[str]] = field(default_factory=dict)
    read_only: set[str] = field(default_factory=set)
    approved: set[str] = field(default_factory=set)
    _pending: dict[str, str] = field(default_factory=dict)

    def _admits(self, auth: AuthContext, path: str) -> bool:
        allowed = self.caveats.get(auth.token, [])
        return not allowed or any(path.startswith(p) for p in allowed)

    def put(self, auth: AuthContext, path: str, data: bytes,
            content_type: str, labels: Sequence[str] = ()) -> str:
        if not self._admits(auth, path):
            raise NotFound(path)
        if auth.token in self.read_only:
            raise AccessDenied(path)
        oid = str(uuid.uuid4())
        self.objects[path] = _Stored(bytes(data), content_type, _expand(labels), oid)
        return oid

    def get(self, auth: AuthContext, path: str) -> bytes:
        if not self._admits(auth, path) or path not in self.objects:
            raise NotFound(path)
        return self.objects[path].data

    def list(self, auth: AuthContext, path_prefix: str = "",
             labels: Sequence[str] = ()) -> list[ObjectInfo]:
        want = set(labels)
        out = []
        for path, obj in sorted(self.objects.items()):
            if not path.startswith(path_prefix) or not self._admits(auth, path):
                continue
            if want and not want.issubset(set(obj.labels)):
                continue
            out.append(ObjectInfo(
                path=path, size=len(obj.data), content_type=obj.content_type,
                etag=hashlib.md5(obj.data).hexdigest(),
                labels=obj.labels, object_id=obj.object_id,
            ))
        return out

    def delete(self, auth: AuthContext, path: str) -> None:
        if not self._admits(auth, path) or path not in self.objects:
            raise NotFound(path)
        if auth.token in self.read_only:
            raise AccessDenied(path)
        request_id = self._pending.get(path)
        if request_id is None or request_id not in self.approved:
            request_id = request_id or f"cr_{uuid.uuid4().hex[:16]}"
            self._pending[path] = request_id
            raise ConsentRequired(
                request_id=request_id, action="object.delete", target=path,
                envelope={"request_id": request_id, "action": "object.delete",
                          "target": path, "target_kind": "path",
                          "reason": "object.delete is a destructive operation",
                          "approval_urls": {"cli": f"datahive consent approve {request_id}"}},
            )
        del self.objects[path]
        self._pending.pop(path, None)

    # -- test helper ------------------------------------------------------
    def approve(self, request_id: str) -> None:
        """Stand in for `datahive consent approve`."""
        self.approved.add(request_id)
