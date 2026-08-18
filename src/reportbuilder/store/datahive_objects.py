"""The seam, implemented against datahive's path-scoped object store.

Endpoints (verified live 2026-08-18 against datahive c88e1c84):

    PUT    /api/v1/objects              multipart: file, path, content_type, labels
    GET    /api/v1/objects?path=
    GET    /api/v1/objects/list?path_prefix=&label=
    DELETE /api/v1/objects?path=

The store is explicitly non-indexing (`indexed=false`) — not chunked, embedded
or classified — which is why it and not `items` is the right home for report
JSON: the serde tests rest on a byte-exact round trip.
"""
from __future__ import annotations

from typing import Sequence

import httpx

from reportbuilder.store.seam import (
    AccessDenied, AuthContext, ConsentRequired, NotFound, ObjectInfo, StoreError,
)


class DataHiveObjectStore:
    """Talks to one datahive instance. Stateless apart from the base URL."""

    def __init__(self, base_url: str, *, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _client(self, auth: AuthContext) -> httpx.Client:
        # A client per call: the bearer IS the caller's identity, so a shared
        # client would have to mutate its own auth header per request — one
        # missed reset and a user reads with another user's rights.
        return httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {auth.token}"},
            timeout=self._timeout,
        )

    @staticmethod
    def _raise(resp: httpx.Response, path: str) -> None:
        if resp.status_code == 404:
            raise NotFound(path)
        if resp.status_code == 403:
            # 403 is overloaded: a plain denial, or a consent request. Only the
            # body distinguishes them, and treating a consent request as a
            # denial would strand the user with no way to proceed.
            try:
                body = resp.json()
            except ValueError:
                body = {}
            if body.get("error") == "consent_required":
                c = body.get("consent", {})
                raise ConsentRequired(
                    request_id=c.get("request_id", ""),
                    action=c.get("action", ""),
                    target=c.get("target", path),
                    envelope=c,
                )
            raise AccessDenied(f"{path}: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise StoreError(f"{resp.status_code} on {path}: {resp.text[:200]}")

    def put(self, auth: AuthContext, path: str, data: bytes,
            content_type: str, labels: Sequence[str] = ()) -> str:
        form: dict[str, object] = {"path": path, "content_type": content_type}
        if labels:
            # A repeated field, not a comma-joined string: datahive expands each
            # label separately ("nsight:report" -> ["nsight", "nsight:report"]).
            form["labels"] = list(labels)
        with self._client(auth) as c:
            r = c.put("/api/v1/objects",
                      files={"file": (path.rsplit("/", 1)[-1], data, content_type)},
                      data=form)
        self._raise(r, path)
        return r.json().get("object_id", "")

    def get(self, auth: AuthContext, path: str) -> bytes:
        with self._client(auth) as c:
            r = c.get("/api/v1/objects", params={"path": path})
        self._raise(r, path)
        return r.content

    def list(self, auth: AuthContext, path_prefix: str = "",
             labels: Sequence[str] = ()) -> list[ObjectInfo]:
        params: list[tuple[str, str]] = []
        if path_prefix:
            params.append(("path_prefix", path_prefix))
        params += [("label", l) for l in labels]
        with self._client(auth) as c:
            r = c.get("/api/v1/objects/list", params=params)
        self._raise(r, path_prefix or "/")
        return [
            ObjectInfo(
                path=o["path"],
                size=int(o.get("size") or 0),
                content_type=o.get("content_type") or "",
                etag=o.get("etag") or "",
                labels=tuple(o.get("labels") or ()),
                object_id=o.get("object_id") or "",
            )
            for o in r.json().get("objects", [])
        ]

    def delete(self, auth: AuthContext, path: str) -> None:
        with self._client(auth) as c:
            r = c.request("DELETE", "/api/v1/objects", params={"path": path})
        self._raise(r, path)
