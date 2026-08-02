"""Do these indicator columns split the sample into segments? (spec 2026-08-02 §2.1)

Overlap is measured among COVERED respondents and the floor is an absolute count,
so a screened design — where only qualifiers see a concept — still counts, while a
family only one person answered cannot pass on vacuous exclusivity.
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.ingest.multi_group import member_masks, near_partition


def _masks(*cols):
    return [pd.Series(c, dtype=bool) for c in cols]


def test_clean_two_way_split_is_a_partition():
    n = 200
    a = [True] * 100 + [False] * 100
    b = [False] * 100 + [True] * 100
    assert near_partition(_masks(a, b), n) is True


def test_screened_design_is_a_partition():
    """Only 60% qualify and see a concept; the rest are in no segment. A coverage
    threshold measured over the whole sample wrongly rejected this."""
    n = 200
    a = [True] * 60 + [False] * 140
    b = [False] * 60 + [True] * 60 + [False] * 80
    assert near_partition(_masks(a, b), n) is True


def test_overlapping_multi_response_is_not_a_partition():
    """var7: nearly everyone ticks two or more."""
    n = 200
    a = [True] * 200
    b = [True] * 190 + [False] * 10
    assert near_partition(_masks(a, b), n) is False


def test_degenerate_family_with_one_respondent_is_rejected():
    """var157/var17: exclusivity is vacuously perfect when almost nobody answered."""
    n = 1549
    a = [True] + [False] * 1548
    b = [False] * 1549
    assert near_partition(_masks(a, b), n) is False


def test_family_with_an_empty_member_is_rejected():
    n = 200
    a = [True] * 100 + [False] * 100
    b = [False] * 100 + [True] * 100
    c = [False] * 200
    assert near_partition(_masks(a, b, c), n) is False


def test_single_column_is_rejected():
    assert near_partition(_masks([True] * 200), 200) is False


def test_more_than_ten_columns_is_rejected():
    n = 200
    cols = [[i * 18 <= j < (i + 1) * 18 for j in range(200)] for i in range(11)]
    assert near_partition(_masks(*cols), n) is False


def test_two_percent_overlap_is_tolerated():
    n = 200
    a = [True] * 102 + [False] * 98
    b = [False] * 100 + [True] * 100          # 2 rows in both
    assert near_partition(_masks(a, b), n) is True


def test_ten_percent_overlap_is_rejected():
    n = 200
    a = [True] * 120 + [False] * 80
    b = [False] * 100 + [True] * 100          # 20 rows in both
    assert near_partition(_masks(a, b), n) is False


def test_small_sample_below_the_absolute_floor_is_rejected():
    """Exclusivity is not evidence of anything at n=20."""
    n = 20
    a = [True] * 10 + [False] * 10
    b = [False] * 10 + [True] * 10
    assert near_partition(_masks(a, b), n) is False


def test_empty_input_is_rejected():
    assert near_partition([], 200) is False
    assert near_partition(_masks([True] * 5, [False] * 5), 0) is False


def test_member_masks_returns_none_for_a_missing_column():
    df = pd.DataFrame({"Polku1": [1.0, None]})
    assert member_masks(df, ("Polku1", "Polku2")) is None


def test_member_masks_treats_missing_as_not_in_segment():
    df = pd.DataFrame({"Polku1": [1.0, None, 1.0]})
    masks = member_masks(df, ("Polku1",))
    assert list(masks[0]) == [True, False, True]


def test_member_masks_ignores_zero_and_other_codes():
    df = pd.DataFrame({"f": [1.0, 0.0, 2.0]})
    masks = member_masks(df, ("f",))
    assert list(masks[0]) == [True, False, False]
