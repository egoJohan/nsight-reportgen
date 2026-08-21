"""Everything nSight keeps, in one zip — and back again.

The point is disaster recovery: if the hive is lost, restoring one file must
bring back the customers, studies, uploaded SAVs, report definitions, brand
templates, fonts, users, grants, invitations and settings. Rendered decks are
NOT in it: they are derived from the report definition and the template, both
of which are, so they can be generated again. That is the one large thing in
the store, and leaving it out is what keeps a backup a manageable size.

Format — a zip holding:

    manifest.json     what is inside, and where each object belongs
    README.txt        the same, for a human who opens the file in a year
    objects/000001    one object's bytes, verbatim
    objects/000002    ...

Members are NUMBERED, not named after their store path. A zip that names its
members after paths from the archive itself is how directory traversal gets
in ("../../etc/..."), and store paths are not constrained to be safe file
names in the first place. The real path lives in the manifest, which is
validated on the way back in.

The backup carries credential material: Argon2id password hashes and the
session signing key. That is deliberate — a restore has to leave people able
to sign in, and with no mail server configured a password reset is not
currently a route back. It does mean the file itself is a secret: whoever
holds it can mint session cookies until that key is rotated.
"""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

from reportbuilder.store import paths as P
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, NotFound

FORMAT = "nsight-backup"
VERSION = 1

# Decks are derived — the report definition and the template that made them
# are both in the backup, so they can be rendered again. Sessions are the
# other omission: a live sign-in on a host that no longer exists is not worth
# restoring, and carrying them would resurrect sessions revoked after the
# backup was taken. Everyone signs in again after a restore.
EXCLUDED_LABELS = frozenset({P.LABEL_RENDER, P.LABEL_SESSION})

# A restore reads a file someone uploaded. Even from an admin, an archive that
# claims 400 GB of members should be refused rather than written object by
# object into the hive until something falls over.
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024   # 8 GiB uncompressed
MAX_OBJECTS = 200_000

_README = """\
nSight backup
=============

manifest.json lists every object: its path in the store, its content type,
its labels, and the zip member holding its bytes. Members are numbered rather
than named after store paths, so that restoring cannot be talked into writing
somewhere it should not.

Rendered decks are not included — they are regenerated from the report
definitions and templates that are. Reports therefore come back as drafts.

This file contains password hashes and the session signing key. Treat it as
you would a password database.
"""


@dataclass
class BackupSummary:
    """What a `write` produced."""
    object_count: int = 0
    total_bytes: int = 0
    skipped: int = 0            # excluded by label (decks, sessions)


