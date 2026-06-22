"""Tests for base_rules.py — denominator correctness (R1).

TDD: written before implementation to define expected behaviour.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from reportbuilder.model.question import ValueLabel, Variable
from reportbuilder.stats.base_rules import multi_base, segment_bases, single_base


def _var(name: str, missing: frozenset[float] = frozenset()) -> Variable:
    """Build a minimal categorical Variable for testing."""
    return Variable(
        name=name,
        label=name,
        measurement="categorical",
        value_labels=(),
        missing_values=missing,
    )


# ---------------------------------------------------------------------------
# single_base
# ---------------------------------------------------------------------------

def test_single_base_excludes_nan_and_user_missing():
    """Valid = non-NaN and not in user-missing set. (REQ-C-16, MV-01/02)"""
    df = pd.DataFrame({"q1": [1.0, 2.0, 1.0, 99.0, np.nan]})
    result = single_base(df, _var("q1", missing=frozenset({99.0})))
    # Valid rows: 1.0, 2.0, 1.0 → 3; 99.0 excluded by user-missing; NaN excluded as Sysmis
    assert result == 3


# ---------------------------------------------------------------------------
# multi_base
# ---------------------------------------------------------------------------

def test_multi_base_is_respondents_answering_not_selection_count():
    """Base = respondents who answered ≥1 item in the set, NOT the total selection count.
    (REQ-M-03)"""
    df = pd.DataFrame({
        "m1": [1.0, 0.0, 0.0],
        "m2": [1.0, 1.0, 0.0],
    })
    # r1: selected m1 and m2 (counts as 1 respondent, 2 selections)
    # r2: selected m2 only  (counts as 1 respondent, 1 selection)
    # r3: selected nothing  (not counted)
    # Selection count = 3, but respondent count = 2 — we want respondents.
    result = multi_base(df, [_var("m1"), _var("m2")])
    assert result == 2


# ---------------------------------------------------------------------------
# segment_bases
# ---------------------------------------------------------------------------

def test_segment_bases_have_total():
    """Per-segment bases plus a 'Total'. (REQ-C-14)"""
    df = pd.DataFrame({
        "q1":  [1.0, 2.0, 1.0, 2.0],
        "seg": [10.0, 10.0, 20.0, 20.0],
    })
    result = segment_bases(df, _var("q1"), "seg")
    assert result["Total"] == 4
    assert result["10"] == 2
    assert result["20"] == 2
