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

from reportbuilder.auth.permissions import may_write
from reportbuilder.store.repository import Repository, _now
from reportbuilder.store.seam import AuthContext, NotFound


class MaterialNotFound(KeyError):
    """A flat material id that resolves to nothing this caller may read."""


def is_deliverable(ref) -> bool:
    """Whether a report is something finished rather than work in progress.

    "A deck has been produced for it", not "the stored deck is current". The
    stricter fact is what the Generated badge and the download button read, and
    a save clears it on purpose — so gating a viewer on it would mean a client
    lost sight of a deck already delivered to them the moment an analyst touched
    a title. Editing does not un-deliver what was delivered.
    """
    return bool(getattr(ref, "has_render", False)
                or getattr(ref, "rendered", False))


def deliverables_only(user, refs):
    """The reports `user` may be SHOWN, from refs they may READ.

    A view-only grant is the client's grant: they see finished work, not the
    half-built state of it. `user=None` is an internal caller — render, export,
    backup, the AI passes — with no request behind it, and sees everything.

    One rule in one place, because it was three: the report list applied it, and
    the study card's "3 drafts" counter, the recent-reports landing page and the
    material's usage list did not — so a client was told about work they then
    could not open, by name and by count.
    """
    if user is None:
        return list(refs)
    return [r for r in refs
            if may_write(user, f"{r.customer_id}/{r.case_id}") or is_deliverable(r)]


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

    def _may_edit(self, k) -> bool:
        """Whether this caller builds reports in this case, or only receives
        them. `user=None` is an internal caller with no request behind it."""
        return self.user is None or may_write(self.user, f"{k.customer_id}/{k.id}")

    def _finished(self, ref) -> bool:
        return is_deliverable(ref)

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

    # -- classifying variables the analysts chose themselves ---------------

    #: Where the marks live inside a material's curation config.
    MARKED_CLASSIFIERS_KEY = "marked_classifiers"

    def marked_classifiers(self, material_id: str) -> list[str]:
        """Variable names somebody marked as classifiers for THIS dataset.

        Per material, because the data is what a variable means: the same name in
        next year's wave may be a different question, and a mark that followed
        the name would quietly mis-describe it (P-C-12, agreed 2026-08-24).
        """
        try:
            m = self._material(material_id)
        except MaterialNotFound:
            return []
        cfg = self.repo.load_material_config(self.auth, m.customer_id, m.case_id, m.id)
        names = cfg.get(self.MARKED_CLASSIFIERS_KEY) or []
        return [str(n) for n in names if isinstance(n, str)]

    def set_marked_classifier(self, material_id: str, name: str,
                              marked: bool) -> list[str]:
        """Mark or unmark one variable; returns the full list afterwards.

        Read-modify-write on the material's config, which holds the groupings and
        label edits too — a blind overwrite would drop them.
        """
        m = self._material(material_id)
        result: list[str] = []

        def mark(cfg: dict) -> dict:
            current = [str(n) for n in (cfg.get(self.MARKED_CLASSIFIERS_KEY) or [])
                       if isinstance(n, str)]
            if marked and name not in current:
                current.append(name)
            elif not marked and name in current:
                current.remove(name)
            cfg[self.MARKED_CLASSIFIERS_KEY] = current
            result[:] = current
            return cfg

        # Through update_material_config, so a rename or a word merge happening
        # at the same time is not thrown away — all three edit the same object.
        self.repo.update_material_config(self.auth, m.customer_id, m.case_id, m.id,
                                         mark)
        return result

    def update_material_config(self, material_id: str, mutate) -> dict:
        """Read-modify-write this material's curation, serialised against the
        other editors of it. See Repository.update_material_config."""
        m = self._material(material_id)
        return self.repo.update_material_config(self.auth, m.customer_id, m.case_id,
                                                m.id, mutate)

    # -- sensitive terms: what must never reach an LLM ---------------------

    #: Where the accepted terms live inside a material's curation config.
    SENSITIVE_TERMS_KEY = "sensitive_terms"

    def sensitive_terms(self, material_id: str) -> dict:
        """This material's accepted sensitive terms, and when they were accepted.

        ``{"accepted": [...], "accepted_at": "...", "accepted_by": "..."}`` —
        or ``{"accepted": None}`` when nobody has reviewed them yet, which is
        what the report-creation gate refuses on. An empty LIST is a real
        answer ("I looked; there are none"); ``None`` means "not looked at".
        """
        try:
            m = self._material(material_id)
        except MaterialNotFound:
            return {"accepted": None}
        cfg = self.repo.load_material_config(self.auth, m.customer_id, m.case_id, m.id)
        stored = cfg.get(self.SENSITIVE_TERMS_KEY)
        if not isinstance(stored, dict):
            return {"accepted": None}
        terms = stored.get("accepted")
        return {
            "accepted": [str(t) for t in terms] if isinstance(terms, list) else None,
            "accepted_at": stored.get("accepted_at", ""),
            "accepted_by": stored.get("accepted_by", ""),
        }

    def accept_sensitive_terms(self, material_id: str, terms: list[str]) -> dict:
        """Record the terms an analyst confirmed, with who and when.

        Who and when are not decoration: this list is the thing that gets
        registered with datahive and decides what is masked before any text
        reaches a model. If a name later turns out to have leaked, the first
        question is who accepted the list that omitted it.
        """
        m = self._material(material_id)
        cleaned = [t.strip() for t in terms if isinstance(t, str) and t.strip()]
        # Longest first: "Esperi Care Oy" must be substituted before "Esperi",
        # or the shorter match leaves " Care Oy" stranded beside a surrogate.
        cleaned = sorted(dict.fromkeys(cleaned), key=lambda t: (-len(t), t.lower()))
        record = {
            "accepted": cleaned,
            "accepted_at": _now(),
            "accepted_by": (getattr(self.user, "name", "")
                            or getattr(self.user, "email", "")),
        }

        def apply(cfg: dict) -> dict:
            cfg[self.SENSITIVE_TERMS_KEY] = record
            return cfg

        self.repo.update_material_config(self.auth, m.customer_id, m.case_id, m.id,
                                         apply)
        return record

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
        # A view-only grant is the CLIENT's grant. Handing them the working
        # state of a deck nobody has finished shows them half-built slides,
        # wrong numbers mid-edit and titles still being written, and invites
        # comment on all of it. They see it when it is rendered.
        if not self._may_edit(k):
            ref = next((r for r in self.repo.list_reports(
                self.auth, k.customer_id, k.id, user=self.user)
                if r.id == report_doc_id), None)
            if ref is not None and not self._finished(ref):
                raise NotFound(f"Report '{report_doc_id}' not found")
        return self.repo.load_report(self.auth, k.customer_id, k.id, report_doc_id)

    def save_report(self, case_id: str, report_id: str | None, report_json: str,
                    readable: str = "",
                    base_version: int | None = None) -> tuple[str, int]:
        """Returns (report_id, new_version). See Repository.save_report for what
        `base_version` refuses."""
        k = self._case(case_id)
        ref = self.repo.save_report(
            self.auth, k.customer_id, k.id, report_json, report_id=report_id,
            modified_by=getattr(self.user, "name", "") or getattr(self.user, "email", ""),
            base_version=base_version,
        )
        return ref.id, ref.version

    def report_version(self, case_id: str, report_id: str) -> int:
        """The version a caller is about to edit from, or 0 if unknown."""
        k = self._case(case_id)
        ref = next((r for r in self.repo.list_reports(self.auth, k.customer_id, k.id,
                                                      user=self.user)
                    if r.id == report_id), None)
        return ref.version if ref is not None else 0

    def list_reports(self, case_id: str) -> list[dict]:
        k = self._case(case_id)
        # Everything the list needs, from sidecars only — no report bodies.
        # The case page used to fetch each report in full just to count its
        # charts, which is why it was slow; "edited by X, 2h ago" answers a more
        # useful question and rides along on a read the listing already does.
        locks = self.repo.report_locks(self.auth, k.customer_id, k.id)
        me = getattr(self.user, "id", "")
        may_edit = self._may_edit(k)
        out = []
        for r in self.repo.list_reports(self.auth, k.customer_id, k.id, user=self.user):
            if not may_edit and not self._finished(r):
                continue    # see load_report
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
                    tab_id: str = "",
                    session_id: str = "") -> tuple[bool, dict]:
        k = self._case(case_id)
        return self.repo.lock_report(
            self.auth, k.customer_id, k.id, report_id,
            getattr(self.user, "id", ""),
            getattr(self.user, "name", "") or getattr(self.user, "email", ""),
            tab_id=tab_id, session_id=session_id)

    def unlock_report(self, case_id: str, report_id: str, tab_id: str = "") -> bool:
        k = self._case(case_id)
        return self.repo.unlock_report(self.auth, k.customer_id, k.id, report_id,
                                       getattr(self.user, "id", ""), tab_id=tab_id)

    def report_locks(self, case_id: str) -> dict[str, dict]:
        """Every live editing lock in this case, keyed by report id."""
        k = self._case(case_id)
        return self.repo.report_locks(self.auth, k.customer_id, k.id)

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
                for r in deliverables_only(self.user, self.repo.reports_using_material(
                    self.auth, k.customer_id, k.id, material_id))]

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
