"""Requirement catalog parser for the nSight report-tool requirements traceability table.

Parses ``docs/superpowers/specs/2026-06-22-nsight-report-tool-requirements.md``
and exposes the in-scope requirement IDs for use by the coverage audit gate.

Scope normalization rules (SCOPE column may carry annotations):
    IN, IN(thin), IN(numeric focus)  → "IN"   (include)
    DEFER, DEFER†                    → "DEFER" (include)
    OUT                              → "OUT"   (exclude)
    BLOCKED, BLOCKED(R4)             → "BLOCKED" (exclude)
    SCOPE-NOTE / SCOPENOTE           → "SCOPE-NOTE" (exclude)
"""
from __future__ import annotations

import pathlib
import re
from typing import NamedTuple


class Requirement(NamedTuple):
    id: str
    scope: str
    description: str


_ID_RE = re.compile(r"REQ-[A-Z]+-\d+[a-z]?")
_SCOPE_STRIP_RE = re.compile(r"[(†].*")  # strip from '(' or '†' onward


def _normalize_scope(raw: str) -> str:
    """Return the canonical scope token from a raw SCOPE cell value."""
    stripped = raw.strip()
    # Remove anything after '(' or '†'
    leading = _SCOPE_STRIP_RE.sub("", stripped).strip().upper()
    # Collapse SCOPENOTE / SCOPE-NOTE / SCOPE NOTE
    leading_nospace = leading.replace("-", "").replace(" ", "")
    if leading_nospace in ("SCOPENOTE", "SCOPNOTE"):
        return "SCOPE-NOTE"
    return leading


def parse_requirements(md_path: "str | pathlib.Path") -> list[Requirement]:
    """Parse the catalog table and return all rows as Requirement namedtuples.

    Rows that do not contain a valid REQ-<FAMILY>-<NN> id are skipped
    (e.g. section headings, the ⮑ continuation rows with lettered sub-IDs
    are included because their ID cell still matches the pattern).
    """
    path = pathlib.Path(md_path)
    text = path.read_text(encoding="utf-8")
    results: list[Requirement] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        # Split on '|', strip each cell
        cells = [c.strip() for c in line.split("|")]
        # Typical row: ['', 'REQ-X-NN', 'description', 'SCOPE', '§ref', 'test-note', '']
        # Need at least id + description + scope → ≥4 non-empty content cells
        if len(cells) < 5:
            continue
        # The id cell may have a '⮑ ' prefix (continuation sub-requirement)
        id_cell = cells[1].lstrip("⮑⮐ ")  # strip ⮑ (U+2B91) / ⬐ (U+2B90) and space
        id_match = _ID_RE.match(id_cell)
        if not id_match:
            continue
        req_id = id_match.group()
        description = cells[2]
        scope_raw = cells[3]
        scope = _normalize_scope(scope_raw)
        results.append(Requirement(id=req_id, scope=scope, description=description))
    return results


def in_scope_ids(md_path: "str | pathlib.Path") -> set[str]:
    """Return the set of REQ ids whose normalized scope is IN or DEFER.

    Excludes OUT, BLOCKED, and SCOPE-NOTE requirements.
    """
    return {
        req.id
        for req in parse_requirements(md_path)
        if req.scope in ("IN", "DEFER")
    }
