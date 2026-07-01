"""Backfill case links for demo-store reports saved before case-tagging.

Reports created before report→case tagging exist in ``reports.json`` with no case
link (the old ``save_report`` ignored ``case_id``), so they can't be listed per
case. This infers the link from each report's ``question_ref``s → the material
that has those qids → that material's case (from ``material_meta``).

Best-effort and non-destructive: it only ADDS links to ``report_meta``, never
deletes a report. A report whose refs uniquely resolve to one case is linked;
refs spanning several cases are flagged ``ambiguous``; refs matching no current
material are ``unmatched``. Re-runnable (already-tagged reports are skipped).

Run against a demo store dir (stop the backend first to avoid racing live writes):

    python -m reportbuilder.store.report_migration [STORE_DIR]

STORE_DIR defaults to $NSIGHT_DEMO_DIR, else <cwd>/work/demo-store.
"""
from __future__ import annotations

import json
import os
import tempfile

from reportbuilder.ingest.multi_group import enrich_model
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.store.memory_client import InMemoryDataHiveClient


def infer_case(refs: set[str], materials: dict[str, tuple[str | None, set[str]]]):
    """Infer the case for a report's question_refs.

    ``materials`` maps material_id -> (case_id, qid_set). A material matches when
    it contains ALL of ``refs``. Returns (case_id | None, reason) where reason is
    ``"linked"`` (matches resolve to exactly one case), ``"ambiguous"`` (matches
    span several cases), or ``"unmatched"`` (no match, or no refs to match on).
    """
    if not refs:
        return None, "unmatched"
    matched_cases = {
        case_id
        for (case_id, qids) in materials.values()
        if case_id is not None and refs <= qids
    }
    if len(matched_cases) == 1:
        return next(iter(matched_cases)), "linked"
    if len(matched_cases) > 1:
        return None, "ambiguous"
    return None, "unmatched"


def _load_material_index(client) -> dict[str, tuple[str | None, set[str]]]:
    """Build {material_id: (case_id, qid_set)} by reading each material's model."""
    index: dict[str, tuple[str | None, set[str]]] = {}
    for mid, meta in dict(client._material_meta).items():
        try:
            raw = client.get_material(mid)
            with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
                tmp.write(raw)
                path = tmp.name
            try:
                _df, model = read_sav(path)
            finally:
                os.unlink(path)
            model = enrich_model(model)
            qids = {q.qid for q in model.questions}
        except Exception:
            continue
        index[mid] = (meta.get("case_id"), qids)
    return index


def backfill_report_case_links(client, material_index=None) -> dict:
    """Infer and persist case links for untagged reports.

    Returns a summary {"linked": [...], "ambiguous": [...], "unmatched": [...]}.
    Only adds links; already-tagged reports are left untouched.
    """
    if material_index is None:
        material_index = _load_material_index(client)
    summary: dict[str, list[str]] = {"linked": [], "ambiguous": [], "unmatched": []}
    changed = False
    for rid, rjson in dict(client._reports).items():
        if rid in client._report_meta:
            continue
        try:
            report = json.loads(rjson)
        except (ValueError, TypeError):
            summary["unmatched"].append(rid)
            continue
        refs = {c.get("question_ref") for c in report.get("charts", [])}
        refs.discard(None)
        case_id, reason = infer_case(refs, material_index)
        if reason == "linked":
            client._report_meta[rid] = {
                "case_id": case_id,
                "name": report.get("name") or "report",
            }
            changed = True
            summary["linked"].append(rid)
        else:
            summary[reason].append(rid)
    if changed:
        client._save()
    return summary


def main() -> None:  # pragma: no cover - CLI
    import sys

    store_dir = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get("NSIGHT_DEMO_DIR")
        or os.path.join(os.getcwd(), "work", "demo-store")
    )
    client = InMemoryDataHiveClient(storage_dir=store_dir)
    summary = backfill_report_case_links(client)
    print(f"store: {store_dir}")
    for key in ("linked", "ambiguous", "unmatched"):
        print(f"{key:10s} {len(summary[key])}  {summary[key]}")


if __name__ == "__main__":  # pragma: no cover
    main()
