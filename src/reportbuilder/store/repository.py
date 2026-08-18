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
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from reportbuilder.store import paths as P
from reportbuilder.store.seam import AuthContext, NotFound, ObjectStore

_JSON = "application/json"
_PPTX = ("application/vnd.openxmlformats-officedocument.presentationml.presentation")


@dataclass(frozen=True)
class Customer:
    id: str
    name: str


@dataclass(frozen=True)
class Case:
    id: str
    customer_id: str
    name: str


@dataclass(frozen=True)
class Material:
    id: str
    case_id: str
    customer_id: str
    name: str
    size: int = 0


@dataclass(frozen=True)
class ReportRef:
    id: str
    case_id: str
    customer_id: str
    name: str
    modified_at: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Repository:
    """Domain operations over the seam. Every call carries the caller's auth,
    so datahive decides what this user may see — never this class."""

    def __init__(self, store: ObjectStore):
        self.store = store

    # -- Asiakas ----------------------------------------------------------

    def create_customer(self, auth: AuthContext, name: str) -> Customer:
        cid = _new_id("cust")
        self._write_json(auth, P.customer_meta_path(cid), {"id": cid, "name": name},
                         [P.LABEL_CUSTOMER])
        return Customer(id=cid, name=name)

    def list_customers(self, auth: AuthContext) -> list[Customer]:
        """Every customer this caller may see.

        No path prefix — the label alone selects them, and datahive has already
        filtered the listing to admitted paths. A caller granted one case sees
        that case's customer and no other.
        """
        out = []
        for info in self.store.list(auth, "", labels=[P.LABEL_CUSTOMER]):
            d = self._read_json(auth, info.path)
            out.append(Customer(id=d["id"], name=d.get("name", d["id"])))
        return sorted(out, key=lambda c: c.name.lower())

    def get_customer(self, auth: AuthContext, customer_id: str) -> Customer:
        d = self._read_json(auth, P.customer_meta_path(customer_id))
        return Customer(id=d["id"], name=d.get("name", d["id"]))

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

    def list_cases(self, auth: AuthContext, customer_id: str) -> list[Case]:
        out = []
        for info in self.store.list(auth, P.customer_prefix(customer_id),
                                    labels=[P.LABEL_CASE]):
            d = self._read_json(auth, info.path)
            out.append(Case(id=d["id"], customer_id=customer_id,
                            name=d.get("name", d["id"])))
        return sorted(out, key=lambda c: c.name.lower())

    def get_case(self, auth: AuthContext, customer_id: str, case_id: str) -> Case:
        d = self._read_json(auth, P.case_meta_path(customer_id, case_id))
        return Case(id=d["id"], customer_id=customer_id, name=d.get("name", d["id"]))

    def find_case(self, auth: AuthContext, case_id: str) -> Case | None:
        """Locate a case by id alone, without knowing its customer.

        The URL surface is still case-rooted (`/cases/{id}/...`) from before the
        hierarchy existed, so the app frequently holds a case id and nothing
        else. One listing answers it: labels select the case metadata objects,
        the store has already restricted them to what this caller may read, and
        the customer is the first path segment.

        Returns None rather than raising — "no such case, or not yours" is an
        ordinary answer here, and the two must stay indistinguishable.
        """
        for info in self.store.list(auth, "", labels=[P.LABEL_CASE]):
            segments = info.path.split("/")
            if len(segments) >= 2 and segments[1] == case_id:
                d = self._read_json(auth, info.path)
                return Case(id=d["id"], customer_id=segments[0],
                            name=d.get("name", d["id"]))
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
        return Material(id=mid, case_id=case_id, customer_id=customer_id,
                        name=name, size=len(data))

    def get_material(self, auth: AuthContext, customer_id: str, case_id: str,
                     material_id: str) -> bytes:
        """The raw .sav bytes, byte-exact — nSight re-parses these on every open."""
        return self.store.get(auth, P.material_path(customer_id, case_id, material_id))

    def list_materials(self, auth: AuthContext, customer_id: str,
                       case_id: str) -> list[Material]:
        """Reads sidecars, not .sav bodies — a listing must never pull megabytes."""
        out = []
        for info in self.store.list(auth, P.materials_prefix(customer_id, case_id),
                                    labels=[P.LABEL_CONFIG]):
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

    def find_material(self, auth: AuthContext, material_id: str) -> Material | None:
        """Locate a material by id alone, without its customer or case.

        The question/preview/render routes are all keyed by a bare material id
        from before the hierarchy existed. Rather than rewrite every one of them
        and the UI that calls them, this resolves the path the same way
        find_case does — one labelled listing, already permission-filtered.
        """
        for info in self.store.list(auth, "", labels=[P.LABEL_CONFIG]):
            segments = info.path.split("/")
            # {asiakas}/{case}/material/{id}.config
            if len(segments) == 4 and segments[3] == f"{material_id}.config":
                try:
                    d = self._read_json(auth, info.path)
                except (NotFound, ValueError, UnicodeDecodeError):
                    return None
                return Material(id=material_id, case_id=segments[1],
                                customer_id=segments[0],
                                name=d.get("name") or material_id,
                                size=int(d.get("size") or 0))
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
                     case_id: str) -> list[ReportRef]:
        """Newest first — reads sidecars, never report bodies."""
        refs = [
            self._ref_from_meta(auth, info.path)
            for info in self.store.list(auth,
                                        P.reports_prefix(customer_id, case_id),
                                        labels=[P.LABEL_REPORT_META])
        ]
        return sorted([r for r in refs if r], key=lambda r: r.modified_at, reverse=True)

    def recent_reports(self, auth: AuthContext, limit: int = 10) -> list[ReportRef]:
        """The caller's most recently modified reports, across every customer.

        No path prefix: the listing is already restricted to paths this caller
        may see, so "accessible to this person" is the store's answer rather
        than a filter applied here.

        Cost note: this reads one sidecar per accessible report. They are ~100
        bytes each and today's corpus is tens of reports, so it is a fine trade
        for having no denormalised index to drift. If report counts reach the
        thousands, the fix is a per-customer recents index, not a bigger fetch.
        """
        refs = [
            self._ref_from_meta(auth, info.path)
            for info in self.store.list(auth, "", labels=[P.LABEL_REPORT_META])
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
        """
        h = hashlib.sha256()
        for part in (
            self.load_report(auth, customer_id, case_id, report_id),
            json.dumps(self.load_material_config(auth, customer_id, case_id,
                                                 material_id), sort_keys=True),
            material_id,
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
