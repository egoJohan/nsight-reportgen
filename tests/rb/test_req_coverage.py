"""Requirement-coverage audit gate (Task 9.4, REQ-N-04 family).

Proves that every in-scope requirement (IN or DEFER scope) in the requirements
catalog has a ``REQ-<id>`` marker token in the test suite — except for a small,
documented allowlist of requirements whose tests are deferred to a not-yet-built
phase (UI/Flutter tests, presentation-quality judge tests).

Two tests:
1. test_all_in_scope_requirements_are_covered — asserts uncovered == set().
2. test_allowlist_is_honest — asserts every allowlist entry is actually in-scope
   AND is not already covered by a test marker (no stale or needless entries).
"""
from __future__ import annotations

import pathlib
import re

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]  # proto/
REQ_MD = _REPO_ROOT / "docs" / "superpowers" / "specs" / "2026-06-22-nsight-report-tool-requirements.md"

# Search directories for REQ-<id> tokens
_TEST_DIRS = [
    _REPO_ROOT / "tests",
]
# Guard: add ui/test dirs only if they exist (Phase 8 Flutter tests)
for _ui_dir in (_REPO_ROOT / "ui" / "test", _REPO_ROOT / "ui" / "integration_test"):
    if _ui_dir.exists():
        _TEST_DIRS.append(_ui_dir)


# ---------------------------------------------------------------------------
# Allowlist: requirements whose covering tests are not yet written
# ---------------------------------------------------------------------------

# Each entry maps a REQ id → one-line reason.
# Policy: only add entries here if NO current-scope backend test can cover them.
# If a covering test exists, backfill the REQ- marker instead.
DEFERRED_ALLOWLIST: dict[str, str] = {
    # --- UI requirements: only review/NFR items with no automatable test remain ---
    # REQ-U-01..02, REQ-U-04..11 are now credited from ui/test/*.dart (Phase 8 Flutter tests).
    "REQ-U-03": "UI-consistency review against a UI-pattern checklist — human review acceptance, no automatable test.",
    "REQ-U-12": "UI-extensibility NFR — review acceptance, no automatable test.",
    # REQ-C-28b covered by @pytest.mark.judge test in tests/rb/e2e/test_pipeline_synthetic.py
    # REQ-C-29b covered by @pytest.mark.judge test in tests/rb/e2e/test_pipeline_attendo.py
}


# ---------------------------------------------------------------------------
# Helper: collect all covered REQ-<id> tokens from the test suite
# ---------------------------------------------------------------------------

_REQ_TOKEN_RE = re.compile(r"REQ-[A-Z]+-[0-9]+[a-z]?")


_THIS_FILE = pathlib.Path(__file__).resolve()


def _collect_covered() -> set[str]:
    """Return all distinct REQ-<id> tokens found in the test directories.

    This file (test_req_coverage.py) is excluded from the scan because it
    contains REQ-<id> strings as allowlist dict keys, not as test markers.

    Python test dirs are scanned for ``*.py``; Flutter ui test dirs are also
    scanned for ``*.dart`` (Phase-8 Flutter tests live under ui/test/).
    """
    _UI_DIRS = {_REPO_ROOT / "ui" / "test", _REPO_ROOT / "ui" / "integration_test"}

    covered: set[str] = set()
    for base in _TEST_DIRS:
        # Python files — always scan these
        for py_file in base.rglob("*.py"):
            if py_file.resolve() == _THIS_FILE:
                continue  # skip this file — it holds the allowlist, not markers
            try:
                text = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            covered.update(_REQ_TOKEN_RE.findall(text))

        # Dart files — only for Flutter ui test dirs
        if base in _UI_DIRS:
            for dart_file in base.rglob("*.dart"):
                try:
                    text = dart_file.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                covered.update(_REQ_TOKEN_RE.findall(text))

    return covered


# ---------------------------------------------------------------------------
# Test 1: every in-scope requirement has a test marker (or is allowlisted)
# ---------------------------------------------------------------------------

def test_all_in_scope_requirements_are_covered():
    """Every IN/DEFER requirement has a REQ-<id> token in the test suite.

    Fails with the sorted list of uncovered ids so the gate names exactly what
    is missing — not just that something is missing.
    """
    from reportbuilder.testing.req_catalog import in_scope_ids

    required = in_scope_ids(REQ_MD)
    covered = _collect_covered()

    uncovered = required - covered - set(DEFERRED_ALLOWLIST)

    assert uncovered == set(), (
        "The following in-scope requirements have no test marker (REQ-<id>) in the suite "
        "and are not in the deferred allowlist:\n"
        + "\n".join(f"  {rid}" for rid in sorted(uncovered))
        + "\n\nFor each id: either add 'REQ-<id>' to an existing test's docstring "
        "(if a covering test exists) or add it to DEFERRED_ALLOWLIST with a reason."
    )


# ---------------------------------------------------------------------------
# Test 2: the allowlist is honest (no stale/typo entries; no needless entries)
# ---------------------------------------------------------------------------

def test_allowlist_is_honest():
    """Every DEFERRED_ALLOWLIST entry is in-scope AND not already covered.

    Prevents the allowlist from silently hiding regressions:
    - If an id is no longer in-scope, the entry is stale (typo or removed req).
    - If a test marker for the id already exists, the entry is needless and
      should be removed (the test provides real coverage now).
    """
    from reportbuilder.testing.req_catalog import in_scope_ids

    required = in_scope_ids(REQ_MD)
    covered = _collect_covered()

    stale = {rid for rid in DEFERRED_ALLOWLIST if rid not in required}
    needless = {rid for rid in DEFERRED_ALLOWLIST if rid in covered}

    errors: list[str] = []
    if stale:
        errors.append(
            "Stale allowlist entries (id not in catalog or not in-scope):\n"
            + "\n".join(f"  {rid}" for rid in sorted(stale))
        )
    if needless:
        errors.append(
            "Needless allowlist entries (id already has a test marker — remove from allowlist):\n"
            + "\n".join(f"  {rid}" for rid in sorted(needless))
        )

    assert not errors, "\n\n".join(errors)
