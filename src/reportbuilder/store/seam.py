"""The store seam: four operations over a path-addressed object store.

This is the ENTIRE storage surface nSight needs (design
`docs/superpowers/specs/2026-08-17-datahive-api-contract.md` §5). It replaces
twelve entity-specific methods (`create_case`, `save_report`,
`attach_material`, `load_material_config`, ...) that were shaped around an
assumed datahive contract which never existed.

Two properties are deliberate:

**Every call carries an auth context.** nSight talks to datahive AS THE
LOGGED-IN USER, so datahive itself enforces which paths that user may touch
(verified: an out-of-caveat read returns 404 and listings show only admitted
paths). The alternative — one service token — would make nSight's own code the
only thing keeping customers apart. Threading auth through the seam is cheap
now and expensive to retrofit, so it is here from the start.

**Deletes can require approval.** datahive gates destructive operations behind
a consent request (floor rule 4). `delete` therefore raises
:class:`ConsentRequired` carrying the approval envelope rather than pretending
the object is gone — the caller drives the approval and retries.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class AuthContext:
    """Who is making this call. `token` is the logged-in user's bearer."""
    token: str


@dataclass(frozen=True)
class ObjectInfo:
    """A listing row. Never carries bytes — listings stay cheap."""
    path: str
    size: int
    content_type: str
    etag: str
    labels: tuple[str, ...] = ()
    object_id: str = ""


class StoreError(Exception):
    """Base for seam failures.

    `status_code` is the status the STORE answered with, when the failure came
    from upstream rather than from us. It is what lets the API tell "the hive is
    unwell, come back shortly" (503) apart from "we mishandled something" (500)
    — a distinction the browser uses to choose between a maintenance screen and
    an error, and one that a message string alone could only be guessed from.
    """

    def __init__(self, *args, status_code: int | None = None):
        super().__init__(*args)
        self.status_code = status_code


class NotFound(StoreError):
    """No object at that path, or the caller may not see it.

    datahive deliberately conflates "absent" with "not yours" so it cannot leak
    the existence of another customer's data. Callers must not infer existence
    from this.
    """


class AccessDenied(StoreError):
    """Authenticated, but not permitted (e.g. a read-only token writing)."""


class StaleWrite(StoreError):
    """The caller is writing over a version it has not seen.

    A report save replaces the whole document, so a save built on a copy
    somebody else has since replaced is not a merge conflict — it is a total
    loss of their work. The editing lock normally prevents two people getting
    that far, but it expires by design (a crashed browser must not strand a
    report for ever), and that leaves a window.
    """


class ConsentRequired(StoreError):
    """A destructive operation needs explicit approval before it will run.

    Carries datahive's envelope verbatim so a UI can show what is about to be
    destroyed and drive the approval, rather than the caller inventing its own
    wording for someone else's data-safety decision.
    """

    def __init__(self, request_id: str, action: str, target: str, envelope: dict):
        super().__init__(f"{action} on {target} requires consent ({request_id})")
        self.request_id = request_id
        self.action = action
        self.target = target
        self.envelope = envelope


class ObjectStore(Protocol):
    """The seam. Implemented once against datahive, once in-memory for tests."""

    def put(self, auth: AuthContext, path: str, data: bytes,
            content_type: str, labels: Sequence[str] = ()) -> str:
        """Store *data* at *path*; return the object id. Overwrites in place."""
        ...

    def get(self, auth: AuthContext, path: str) -> bytes:
        """Return the stored bytes, byte-exact. Raises :class:`NotFound`."""
        ...

    def list(self, auth: AuthContext, path_prefix: str = "",
             labels: Sequence[str] = ()) -> list[ObjectInfo]:
        """Rows under *path_prefix*, optionally filtered by *labels*.

        Filtering happens server-side on both axes, and the result is already
        restricted to what this caller may see — nSight must never receive a
        broader list and narrow it itself.
        """
        ...

    def delete(self, auth: AuthContext, path: str) -> None:
        """Remove the object. Raises :class:`ConsentRequired` when datahive
        wants explicit approval first."""
        ...