@dataclass
class RestoreSummary:
    """What a `read` wrote."""
    restored: int = 0
    total_bytes: int = 0
    problems: list[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _strip_render_stamp(data: bytes) -> bytes:
    """Report sidecars claim a finished deck; the backup has no decks.

    `rendered` is read off `render_key` (repository.list_reports), so carrying
    the stamp without the bytes would restore reports that call themselves
    generated and 404 when downloaded. Dropping it here — rather than at
    restore time — keeps the archive self-consistent: what it says is what it
    holds.
    """
    try:
        d = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return data  # not JSON we understand; store it untouched
    if not isinstance(d, dict):
        return data
    if "render_key" not in d and "rendered_at" not in d:
        return data
    d.pop("render_key", None)
    d.pop("rendered_at", None)
    return json.dumps(d).encode("utf-8")


def write(repo: Repository, auth: AuthContext, out) -> BackupSummary:
    """Write a backup zip of everything in *repo* to the binary stream *out*.

    One listing for the whole store, then one get per object. Objects are
    streamed into the zip as they are read, so peak memory is one object, not
    the whole archive — a customer's SAV files are the large thing here.
    """
    summary = BackupSummary()
    entries: list[dict] = []

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info in sorted(repo.store.list(auth, ""), key=lambda i: i.path):
            if EXCLUDED_LABELS.intersection(info.labels):
                summary.skipped += 1
                continue
            try:
                data = repo.store.get(auth, info.path)
            except NotFound:
                # Deleted between the listing and the read. Not an error: the
                # backup is a snapshot, and this object was gone by the time
                # we reached it.
                summary.skipped += 1
                continue
            if P.LABEL_REPORT_META in info.labels:
                data = _strip_render_stamp(data)

            member = f"objects/{len(entries) + 1:06d}"
            z.writestr(member, data)
            entries.append({
                "member": member,
                "path": info.path,
                "content_type": info.content_type or "application/octet-stream",
                "labels": list(info.labels),
                "size": len(data),
            })
            summary.object_count += 1
            summary.total_bytes += len(data)

        z.writestr("manifest.json", json.dumps({
            "format": FORMAT,
            "version": VERSION,
            "created_at": _now(),
            "object_count": summary.object_count,
            "total_bytes": summary.total_bytes,
            "excluded_labels": sorted(EXCLUDED_LABELS),
            "objects": entries,
        }, indent=2).encode("utf-8"))
        z.writestr("README.txt", _README.encode("utf-8"))

    return summary


class BadBackup(Exception):
    """The uploaded file is not a backup this version can restore."""


def _manifest(z: zipfile.ZipFile) -> dict:
    try:
        raw = z.read("manifest.json")
    except KeyError:
        raise BadBackup("No manifest.json — this is not an nSight backup.") from None
    try:
        m = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BadBackup(f"manifest.json is not readable JSON: {exc}") from None
    if not isinstance(m, dict) or m.get("format") != FORMAT:
        raise BadBackup("This zip is not an nSight backup.")
    version = m.get("version")
    if version != VERSION:
        raise BadBackup(
            f"Backup format version {version!r}; this nSight restores version {VERSION}.")
    objects = m.get("objects")
    if not isinstance(objects, list):
        raise BadBackup("manifest.json lists no objects.")
    if len(objects) > MAX_OBJECTS:
        raise BadBackup(f"Backup declares {len(objects)} objects; the limit is {MAX_OBJECTS}.")
    return m


def read(repo: Repository, auth: AuthContext, source) -> RestoreSummary:
    """Restore a backup zip read from *source* (a path or a binary stream).

    Objects are written over whatever is at the same path, and anything not in
    the backup is left alone: a restore puts back what was lost without
    deleting what survived. The consequence is worth stating plainly — a
    customer deleted after the backup was taken comes back.

    A member that fails to restore is recorded in `problems` and the rest
    continue. Half a restore beats none: the alternative is stopping on the
    first bad object and leaving the hive in a state nobody chose.
    """
    summary = RestoreSummary()
    with zipfile.ZipFile(source) as z:
        m = _manifest(z)

        declared = sum(int(e.get("size") or 0) for e in m["objects"] if isinstance(e, dict))
        if declared > MAX_TOTAL_BYTES:
            raise BadBackup(
                f"Backup declares {declared} bytes, above the {MAX_TOTAL_BYTES} limit.")

        for entry in m["objects"]:
            if not isinstance(entry, dict):
                summary.problems.append("Skipped a malformed manifest entry.")
                continue
            path, member = entry.get("path"), entry.get("member")
            if not path or not member:
                summary.problems.append(f"Skipped an entry with no path or member: {entry!r}")
                continue
            # The manifest decides where bytes land, so it is checked, not
            # trusted: a path that climbs out of the store or is absolute
            # would write outside everything the app addresses.
            if path.startswith("/") or ".." in path.split("/"):
                summary.problems.append(f"Refused a suspicious path: {path}")
                continue
            try:
                data = z.read(member)
            except KeyError:
                summary.problems.append(f"Missing from the zip: {member} ({path})")
                continue
            try:
                repo.store.put(auth, path, data,
                               entry.get("content_type") or "application/octet-stream",
                               labels=list(entry.get("labels") or ()))
            except Exception as exc:  # noqa: BLE001 — one bad object must not end the restore
                summary.problems.append(f"{path}: {exc}")
                continue
            summary.restored += 1
            summary.total_bytes += len(data)
    return summary


def to_bytes(repo: Repository, auth: AuthContext) -> bytes:
    """The whole backup in memory. For tests and small stores."""
    buf = io.BytesIO()
    write(repo, auth, buf)
    return buf.getvalue()
