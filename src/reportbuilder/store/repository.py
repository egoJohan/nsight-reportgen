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

import json
import uuid
from dataclasses import dataclass
from typing import Sequence

from reportbuilder.store import paths as P
from reportbuilder.store.seam import AuthContext, NotFound, ObjectStore

_JSON = "application/json"


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
class ReportRef:
    id: str
    case_id: str
    customer_id: str
    name: str


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

    def rename_case(self, auth: AuthContext, customer_id: str, case_id: str,
                    name: str) -> Case:
        d = self._read_json(auth, P.case_meta_path(customer_id, case_id))
        d["name"] = name
        self._write_json(auth, P.case_meta_path(customer_id, case_id), d, [P.LABEL_CASE])
        return Case(id=case_id, customer_id=customer_id, name=name)

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
        path = P.report_path(customer_id, case_id, rid)
        self.store.put(auth, path, report_json.encode("utf-8"), _JSON,
                       labels=[P.LABEL_REPORT])
        name = ""
        try:
            name = json.loads(report_json).get("name", "")
        except (ValueError, AttributeError):
            pass
        return ReportRef(id=rid, case_id=case_id, customer_id=customer_id, name=name)

    def load_report(self, auth: AuthContext, customer_id: str, case_id: str,
                    report_id: str) -> str:
        return self.store.get(
            auth, P.report_path(customer_id, case_id, report_id)
        ).decode("utf-8")

    def list_reports(self, auth: AuthContext, customer_id: str,
                     case_id: str) -> list[ReportRef]:
        """Names come from each report's own JSON.

        That means one fetch per report instead of a metadata sidecar. A sidecar
        would halve the reads but double every write and add a second thing to
        keep consistent; at a handful of reports per case the fetch is cheaper
        than the drift.
        """
        out = []
        for info in self.store.list(auth, P.reports_prefix(customer_id, case_id),
                                    labels=[P.LABEL_REPORT]):
            rid = info.path.rsplit("/", 1)[-1]
            name = rid
            try:
                name = json.loads(self.store.get(auth, info.path).decode("utf-8")
                                  ).get("name") or rid
            except (ValueError, UnicodeDecodeError, NotFound):
                pass
            out.append(ReportRef(id=rid, case_id=case_id, customer_id=customer_id,
                                 name=name))
        return sorted(out, key=lambda r: r.name.lower())

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

    # -- helpers ----------------------------------------------------------

    def _write_json(self, auth: AuthContext, path: str, payload: dict,
                    labels: Sequence[str]) -> None:
        self.store.put(auth, path,
                       json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       _JSON, labels=labels)

    def _read_json(self, auth: AuthContext, path: str) -> dict:
        return json.loads(self.store.get(auth, path).decode("utf-8"))
