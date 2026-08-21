"""Asiakas -> Case -> Raportti, over the object seam.

The hierarchy the Asiakkuuden hallinta card specifies:

    Asiakas  — name given at creation
    Case     — belongs to exactly one Asiakas; defaults to the material filename
    Raportti — belongs to exactly one Case; defaults to "Raportti n", 1-based

None of that is datahive's concern. Datahive stores bytes at paths; the tree
lives here, expressed as path structure (`store/paths.py`) plus labels. That
split is the whole point of the migration: when the backend swaps from the JSON
store to datahive, this file does not change.

Ids vs names: a path segment is an ID and never a name, so renaming is a
metadata write rather than a data migration. Names live in a small JSON sidecar
per container (`customer.json`, `case.json`).
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Sequence

from reportbuilder.auth.permissions import Grant, User, may_read
from reportbuilder.store import paths as P
from reportbuilder.store.seam import AuthContext, ConsentRequired, NotFound, ObjectStore

_JSON = "application/json"
_PPTX = ("application/vnd.openxmlformats-officedocument.presentationml.presentation")


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    # The template bound AT THIS LEVEL, "" when none. Surfaced because the UI
    # must distinguish "set here" from "inherited" to show the right thing.
    template_id: str = ""


@dataclass(frozen=True)
class Case:
    id: str
    customer_id: str
    name: str
    template_id: str = ""


@dataclass(frozen=True)
class Material:
    id: str
    case_id: str
    customer_id: str
    name: str
    size: int = 0


@dataclass(frozen=True)
class Template:
    id: str
    customer_id: str
    name: str
    size: int = 0
    layout_name: str = ""
    palette: tuple[str, ...] = ()
    heading_font: str = ""
    body_font: str = ""
    # Whether the render host can actually supply the fonts this template names.
    # Recorded at upload; a name is not the font, and a missing one is
    # substituted silently by fontconfig unless something says otherwise.
    fonts: tuple[dict, ...] = ()


@dataclass(frozen=True)
class FontFile:
    """A font an admin installed, stored so it outlives the render host."""

    id: str
    family: str
    filename: str = ""
    size: int = 0


@dataclass(frozen=True)
class ReportRef:
    id: str
    case_id: str
    customer_id: str
    name: str
    modified_at: str = ""


@dataclass(frozen=True)
class Session:
    id: str
    user_id: str
    created: str
    last_seen: str
    expires: str


@dataclass(frozen=True)
class Invite:
    """An admin's offer of access to one email address (spec §6).

    Persists PAST acceptance: `accepted_user_id`/`accepted_at`, once set,
    are what let `auth.invites.revoke_invitation` (Task 5) find and remove
    the user an accepted invite became, so revoking access an admin
    granted by mistake works even after the invitee has signed in. The
    record is removed only by an explicit `delete_invite` (a revoke),
    never automatically on acceptance or expiry.
    """
    id: str
    email: str
    grants: tuple[Grant, ...]
    invited_by: str
    invited_at: str
    expires: str
    accepted_user_id: str | None = None
    accepted_at: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Smaller number = more specific. A choice at a more specific level overrides a
# pin made at a broader one.
# How specific a binding is; lower wins. "first" is the asiakas's first template
# standing in when nothing is bound anywhere — no more specific than the asiakas
# itself, and it must be present here or resolve_template raises comparing it
# against a report's pinned level.
_SPECIFICITY = {"report": 0, "case": 1, "customer": 2, "first": 2, "default": 3}


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _new_invite_id() -> str:
    """An invite's id doubles as its token (`P.invite_path`'s docstring):
    holding it is what lets `get_invite`/`delete_invite` find the record
    with no email involved, and once an invite is accepted it names the
    account it became. That makes it a credential, not merely a lookup
    key, so it is drawn from `secrets` rather than `_new_id`'s uuid4 --
    192 bits, comfortably beyond guessing -- and this value must never be
    logged.
    """
    return f"inv-{secrets.token_urlsafe(24)}"


def _natural_key(name: str) -> list:
    """Sort key where digit runs compare as numbers, not as text."""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", name or "")]


def _admits(user, path: str) -> bool:
    """Does *user* admit this path? A None user is unfiltered — see the
    `user=` parameter on the listing methods."""
    if user is None:
        return True
    return may_read(user, path)


class Repository:
    """Domain operations over the seam. Every call carries the caller's auth,
    but datahive no longer decides what this user may see: nSight holds one
    tenant-wide service credential (spec D3), so the store hands back the
    whole tenant regardless of who is asking. For the listing methods, THIS
    CLASS narrows that down, via `_admits`, using the caller's grants."""

    def __init__(self, store: ObjectStore):
        self.store = store
        # material id -> (customer_id, case_id). Resolving one otherwise lists
        # every config object in the tenant, and the material routes are called
        # per chart (spec §5.1). Location only — never the permission answer,
        # which differs per user and is re-checked on every hit.
        #
        # Lifetime is the process: get_repository() memoises one Repository per
        # process, so this cache lives as long as the backend does and is
        # shared by every request — correct for a location that only changes
        # when a material is attached or deleted, both of which go through
        # this class. It is NOT correct across processes: a material deleted by
        # worker A stays in worker B's cache until B tries to read it, at which
        # point the NotFound branch below evicts it. That self-healing path is
        # why a stale entry falls through to a listing rather than returning
        # what it remembered.
        self._material_location: dict[str, tuple[str, str]] = {}

    # -- Asiakas ----------------------------------------------------------

    def create_customer(self, auth: AuthContext, name: str) -> Customer:
        cid = _new_id("cust")
        self._write_json(auth, P.customer_meta_path(cid), {"id": cid, "name": name},
                         [P.LABEL_CUSTOMER])
        return Customer(id=cid, name=name)

    def list_customers(self, auth: AuthContext, user=None) -> list[Customer]:
        """Every customer this user may see.

        Filtered HERE, not by datahive. nSight holds a tenant-wide token, so
        the store returns the whole tenant (spec §5.3). A user granted one case
        sees no customer at all — the customer object is above their grant.
        """
        out = []
        for info in self.store.list(auth, "", labels=[P.LABEL_CUSTOMER]):
            if not _admits(user, info.path):
                continue
            d = self._read_json(auth, info.path)
            out.append(Customer(id=d["id"], name=d.get("name", d["id"]),
                                template_id=d.get("template_id", "")))
        # A customer list is a directory: alphabetical is how you find a name
        # in it. Only the CASE list is newest-first.
        return sorted(out, key=lambda c: _natural_key(c.name))

    def get_customer(self, auth: AuthContext, customer_id: str) -> Customer:
        d = self._read_json(auth, P.customer_meta_path(customer_id))
        return Customer(id=d["id"], name=d.get("name", d["id"]),
                        template_id=d.get("template_id", ""))

    def find_customer(self, auth: AuthContext, customer_id: str,
                      user=None) -> Customer | None:
        """Locate a customer by id, or None if it does not exist or is not
        this user's to see.

        Mirrors `find_case`/`find_material`: existence and grant are answered
        together so a caller can 404 either way without leaking which one it
        was. Unlike those two, the path is addressable directly — no scan
        needed — so a missing object surfaces as `NotFound` from the store.
        """
        path = P.customer_meta_path(customer_id)
        try:
            d = self._read_json(auth, path)
        except (NotFound, ValueError, UnicodeDecodeError):
            return None
        if not _admits(user, path):
            return None
        return Customer(id=d["id"], name=d.get("name", d["id"]),
                        template_id=d.get("template_id", ""))

    def rename_customer(self, auth: AuthContext, customer_id: str, name: str) -> Customer:
        """A metadata write, not a move — which is why ids are in the path and
        names are not."""
        d = self._read_json(auth, P.customer_meta_path(customer_id))
        d["name"] = name
        self._write_json(auth, P.customer_meta_path(customer_id), d, [P.LABEL_CUSTOMER])
        return Customer(id=customer_id, name=name)

    # -- Case -------------------------------------------------------------

    def create_case(self, auth: AuthContext, customer_id: str, name: str) -> Case:
        self.get_customer(auth, customer_id)  # 404 early if it is not ours
        case_id = _new_id("case")
        self._write_json(auth, P.case_meta_path(customer_id, case_id),
                         {"id": case_id, "customer_id": customer_id, "name": name},
                         [P.LABEL_CASE])
        return Case(id=case_id, customer_id=customer_id, name=name)

    def list_cases(self, auth: AuthContext, customer_id: str, user=None) -> list[Case]:
        out = []
        for info in self.store.list(auth, P.customer_prefix(customer_id),
                                    labels=[P.LABEL_CASE]):
            if not _admits(user, info.path):
                continue
            d = self._read_json(auth, info.path)
            out.append(Case(id=d["id"], customer_id=customer_id,
                            name=d.get("name", d["id"]),
                            template_id=d.get("template_id", "")))
        # Newest first. Studies are named by wave — "Brändiseuranta 2025",
        # "…tutkimus 3" — so descending puts the current one at the top, which
        # is the one being worked on. Numbers sort as numbers, or "10" would
        # come before "9".
        return sorted(out, key=lambda c: _natural_key(c.name), reverse=True)

    def get_case(self, auth: AuthContext, customer_id: str, case_id: str) -> Case:
        d = self._read_json(auth, P.case_meta_path(customer_id, case_id))
        return Case(id=d["id"], customer_id=customer_id,
                    name=d.get("name", d["id"]),
                    template_id=d.get("template_id", ""))

    def find_case(self, auth: AuthContext, case_id: str, user=None) -> Case | None:
        """Locate a case by id alone, without knowing its customer.

        The URL surface is still case-rooted (`/cases/{id}/...`) from before the
        hierarchy existed, so the app frequently holds a case id and nothing
        else. One listing answers it: labels select the case metadata objects,
        filtered here by the caller's grants — the store returns the whole
        tenant — and the customer is the first path segment.

        Returns None rather than raising — "no such case, or not yours" is an
        ordinary answer here, and the two must stay indistinguishable.
        """
        for info in self.store.list(auth, "", labels=[P.LABEL_CASE]):
            segments = info.path.split("/")
            if len(segments) >= 2 and segments[1] == case_id:
                if not _admits(user, info.path):
                    return None
                d = self._read_json(auth, info.path)
                return Case(id=d["id"], customer_id=segments[0],
                            name=d.get("name", d["id"]),
                            template_id=d.get("template_id", ""))
        return None

    def rename_case(self, auth: AuthContext, customer_id: str, case_id: str,
                    name: str) -> Case:
        d = self._read_json(auth, P.case_meta_path(customer_id, case_id))
        d["name"] = name
        self._write_json(auth, P.case_meta_path(customer_id, case_id), d, [P.LABEL_CASE])
        return Case(id=case_id, customer_id=customer_id, name=name)

    # -- Aineisto (material) ---------------------------------------------

    def attach_material(self, auth: AuthContext, customer_id: str, case_id: str,
                        name: str, data: bytes) -> Material:
        """Store a .sav under a case. Returns the material.

        Two objects: the bytes, and a sidecar. The bytes cannot carry a name —
        they are an SPSS file — and the sidecar is also where per-material
        curation lives (grouping overrides, word merges, label edits), which is
        rewritten far more often than the .sav it describes.
        """
        mid = _new_id("mat")
        self.store.put(auth, P.material_path(customer_id, case_id, mid), data,
                       "application/octet-stream", labels=[P.LABEL_MATERIAL])
        self._write_json(auth, P.material_config_path(customer_id, case_id, mid),
                         {"id": mid, "case_id": case_id, "customer_id": customer_id,
                          "name": name, "size": len(data), "config": {}},
                         [P.LABEL_CONFIG])
        self._material_location[mid] = (customer_id, case_id)
        return Material(id=mid, case_id=case_id, customer_id=customer_id,
                        name=name, size=len(data))

    def get_material(self, auth: AuthContext, customer_id: str, case_id: str,
                     material_id: str) -> bytes:
        """The raw .sav bytes, byte-exact — nSight re-parses these on every open."""
        return self.store.get(auth, P.material_path(customer_id, case_id, material_id))

    def list_materials(self, auth: AuthContext, customer_id: str,
                       case_id: str, user=None) -> list[Material]:
        """Reads sidecars, not .sav bodies — a listing must never pull megabytes."""
        out = []
        for info in self.store.list(auth, P.materials_prefix(customer_id, case_id),
                                    labels=[P.LABEL_CONFIG]):
            if not _admits(user, info.path):
                continue
            try:
                d = self._read_json(auth, info.path)
            except (NotFound, ValueError, UnicodeDecodeError):
                continue
            out.append(Material(id=d.get("id", ""), case_id=case_id,
                                customer_id=customer_id,
                                name=d.get("name") or d.get("id", ""),
                                size=int(d.get("size") or 0)))
        return sorted(out, key=lambda m: m.name.lower())

    def load_material_config(self, auth: AuthContext, customer_id: str, case_id: str,
                             material_id: str) -> dict:
        """Curation for a material. Absent config is an empty dict, not an error:
        a freshly uploaded material legitimately has none."""
        try:
            return self._read_json(
                auth, P.material_config_path(customer_id, case_id, material_id)
            ).get("config") or {}
        except (NotFound, ValueError, UnicodeDecodeError):
            return {}

    def save_material_config(self, auth: AuthContext, customer_id: str, case_id: str,
                             material_id: str, config: dict) -> None:
        """Replace the curation, preserving the name and size beside it.

        Read-modify-write rather than a blind overwrite: the sidecar holds the
        material's identity too, and losing that would orphan the .sav.
        """
        path = P.material_config_path(customer_id, case_id, material_id)
        try:
            d = self._read_json(auth, path)
        except (NotFound, ValueError, UnicodeDecodeError):
            d = {"id": material_id, "case_id": case_id, "customer_id": customer_id}
        d["config"] = config
        self._write_json(auth, path, d, [P.LABEL_CONFIG])

    def find_material(self, auth: AuthContext, material_id: str,
                      user=None) -> Material | None:
        """Locate a material by id alone, without its customer or case.

        The question/preview/render routes are all keyed by a bare material id
        from before the hierarchy existed. Rather than rewrite every one of them
        and the UI that calls them, this resolves the path the same way
        find_case does — one labelled listing, filtered here by the caller's
        grants, since the store returns the whole tenant.

        Cached by location. A hit still goes through _admits, so warming the
        cache as one user tells another user nothing.
        """
        hit = self._material_location.get(material_id)
        if hit is not None:
            customer_id, case_id = hit
            path = P.material_config_path(customer_id, case_id, material_id)
            if not _admits(user, path):
                return None
            try:
                d = self._read_json(auth, path)
            except (NotFound, ValueError, UnicodeDecodeError):
                # Gone from under us — drop the stale entry and fall through to
                # a full listing rather than reporting a material that is not
                # there.
                self._material_location.pop(material_id, None)
            else:
                return Material(id=material_id, case_id=case_id,
                                customer_id=customer_id,
                                name=d.get("name") or material_id,
                                size=int(d.get("size") or 0))

        for info in self.store.list(auth, "", labels=[P.LABEL_CONFIG]):
            segments = info.path.split("/")
            # {asiakas}/{case}/material/{id}.config
            if len(segments) == 4 and segments[3] == f"{material_id}.config":
                # Remember the location before the permission check, so a user
                # who may not see it does not force the next user to list again.
                self._material_location[material_id] = (segments[0], segments[1])
                if not _admits(user, info.path):
                    return None
                try:
                    d = self._read_json(auth, info.path)
                except (NotFound, ValueError, UnicodeDecodeError):
                    return None
                return Material(id=material_id, case_id=segments[1],
                                customer_id=segments[0],
                                name=d.get("name") or material_id,
                                size=int(d.get("size") or 0))
        # A miss is NOT cached: the id may be attached a moment from now.
        return None

    # -- Raportti ---------------------------------------------------------

    def next_report_name(self, auth: AuthContext, customer_id: str, case_id: str) -> str:
        """"Raportti n", 1-based, per the card.

        Counts existing reports rather than tracking a counter: a stored counter
        would drift the moment a report is deleted outside this code path, and
        the count is one listing call.
        """
        n = len(self.store.list(auth, P.reports_prefix(customer_id, case_id),
                                labels=[P.LABEL_REPORT]))
        return f"Raportti {n + 1}"

    def save_report(self, auth: AuthContext, customer_id: str, case_id: str,
                    report_json: str, report_id: str | None = None) -> ReportRef:
        """Create, or replace in place when *report_id* is given.

        The JSON is stored verbatim — the serde round-trip
        (report_from_json(report_to_json(r)) == r) is an invariant the report
        model is deliberately normalised to preserve.
        """
        rid = report_id or _new_id("rep")
        self.store.put(auth, P.report_path(customer_id, case_id, rid),
                       report_json.encode("utf-8"), _JSON, labels=[P.LABEL_REPORT])
        name = ""
        try:
            name = json.loads(report_json).get("name", "") or ""
        except (ValueError, AttributeError):
            pass
        modified_at = _now()
        # The sidecar is what listings read, so a list never has to fetch a
        # 30 KB report body just to learn its name.
        self._write_json(auth, P.report_meta_path(customer_id, case_id, rid),
                         {"id": rid, "case_id": case_id, "customer_id": customer_id,
                          "name": name, "modified_at": modified_at},
                         [P.LABEL_REPORT_META])
        return ReportRef(id=rid, case_id=case_id, customer_id=customer_id,
                         name=name, modified_at=modified_at)

    def load_report(self, auth: AuthContext, customer_id: str, case_id: str,
                    report_id: str) -> str:
        return self.store.get(
            auth, P.report_path(customer_id, case_id, report_id)
        ).decode("utf-8")

    def list_reports(self, auth: AuthContext, customer_id: str,
                     case_id: str, user=None) -> list[ReportRef]:
        """Newest first — reads sidecars, never report bodies."""
        refs = [
            self._ref_from_meta(auth, info.path)
            for info in self.store.list(auth,
                                        P.reports_prefix(customer_id, case_id),
                                        labels=[P.LABEL_REPORT_META])
            if _admits(user, info.path)
        ]
        return sorted([r for r in refs if r], key=lambda r: r.modified_at, reverse=True)

    def recent_reports(self, auth: AuthContext, limit: int = 10,
                       user=None) -> list[ReportRef]:
        """The most recently modified reports this user may see, across every
        customer.

        No path prefix — this listing spans the whole tenant by design, because
        it is the landing page. "Accessible to this person" used to be the
        store's answer for free; now it is this method's answer, via
        `_admits`, because the store no longer narrows by caller.

        Cost note: this reads one sidecar per accessible report. They are ~100
        bytes each and today's corpus is tens of reports, so it is a fine trade
        for having no denormalised index to drift. If report counts reach the
        thousands, the fix is a per-customer recents index, not a bigger fetch.
        """
        refs = [
            self._ref_from_meta(auth, info.path)
            for info in self.store.list(auth, "", labels=[P.LABEL_REPORT_META])
            if _admits(user, info.path)
        ]
        ordered = sorted([r for r in refs if r],
                         key=lambda r: r.modified_at, reverse=True)
        return ordered[:limit]

    def _ref_from_meta(self, auth: AuthContext, path: str) -> "ReportRef | None":
        """A sidecar may vanish between listing and read (another session
        deleting the report), which is ordinary rather than exceptional."""
        try:
            d = self._read_json(auth, path)
        except (NotFound, ValueError, UnicodeDecodeError):
            return None
        return ReportRef(id=d.get("id", ""), case_id=d.get("case_id", ""),
                         customer_id=d.get("customer_id", ""),
                         name=d.get("name") or d.get("id", ""),
                         modified_at=d.get("modified_at", ""))

    def duplicate_report(self, auth: AuthContext, customer_id: str, case_id: str,
                         report_id: str, new_name: str) -> ReportRef:
        """"Raportti voidaan kopioida uudeksi" — every setting copied, new id."""
        raw = self.load_report(auth, customer_id, case_id, report_id)
        try:
            d = json.loads(raw)
            d["name"] = new_name
            raw = json.dumps(d, ensure_ascii=False)
        except ValueError:
            pass
        return self.save_report(auth, customer_id, case_id, raw)

    # -- Deletion ---------------------------------------------------------

    def _delete_prefix(self, auth: AuthContext, prefix: str) -> int:
        """Remove every object under *prefix*; return how many went.

        ConsentRequired is deliberately NOT caught. datahive gates destructive
        operations behind human approval (floor rule 4), and swallowing that
        here would either silently do nothing or force nSight to auto-approve
        the destruction of somebody's work. The caller surfaces the approval and
        retries; each retry makes progress, because approved objects are gone by
        then.

        The case/customer's own meta object goes last: a retry re-resolves the
        bare id it was called with (find_case/find_customer) by reading that
        exact object, so deleting it before the rest of the prefix is gone
        would turn the next consent retry into a 404 instead of letting the
        cascade continue.
        """
        anchor_labels = {P.LABEL_CASE, P.LABEL_CUSTOMER}
        listing = sorted(
            self.store.list(auth, prefix),
            key=lambda info: bool(anchor_labels & set(info.labels)),
        )
        removed = 0
        for info in listing:
            self.store.delete(auth, info.path)
            removed += 1
        return removed

    def delete_report(self, auth: AuthContext, customer_id: str, case_id: str,
                      report_id: str) -> int:
        """The report, its sidecar and any cached render — a report whose meta
        outlived it would keep appearing in listings and recents."""
        removed = 0
        for path in (P.report_path(customer_id, case_id, report_id),
                     P.report_meta_path(customer_id, case_id, report_id),
                     P.report_render_path(customer_id, case_id, report_id)):
            try:
                self.store.delete(auth, path)
                removed += 1
            except NotFound:
                pass  # a report may never have been rendered
        return removed

    def reports_using_material(self, auth: AuthContext, customer_id: str,
                               case_id: str, material_id: str) -> list[ReportRef]:
        """Reports that were built from this dataset.

        Every report in the tutkimus, in practice: a tutkimus holds one dataset
        and its reports chart that dataset's questions. Listed rather than
        counted so the caller can NAME them — "this also empties 3 reports" is a
        fact someone can act on, "3 reports affected" is not.
        """
        if not self.list_materials(auth, customer_id, case_id):
            return []
        return self.list_reports(auth, customer_id, case_id)

    def delete_material(self, auth: AuthContext, customer_id: str, case_id: str,
                        material_id: str) -> int:
        """A dataset, its curation, and the renders drawn from it.

        The reports are KEPT. A report is a list of questions and how to chart
        them, written by an analyst; the dataset is what those questions were
        asked of. Deleting the data to import a corrected export is the reason
        this exists, and throwing away the report layout with it would make the
        feature useless for its own purpose. The reports go empty until a
        dataset is imported again — which is why the caller warns first.

        Cached renders DO go: a deck on disk drawn from data that no longer
        exists is the one artefact nobody can tell is stale by looking.
        """
        # Deliberately tolerant of what is already gone: datahive gates each
        # delete behind approval, so this method is CALLED AGAIN after consent,
        # and by then the objects it removed on the first pass do not exist.
        # "Does this dataset exist at all" is the caller's question, asked once
        # before it starts — see routes_materials.delete_material.
        self._material_location.pop(material_id, None)
        removed = 0
        for path in (P.material_path(customer_id, case_id, material_id),
                     P.material_config_path(customer_id, case_id, material_id)):
            try:
                self.store.delete(auth, path)
                removed += 1
            except NotFound:
                pass  # a material may carry no curation
        for report in self.list_reports(auth, customer_id, case_id):
            try:
                self.store.delete(
                    auth, P.report_render_path(customer_id, case_id, report.id))
                removed += 1
            except NotFound:
                pass
        return removed

    def delete_case(self, auth: AuthContext, customer_id: str, case_id: str) -> int:
        """The tutkimus and everything in it: materials, curation, reports,
        renders. Cascade rather than refusal, because a tutkimus with no
        material and no reports is not a thing a user would want kept."""
        return self._delete_prefix(auth, P.case_prefix(customer_id, case_id))

    def delete_customer(self, auth: AuthContext, customer_id: str) -> int:
        """The customer and every tutkimus under it."""
        return self._delete_prefix(auth, P.customer_prefix(customer_id))

    # -- Presentation templates -------------------------------------------

    def upload_template(self, auth: AuthContext, customer_id: str, name: str,
                        pptx: bytes, summary: dict | None = None) -> Template:
        """Store a customer's .pptx. *summary* is template_check's findings.

        The summary is recorded rather than recomputed on every read: opening a
        PowerPoint file to answer "what is this template called" would make a
        list of six templates six file parses.
        """
        tid = _new_id("tpl")
        self.store.put(auth, P.template_path(customer_id, tid), pptx, _PPTX,
                       labels=[P.LABEL_TEMPLATE])
        meta = {"id": tid, "customer_id": customer_id, "name": name,
                "size": len(pptx), **(summary or {})}
        self._write_json(auth, P.template_meta_path(customer_id, tid), meta,
                         [P.LABEL_TEMPLATE_META])
        return self._template_from(meta)

    # --- settings -----------------------------------------------------------

    def get_setting(self, auth: AuthContext, key: str, default=None):
        """A stored setting, or *default* when never set or unreadable."""
        try:
            return self._read_json(auth, P.settings_path(key))
        except (NotFound, ValueError, UnicodeDecodeError):
            return default

    def set_setting(self, auth: AuthContext, key: str, value: dict) -> dict:
        self._write_json(auth, P.settings_path(key), value, [P.LABEL_SETTINGS])
        return value

    # --- users and grants -------------------------------------------------
    #
    # Stored in datahive so that attaching a different hive brings the people
    # with it (spec §2). nSight keeps no user list of its own.

    def save_user(self, auth: AuthContext, user: "User") -> "User":
        """Create or replace. An empty id means create."""
        uid = user.id or _new_id("usr")
        self._write_json(auth, P.user_path(uid),
                         {"id": uid, "email": user.email.strip(),
                          "name": user.name, "is_admin": bool(user.is_admin)},
                         [P.LABEL_USER])
        self.set_grants(auth, uid, user.grants)
        return replace(user, id=uid)

    def set_grants(self, auth: AuthContext, user_id: str, grants) -> None:
        self._write_json(auth, P.user_grants_path(user_id),
                         {"grants": [{"scope": g.scope, "mode": g.mode} for g in grants]},
                         [P.LABEL_GRANTS])

    def _grants(self, auth: AuthContext, user_id: str) -> tuple:
        try:
            d = self._read_json(auth, P.user_grants_path(user_id))
        except (NotFound, ValueError, UnicodeDecodeError):
            return ()
        grants = []
        for g in d.get("grants", []):
            if not g.get("scope"):
                continue
            try:
                grants.append(Grant(g["scope"], g.get("mode", "view")))
            except ValueError:
                # A malformed grant row must cost its owner that one grant, not
                # their whole account. Task 1 made Grant construction strict
                # (rejecting empty/trailing-slash/. or .. scopes and invalid
                # modes), so a bad row here is a configuration error. Skip it and
                # let the user load with their valid grants intact.
                continue
        return tuple(grants)

    def get_user(self, auth: AuthContext, user_id: str) -> "User | None":
        try:
            d = self._read_json(auth, P.user_path(user_id))
        except (NotFound, ValueError, UnicodeDecodeError):
            return None
        return User(id=d["id"], email=d.get("email", ""), name=d.get("name", ""),
                    is_admin=bool(d.get("is_admin")), grants=self._grants(auth, d["id"]))

    def list_users(self, auth: AuthContext) -> list:
        out = []
        for info in self.store.list(auth, P.SETTINGS_ROOT + "/", labels=[P.LABEL_USER]):
            user = self.get_user(auth, info.path.rsplit("/", 1)[-1])
            if user is not None:
                out.append(user)
        return sorted(out, key=lambda u: u.email.lower())

    def find_user_by_email(self, auth: AuthContext, email: str) -> "User | None":
        """Sign-in has a verified email and nothing else.

        Case-insensitive: an IdP may return `Maija@Egoiq.com` today and
        `maija@egoiq.com` tomorrow, and they are the same person.
        """
        wanted = (email or "").strip().lower()
        if not wanted:
            # An empty or whitespace-only query must fail safe: it cannot match
            # a user with an empty email (a misconfigured IdP claim or upstream
            # bug). This is the load-bearing path into a user record per spec §4.
            return None
        return next((u for u in self.list_users(auth) if u.email.lower() == wanted), None)

    def delete_user(self, auth: AuthContext, user_id: str) -> None:
        """Delete the user record, their grants, and their password hash if
        they had one (the "passwords" section below calls it "a sibling of
        the user record, like grants" -- it belongs here for the same
        reason). Without this, removing a user left its password hash
        behind forever: unreachable orphaned credential material, since
        ids are never reused, but nothing that should be left lying
        around in datahive either. A path that never existed (no grants
        ever set, no password ever set) is not an error.

        `user_path` is deleted LAST, deliberately. `users.remove_user`
        looks the user up with `get_user` before doing anything, and
        returns early (a no-op) once that lookup comes back empty -- the
        idempotent-under-a-double-click behaviour its own docstring
        promises. In production that guard and this loop both run under
        one already-authorised bearer, so it never matters which path
        goes first. But a caller that has to re-approve each destructive
        delete one at a time (`InMemoryObjectStore`'s consent gate, and
        so every test that drives it to completion by retrying the whole
        `remove_user` call) would, with `user_path` deleted first, see
        `get_user` come back empty on the very next retry and bail out
        before the grants/password paths ever got their own turn --
        orphaning exactly the credential material this method exists to
        clean up. Deleting `user_path` last keeps the user "found" for
        every retry until every sibling path has actually been removed.
        """
        for path in (P.user_grants_path(user_id), P.user_password_path(user_id),
                    P.user_path(user_id)):
            try:
                self.store.delete(auth, path)
            except NotFound:
                pass

    # --- passwords ----------------------------------------------------------
    #
    # A sibling of the user record, like grants (spec: this plan's Task 3).
    # Absent for a user who only ever signed in with Google or Microsoft.

    def set_password(self, auth: AuthContext, user_id: str, password_hash: str) -> None:
        self._write_json(auth, P.user_password_path(user_id),
                         {"hash": password_hash}, [P.LABEL_PASSWORD])

    def get_password_hash(self, auth: AuthContext, user_id: str) -> str | None:
        try:
            d = self._read_json(auth, P.user_password_path(user_id))
        except (NotFound, ValueError, UnicodeDecodeError):
            return None
        return d.get("hash") or None

    # --- per-user workspace state --------------------------------------------
    #
    # spec §8: the material pointer and report timestamps that used to live
    # in web/src/lib/workspace.ts's localStorage. Moved here so attaching a
    # different hive brings a user's UI state with it (spec §2: nSight
    # keeps nothing of its own it cannot rebuild). One JSON object per
    # user, keyed by case inside it -- small, per-user, read/written whole
    # every time a case is opened.

    def get_workspace(self, auth: AuthContext, user_id: str) -> dict:
        try:
            d = self._read_json(auth, P.user_workspace_path(user_id))
        except (NotFound, ValueError, UnicodeDecodeError):
            return {}
        return d if isinstance(d, dict) else {}

    def set_case_workspace(self, auth: AuthContext, user_id: str, case_id: str,
                           state: dict) -> dict:
        """Replace the state for ONE case, leaving every other case's
        entry in this user's workspace untouched."""
        whole = self.get_workspace(auth, user_id)
        whole[case_id] = state
        self._write_json(auth, P.user_workspace_path(user_id), whole, [P.LABEL_WORKSPACE])
        return state

    # --- sessions -------------------------------------------------------------
    #
    # A cookie names a session id; this record decides who that is and whether
    # it still counts (spec §7). `created`/`expires` are set once; `last_seen`
    # moves — see reportbuilder/auth/session.py for the idle/absolute rules
    # that read these three fields.

    def create_session(self, auth: AuthContext, user_id: str,
                       lifetime_seconds: int) -> Session:
        sid = _new_id("sess")
        now = _now()
        expires = (datetime.now(timezone.utc) + timedelta(seconds=lifetime_seconds)) \
            .isoformat(timespec="seconds")
        self._write_json(auth, P.session_path(sid),
                         {"id": sid, "user_id": user_id, "created": now,
                          "last_seen": now, "expires": expires},
                         [P.LABEL_SESSION])
        return Session(id=sid, user_id=user_id, created=now, last_seen=now, expires=expires)

    def get_session(self, auth: AuthContext, session_id: str) -> Session | None:
        """A live session, or None — for an unknown id AND an expired one.

        This is the property `delete_session` leans on to stay safe without
        the delete having to succeed (see its docstring): a session's
        authority comes from being found here, unexpired, never from the
        record having been physically removed. So expiry is enforced on
        every read, not only when something gets around to deleting it.
        """
        try:
            d = self._read_json(auth, P.session_path(session_id))
        except (NotFound, ValueError, UnicodeDecodeError):
            return None
        if d["expires"] <= _now():
            # ISO 8601 timestamps with the same (UTC) offset compare
            # correctly as strings — no parsing needed, and no risk of a
            # naive/aware mismatch.
            return None
        return Session(id=d["id"], user_id=d["user_id"], created=d["created"],
                       last_seen=d["last_seen"], expires=d["expires"])

    def touch_session(self, auth: AuthContext, session_id: str, last_seen: str) -> None:
        session = self.get_session(auth, session_id)
        if session is None:
            return
        self._write_json(auth, P.session_path(session_id),
                         {"id": session.id, "user_id": session.user_id,
                          "created": session.created, "last_seen": last_seen,
                          "expires": session.expires},
                         [P.LABEL_SESSION])

    def delete_session(self, auth: AuthContext, session_id: str) -> None:
        """End a session. Never raises for consent, on purpose.

        Sign-out and the idle/expiry cleanup in `auth/session.py` both call
        this with no human present to answer a consent prompt — nSight runs
        against its own hive under an admin bearer precisely so a destructive
        op like this one does not need one (`scripts/dev-stack.sh`), but the
        in-memory double used in tests still gates every first delete
        unconditionally. Swallowing `ConsentRequired` here, rather than
        weakening that double, is safe only because `get_session` treats an
        expired record as absent: a session this call could not physically
        remove is still unusable the moment it expires, so nothing downstream
        depends on this delete having actually taken effect.
        """
        try:
            self.store.delete(auth, P.session_path(session_id))
        except (NotFound, ConsentRequired):
            pass

    def delete_sessions_for_user(self, auth: AuthContext, user_id: str) -> None:
        """Used when a user is deleted (spec §7: "deleting a user, or their
        session, ends it"). Not wired to `delete_user` in this plan — nothing
        calls `delete_user` over HTTP yet (Plan 1's own note); Plan 3's Users
        screen wires the two together when it adds "revoke"."""
        for info in self.store.list(auth, P.SETTINGS_ROOT + "/", labels=[P.LABEL_SESSION]):
            try:
                d = self._read_json(auth, info.path)
            except (NotFound, ValueError, UnicodeDecodeError):
                continue
            if d.get("user_id") == user_id:
                self.delete_session(auth, d["id"])

    # --- invitations --------------------------------------------------------
    #
    # An admin adds someone by email (spec §6): this record is what
    # "pending"/"accepted" MEANS, and it outlives acceptance so a later
    # revoke can find and remove the user it produced (Invite's docstring).
    # Keyed by the invite's own (unguessable) id rather than by email --
    # see `P.invite_path` -- so a lookup needs only the id, not the email.

    def create_invite(self, auth: AuthContext, email: str, grants,
                      invited_by: str, lifetime_seconds: int) -> Invite:
        iid = _new_invite_id()
        # Microsecond precision, unlike the shared `_now()`: `list_invites`
        # sorts newest-first by this field, and two invites sent by an
        # admin moments apart must not tie at one-second resolution --
        # `expires` keeps `_now()`'s coarser, comparison-only precision
        # since nothing sorts by it.
        now = datetime.now(timezone.utc).isoformat()
        expires = (datetime.now(timezone.utc) + timedelta(seconds=lifetime_seconds)) \
            .isoformat(timespec="seconds")
        normalized = (email or "").strip().lower()
        grant_tuple = tuple(grants)
        self._write_json(auth, P.invite_path(iid),
                         {"id": iid, "email": normalized,
                          "grants": [{"scope": g.scope, "mode": g.mode} for g in grant_tuple],
                          "invited_by": invited_by, "invited_at": now, "expires": expires,
                          "accepted_user_id": None, "accepted_at": None},
                         [P.LABEL_INVITE])
        return Invite(id=iid, email=normalized, grants=grant_tuple,
                      invited_by=invited_by, invited_at=now, expires=expires)

    def _invite_from(self, d: dict) -> Invite:
        grants = []
        for g in d.get("grants", []):
            if not g.get("scope"):
                continue
            try:
                grants.append(Grant(g["scope"], g.get("mode", "view")))
            except ValueError:
                # One malformed grant must cost the invite that one grant,
                # not the whole record -- same reasoning as `_grants` for
                # a user's grants.
                continue
        return Invite(id=d["id"], email=d.get("email", ""), grants=tuple(grants),
                      invited_by=d.get("invited_by", ""), invited_at=d.get("invited_at", ""),
                      expires=d.get("expires", ""),
                      accepted_user_id=d.get("accepted_user_id"),
                      accepted_at=d.get("accepted_at"))

    def get_invite(self, auth: AuthContext, invite_id: str) -> "Invite | None":
        """The record for *invite_id*, or None if it does not exist or is
        unreadable -- never for having expired or already been accepted.

        Unlike `get_session`, this does NOT hide an expired (or accepted)
        invite: an admin's invitations list (Task 6) has to show "expired"
        and "accepted" as statuses, and `revoke_invitation` (Task 5) has to
        find an already-accepted invite by id to revoke it. Expiry only
        changes whether sign-in treats the invite as live -- that check
        lives in `find_pending_invite_by_email`, the read sign-in actually
        uses, the same way `get_session` guards session authority.
        """
        try:
            d = self._read_json(auth, P.invite_path(invite_id))
        except (NotFound, ValueError, UnicodeDecodeError):
            return None
        return self._invite_from(d)

    def list_invites(self, auth: AuthContext) -> list[Invite]:
        """Every invite, newest first -- an admin cares most about what was
        just sent. One unreadable row is skipped, not fatal to the rest,
        the same tolerance `_grants` gives a user's grants."""
        out = []
        for info in self.store.list(auth, P.SETTINGS_ROOT + "/", labels=[P.LABEL_INVITE]):
            invite = self.get_invite(auth, info.path.rsplit("/", 1)[-1])
            if invite is not None:
                out.append(invite)
        return sorted(out, key=lambda i: i.invited_at, reverse=True)

    def find_pending_invite_by_email(self, auth: AuthContext, email: str) -> "Invite | None":
        """The live invitation for *email*, if any: not yet accepted, not
        yet expired. Sign-in has a verified email and nothing else --
        same shape as `find_user_by_email`, and the same
        expiry-reads-as-absent rule `get_session` applies to sessions.
        """
        wanted = (email or "").strip().lower()
        if not wanted:
            return None
        now = _now()
        return next((i for i in self.list_invites(auth)
                    if i.email == wanted and i.accepted_user_id is None and i.expires > now),
                   None)

    def mark_invite_accepted(self, auth: AuthContext, invite_id: str, user_id: str) -> None:
        """Single-use: once `accepted_user_id` is set, the invite can never
        again satisfy `find_pending_invite_by_email`, so it cannot be
        replayed into a second account. The record itself is kept, not
        deleted -- see `Invite`'s docstring."""
        invite = self.get_invite(auth, invite_id)
        if invite is None:
            return
        self._write_json(auth, P.invite_path(invite_id),
                         {"id": invite.id, "email": invite.email,
                          "grants": [{"scope": g.scope, "mode": g.mode} for g in invite.grants],
                          "invited_by": invite.invited_by, "invited_at": invite.invited_at,
                          "expires": invite.expires, "accepted_user_id": user_id,
                          "accepted_at": _now()},
                         [P.LABEL_INVITE])

    def delete_invite(self, auth: AuthContext, invite_id: str) -> None:
        """Revoke. Does NOT swallow `ConsentRequired` -- unlike
        `delete_session`, and deliberately so.

        An admin revoking an invitation is an ATTENDED action: there is a
        human at the other end of the request who can answer a consent
        prompt, the same as `users.remove_user`'s `delete_user` call (see
        its docstring) -- so the gate (floor rule 4) is left to propagate,
        same as every other destructive delete in this codebase.
        `delete_session` swallows `ConsentRequired` only because ITS
        callers -- idle/expiry cleanup and sign-out (`auth/session.py`) --
        run with nobody present to answer one; that swallow is also safe
        only because `get_session` treats an undeleted-but-expired session
        as gone, so a delete that could not physically complete still cost
        the session its authority. An invite has no such fallback (an
        unrevoked invite is a live credential whether or not the delete
        landed), so it does not get the same treatment. Two deletes in
        this file behaving differently is not one of them being wrong --
        it tracks whether anyone is there to grant consent.

        Reaches production only in theory: nSight's own admin bearer
        already carries this authority, so the call just succeeds there
        (`scripts/dev-stack.sh`). An unknown id is a no-op.
        """
        try:
            self.store.delete(auth, P.invite_path(invite_id))
        except NotFound:
            pass

    # --- fonts ------------------------------------------------------------
    #
    # Font FILES live in datahive, not merely on the render host. A host can be
    # replaced or scaled out, and a font that exists only in its filesystem
    # disappears with it — the same mistake as leaving finished decks in /tmp.
    # `sync_fonts` materialises them onto whichever host is running.

    def install_font(self, auth: AuthContext, filename: str, blob: bytes,
                     family: str) -> "FontFile":
        """Store a font and record what family it provides."""
        fid = _new_id("fnt")
        self.store.put(auth, P.font_path(fid), blob, "font/sfnt",
                       labels=[P.LABEL_FONT])
        meta = {"id": fid, "family": family, "filename": filename,
                "size": len(blob)}
        self._write_json(auth, P.font_meta_path(fid), meta, [P.LABEL_FONT_META])
        return FontFile(**meta)

    def list_fonts(self, auth: AuthContext) -> list["FontFile"]:
        out = []
        for info in self.store.list(auth, P.fonts_prefix(),
                                    labels=[P.LABEL_FONT_META]):
            try:
                meta = self._read_json(auth, info.path)
            except (NotFound, ValueError, UnicodeDecodeError):
                continue
            out.append(FontFile(id=meta.get("id", ""), family=meta.get("family", ""),
                                filename=meta.get("filename", ""),
                                size=int(meta.get("size") or 0)))
        return sorted(out, key=lambda f: f.family.lower())

    def get_font_bytes(self, auth: AuthContext, font_id: str) -> bytes:
        return self.store.get(auth, P.font_path(font_id))

    def delete_font(self, auth: AuthContext, font_id: str) -> str:
        """Remove a stored font; returns the family it provided.

        Idempotent per object. A font is two objects and datahive gates each
        one separately, so a delete can stop half-way waiting for approval and
        be retried — at which point the first object is already gone. Treating
        that as "not found" would report failure for a delete that is in fact
        proceeding, so an object that has already gone is simply skipped.
        """
        import contextlib

        try:
            meta = self._read_json(auth, P.font_meta_path(font_id))
        except (NotFound, ValueError, UnicodeDecodeError):
            meta = {}
        found = False
        for path in (P.font_path(font_id), P.font_meta_path(font_id)):
            with contextlib.suppress(NotFound):
                self.store.delete(auth, path)
                found = True
        if not found and not meta:
            raise NotFound(P.font_path(font_id))
        return meta.get("family", "")

    def sync_fonts(self, auth: AuthContext, installer) -> list:
        """Put every stored font onto this host. Returns each install result.

        Called at startup: a freshly started render host has an empty font
        directory, and the fonts an admin installed weeks ago have to be there
        before the first deck is rendered, not after someone notices.
        """
        results = []
        for font in self.list_fonts(auth):
            try:
                blob = self.get_font_bytes(auth, font.id)
            except NotFound:
                continue
            results.append(installer(blob, filename=font.filename,
                                     family=font.family))
        return results

    def record_template_fonts(self, auth: AuthContext, customer_id: str,
                              template_id: str, fonts: list[dict]) -> None:
        """Add a font-availability check to a template's stored summary.

        Lets a template uploaded before the check existed acquire one without
        being re-uploaded. Merges into the meta rather than rewriting it, so a
        concurrent binding change is not clobbered by a font check.
        """
        path = P.template_meta_path(customer_id, template_id)
        meta = self._read_json(auth, path)
        meta["fonts"] = fonts
        self._write_json(auth, path, meta, [P.LABEL_TEMPLATE_META])

    def list_templates(self, auth: AuthContext, customer_id: str) -> list[Template]:
        out = []
        for info in self.store.list(auth, P.templates_prefix(customer_id),
                                    labels=[P.LABEL_TEMPLATE_META]):
            try:
                out.append(self._template_from(self._read_json(auth, info.path)))
            except (NotFound, ValueError, UnicodeDecodeError):
                continue
        return sorted(out, key=lambda t: t.name.lower())

    def get_template_bytes(self, auth: AuthContext, customer_id: str,
                           template_id: str) -> bytes:
        return self.store.get(auth, P.template_path(customer_id, template_id))

    def delete_template(self, auth: AuthContext, customer_id: str,
                        template_id: str) -> int:
        removed = 0
        for path in (P.template_path(customer_id, template_id),
                     P.template_meta_path(customer_id, template_id)):
            try:
                self.store.delete(auth, path)
                removed += 1
            except NotFound:
                pass
        return removed

    def ensure_default_template(self, auth: AuthContext, pptx: bytes) -> None:
        """Seed the house-style default if it is not there yet.

        Written once and left alone: overwriting on every boot would discard a
        deliberately customised default, and the bytes are deterministic anyway.
        """
        try:
            self.store.get(auth, P.default_template_path())
            return
        except NotFound:
            pass
        self.store.put(auth, P.default_template_path(), pptx, _PPTX,
                       labels=[P.LABEL_TEMPLATE])

    def template_bytes_for_report(self, auth: AuthContext, customer_id: str,
                                  case_id: str, report_id: str) -> bytes | None:
        """The .pptx this report should render into, following the chain.

        None means "not available" — a binding pointing at a deleted template,
        or no default seeded — and the caller falls back to a blank deck rather
        than failing a render over styling.
        """
        template_id, _level = self.resolve_template(auth, customer_id, case_id,
                                                    report_id)
        try:
            if template_id:
                return self.get_template_bytes(auth, customer_id, template_id)
            return self.store.get(auth, P.default_template_path())
        except NotFound:
            return None

    @staticmethod
    def _template_from(meta: dict) -> Template:
        return Template(
            id=meta.get("id", ""), customer_id=meta.get("customer_id", ""),
            name=meta.get("name") or meta.get("id", ""),
            size=int(meta.get("size") or 0),
            layout_name=meta.get("layout_name", ""),
            palette=tuple(meta.get("palette") or ()),
            heading_font=meta.get("heading_font", ""),
            body_font=meta.get("body_font", ""),
            fonts=tuple(meta.get("fonts") or ()),
        )

    def set_template(self, auth: AuthContext, template_id: str | None, *,
                     customer_id: str, case_id: str | None = None) -> None:
        """Bind a template to a customer or a tutkimus. None clears the binding.

        Stored on the container's own metadata rather than in a separate table:
        the binding IS a property of the customer or tutkimus, and keeping it
        there means one read to resolve it and nothing to keep in step.
        """
        path = (P.case_meta_path(customer_id, case_id) if case_id
                else P.customer_meta_path(customer_id))
        label = P.LABEL_CASE if case_id else P.LABEL_CUSTOMER
        d = self._read_json(auth, path)
        if template_id:
            d["template_id"] = template_id
        else:
            d.pop("template_id", None)
        self._write_json(auth, path, d, [label])

    def _live_template_ids(self, auth: AuthContext, customer_id: str) -> set[str]:
        """Ids of templates the asiakas still has.

        Resolution checks every binding against this, so deleting a template
        from the asiakas resets whatever pointed at it back to inheriting —
        wherever that binding was. Doing it here rather than by rewriting the
        bindings on delete means nothing can be missed: a report bound to a
        deleted file cannot survive in a document nobody thought to walk.
        """
        try:
            return {t.id for t in self.list_templates(auth, customer_id)}
        except Exception:  # noqa: BLE001 — resolution must not fail on a listing
            return set()

    def resolve_case_template(self, auth: AuthContext, customer_id: str,
                              case_id: str) -> tuple[str, str]:
        """What a tutkimus renders with absent any report-level choice.

        This is the inheritance half of `resolve_template`, split out because
        the tutkimus page has to answer it with no report in hand. Same order,
        lowest wins: the tutkimus's own choice, then its asiakas, then the
        asiakas's first template, then the house default.

        The first-template step is what makes an uploaded pohja take effect
        without anyone binding it: a customer who has exactly one is the common
        case, and having to upload it AND then select it read as the upload not
        having worked.
        """
        live = self._live_template_ids(auth, customer_id)
        for path, level in ((P.case_meta_path(customer_id, case_id), "case"),
                            (P.customer_meta_path(customer_id), "customer")):
            try:
                d = self._read_json(auth, path)
            except (NotFound, ValueError, UnicodeDecodeError):
                continue
            if d.get("template_id") in live:
                return d["template_id"], level
        first = self.list_templates(auth, customer_id)
        if first:
            return first[0].id, "first"
        return "", "default"

    def resolve_template(self, auth: AuthContext, customer_id: str, case_id: str,
                         report_id: str) -> tuple[str, str]:
        """Which template does this report render with, and where did it come from?

        Order, lowest wins: the report's own explicit choice, then the template
        it last rendered with, then its tutkimus, then its customer, then the
        house default.

        The second step is the card's rule that an existing report must not
        change under its author: *"Jo luotujen raporttien pohja ei muutoksessa
        automaattisesti päivity, vaan päivitys pitää erikseen pyytää."* Once a
        report has rendered, the template it used is pinned, so changing the
        customer's template re-styles new reports and leaves delivered ones
        alone. `clear_pinned_template` is the explicit request to move it on.

        Returns (template_id, level) where level is one of
        "report" | "pinned" | "case" | "customer" | "default". An empty
        template_id means the house default.
        """
        live = self._live_template_ids(auth, customer_id)
        try:
            report = json.loads(self.load_report(auth, customer_id, case_id, report_id))
            if report.get("template_ref") in live:
                return report["template_ref"], "report"
        except (NotFound, ValueError, UnicodeDecodeError):
            pass

        pinned, pinned_level = "", ""
        try:
            meta = self._read_json(
                auth, P.report_meta_path(customer_id, case_id, report_id))
            pinned = meta.get("pinned_template") or ""
            if pinned not in live:
                pinned = ""
            # Older pins predate the level being recorded. Treat them as the
            # least specific thing that could have set them, so a deliberate
            # choice still wins rather than being blocked by a pin we cannot
            # place.
            pinned_level = meta.get("pinned_level") or "customer"
        except (NotFound, ValueError, UnicodeDecodeError):
            pass

        inherited, inherited_level = self.resolve_case_template(
            auth, customer_id, case_id)

        # Specificity beats recency. A template set on the TUTKIMUS is a more
        # specific decision than one on the asiakas, so it wins even over a pin
        # — otherwise "lower level overrides upper" would silently stop being
        # true the moment a report had been rendered once.
        #
        # A change at the same or a broader level does NOT win: that is the
        # card's "jo luotujen raporttien pohja ei muutoksessa automaattisesti
        # päivity", and clear_pinned_template is how it is requested.
        if pinned and (not inherited
                       or _SPECIFICITY[inherited_level] >= _SPECIFICITY[pinned_level]):
            return pinned, "pinned"
        if inherited:
            return inherited, inherited_level
        return "", "default"

    def pin_template(self, auth: AuthContext, customer_id: str, case_id: str,
                     report_id: str, template_id: str, level: str = "customer") -> None:
        """Record what a report rendered with, so a later change upstream does
        not silently restyle it."""
        path = P.report_meta_path(customer_id, case_id, report_id)
        try:
            d = self._read_json(auth, path)
        except (NotFound, ValueError, UnicodeDecodeError):
            d = {"id": report_id, "case_id": case_id, "customer_id": customer_id}
        d["pinned_template"] = template_id
        # The level matters as much as the id: it is what lets a later, MORE
        # specific choice override the pin while a broader one does not.
        d["pinned_level"] = level
        self._write_json(auth, path, d, [P.LABEL_REPORT_META])

    def clear_pinned_template(self, auth: AuthContext, customer_id: str,
                              case_id: str, report_id: str) -> None:
        """The explicit "update this report to the current template" request."""
        path = P.report_meta_path(customer_id, case_id, report_id)
        try:
            d = self._read_json(auth, path)
        except (NotFound, ValueError, UnicodeDecodeError):
            return
        d.pop("pinned_template", None)
        d.pop("pinned_level", None)
        self._write_json(auth, path, d, [P.LABEL_REPORT_META])

    # -- Rendered deck (a cache, in the store) ----------------------------

    def render_key(self, auth: AuthContext, customer_id: str, case_id: str,
                   report_id: str, material_id: str) -> str:
        """Fingerprint of everything a render depends on.

        Not just the report: orchestrate_render builds the question model from
        the material AND the report's grouping, and the material's curation
        (word merges, label overrides) changes the charts. A cache keyed on the
        report alone would serve a deck that silently disagrees with the data.

        The material bytes are excluded deliberately — a re-upload mints a new
        material id, so identity already covers them.

        Host rendering settings count too: a font stand-in changes what the deck
        LOOKS like without changing the report, so a deck stored before the
        change must not be handed back after it.
        """
        from reportbuilder.render.fonts import rendering_fingerprint

        h = hashlib.sha256()
        for part in (
            self.load_report(auth, customer_id, case_id, report_id),
            json.dumps(self.load_material_config(auth, customer_id, case_id,
                                                 material_id), sort_keys=True),
            material_id,
            rendering_fingerprint(),
        ):
            h.update(part.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def save_render(self, auth: AuthContext, customer_id: str, case_id: str,
                    report_id: str, pptx: bytes, key: str) -> None:
        """Store a rendered deck and stamp the key it was rendered from."""
        self.store.put(auth, P.report_render_path(customer_id, case_id, report_id),
                       pptx, _PPTX, labels=[P.LABEL_RENDER])
        meta_path = P.report_meta_path(customer_id, case_id, report_id)
        try:
            d = self._read_json(auth, meta_path)
        except (NotFound, ValueError, UnicodeDecodeError):
            d = {"id": report_id, "case_id": case_id, "customer_id": customer_id}
        d["render_key"] = key
        self._write_json(auth, meta_path, d, [P.LABEL_REPORT_META])

    def load_render(self, auth: AuthContext, customer_id: str, case_id: str,
                    report_id: str, key: str) -> bytes | None:
        """The stored deck, or None when it is missing or stale.

        Returning None for stale rather than serving it is the whole point: a
        deck that no longer matches its data is worse than no deck, because
        nobody can tell by looking.
        """
        try:
            d = self._read_json(auth, P.report_meta_path(customer_id, case_id, report_id))
        except (NotFound, ValueError, UnicodeDecodeError):
            return None
        if d.get("render_key") != key:
            return None
        try:
            return self.store.get(
                auth, P.report_render_path(customer_id, case_id, report_id))
        except NotFound:
            return None

    # -- helpers ----------------------------------------------------------

    def _write_json(self, auth: AuthContext, path: str, payload: dict,
                    labels: Sequence[str]) -> None:
        self.store.put(auth, path,
                       json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       _JSON, labels=labels)

    def _read_json(self, auth: AuthContext, path: str) -> dict:
        return json.loads(self.store.get(auth, path).decode("utf-8"))
