"""The legacy client surface, backed by the repository (and so by datahive).

Twenty-odd routes — questions, variables, preview, render, AI, chat — are keyed
by a bare `material_id` or `case_id` from before the hierarchy existed, and all
of them reach storage through a `client` object with this shape. Rewriting every
one of them at once would be a large, untestable change; giving that shape a new
backing is a small one.

So this adapter speaks the old vocabulary and resolves each flat id to its path
(`find_material` / `find_case`), which is exactly what those lookups were built
for. The legacy JSON store stops being read the moment `get_client` returns this
instead — no data is deleted, it simply goes unreferenced.

This is scaffolding with a purpose, not a permanent layer: as each route is
rewritten to take (customer, case) directly, its method here loses its last
caller and goes. When the file is empty, the migration is done.
"""
from __future__ import annotations

from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, NotFound


class MaterialNotFound(KeyError):
    """A flat material id that resolves to nothing this caller may read."""


class RepositoryClient:
    """Flat-id façade over the hierarchy. One per request — it carries the
    caller's auth AND their grants, so it must never be shared between
    requests. `user=None` is unfiltered, for callers with no request behind
    them."""

    def __init__(self, repo: Repository, auth: AuthContext, user=None):
        self.repo = repo
        self.auth = auth
        self.user = user

    # -- resolution -------------------------------------------------------

    def _material(self, material_id: str):
        m = self.repo.find_material(self.auth, material_id, user=self.user)
        if m is None:
            raise MaterialNotFound(material_id)
        return m

    def _case(self, case_id: str):
        k = self.repo.find_case(self.auth, case_id, user=self.user)
        if k is None:
            raise KeyError(case_id)
        return k

    # -- material ---------------------------------------------------------

    def attach_material(self, case_id: str, name: str, sav_bytes: bytes,
                        codebook_summary: str = "") -> str:
        """Attach a .sav to a tutkimus; return the material id.

        The legacy signature is case-rooted, so the customer is resolved here.
        `codebook_summary` is accepted and ignored: nSight parses the .sav in
        process, so nothing downstream reads it, and the legacy caller still
        passes it.
        """
        k = self._case(case_id)
        return self.repo.attach_material(self.auth, k.customer_id, k.id,
                                         name, sav_bytes).id

    def get_material(self, material_id: str) -> bytes:
        m = self._material(material_id)
        return self.repo.get_material(self.auth, m.customer_id, m.case_id, m.id)

    def list_materials(self, case_id: str) -> list[dict]:
        k = self._case(case_id)
        return [{"material_id": m.id, "name": m.name}
                for m in self.repo.list_materials(self.auth, k.customer_id, k.id,
                                                  user=self.user)]

    def load_material_config(self, material_id: str) -> str | None:
        """Returns JSON TEXT, not a dict: the legacy callers parse it themselves,
        and model_loader tolerates malformed input by design."""
        import json
        try:
            m = self._material(material_id)
        except MaterialNotFound:
            return None
        cfg = self.repo.load_material_config(self.auth, m.customer_id, m.case_id, m.id)
        return json.dumps(cfg) if cfg else None

    def save_material_config(self, material_id: str, config_json: str) -> None:
        import json
        m = self._material(material_id)
        try:
            cfg = json.loads(config_json) if config_json else {}
        except ValueError:
            cfg = {}
        self.repo.save_material_config(self.auth, m.customer_id, m.case_id, m.id, cfg)

    # -- report -----------------------------------------------------------

    def load_report(self, case_id: str, report_doc_id: str) -> str:
        k = self._case(case_id)
        return self.repo.load_report(self.auth, k.customer_id, k.id, report_doc_id)

    def save_report(self, case_id: str, report_id: str | None, report_json: str,
                    readable: str = "") -> str:
        k = self._case(case_id)
        return self.repo.save_report(
            self.auth, k.customer_id, k.id, report_json, report_id=report_id,
            modified_by=getattr(self.user, "name", "") or getattr(self.user, "email", "")
        ).id

    def list_reports(self, case_id: str) -> list[dict]:
        k = self._case(case_id)
        # Everything the list needs, from sidecars only — no report bodies.
        # The case page used to fetch each report in full just to count its
        # charts, which is why it was slow; "edited by X, 2h ago" answers a more
        # useful question and rides along on a read the listing already does.
        locks = self.repo.report_locks(self.auth, k.customer_id, k.id)
        me = getattr(self.user, "id", "")
        out = []
        for r in self.repo.list_reports(self.auth, k.customer_id, k.id, user=self.user):
            lock = locks.get(r.id)
            out.append({
                "report_id": r.id, "name": r.name,
                "rendered": r.rendered, "rendered_at": r.rendered_at,
                "modified_at": r.modified_at, "modified_by": r.modified_by,
                # Who has it open, and whether that is you — a report you left
                # open in another tab must not look barred to you.
                "locked_by": (lock or {}).get("user_id", ""),
                "locked_by_name": (lock or {}).get("user_name", ""),
                "locked_since": (lock or {}).get("acquired_at", ""),
                "locked_by_me": bool(lock and lock.get("user_id") == me),
            })
        return out

    # -- editing locks ----------------------------------------------------

    def lock_report(self, case_id: str, report_id: str,
                    tab_id: str = "") -> tuple[bool, dict]:
        k = self._case(case_id)
        return self.repo.lock_report(
            self.auth, k.customer_id, k.id, report_id,
            getattr(self.user, "id", ""),
            getattr(self.user, "name", "") or getattr(self.user, "email", ""),
            tab_id=tab_id)

    def unlock_report(self, case_id: str, report_id: str, tab_id: str = "") -> bool:
        k = self._case(case_id)
        return self.repo.unlock_report(self.auth, k.customer_id, k.id, report_id,
                                       getattr(self.user, "id", ""), tab_id=tab_id)

    def report_lock(self, case_id: str, report_id: str) -> dict | None:
        k = self._case(case_id)
        return self.repo._lock_state(self.auth, k.customer_id, k.id, report_id)

    def delete_report(self, case_id: str, report_doc_id: str) -> None:
        k = self._case(case_id)
        self.repo.delete_report(self.auth, k.customer_id, k.id, report_doc_id)

    # -- case -------------------------------------------------------------

    def list_cases(self) -> list[dict]:
        """Every tutkimus the caller may see, across customers — the flat shape
        the old routes expect."""
        out = []
        for c in self.repo.list_customers(self.auth, user=self.user):
            out += [{"id": k.id, "name": k.name}
                    for k in self.repo.list_cases(self.auth, c.id, user=self.user)]
        return out

    def reports_using_material(self, case_id: str, material_id: str) -> list[dict]:
        k = self._case(case_id)
        return [{"report_id": r.id, "name": r.name}
                for r in self.repo.reports_using_material(
                    self.auth, k.customer_id, k.id, material_id)]

    def delete_material(self, case_id: str, material_id: str) -> int:
        """Delete a dataset. ConsentRequired propagates, as for a case."""
        k = self._case(case_id)
        return self.repo.delete_material(self.auth, k.customer_id, k.id, material_id)

    def delete_case(self, case_id: str) -> int:
        """Delete a tutkimus and everything under it.

        ConsentRequired is allowed to propagate: datahive gates destructive
        operations behind explicit approval, and catching it here would either
        silently delete nothing or auto-approve destroying an analyst's work.
        The route turns it into a response the UI can act on.
        """
        k = self._case(case_id)
        return self.repo.delete_case(self.auth, k.customer_id, k.id)

    def rename_case(self, case_id: str, name: str) -> None:
        k = self._case(case_id)
        self.repo.rename_case(self.auth, k.customer_id, k.id, name)
