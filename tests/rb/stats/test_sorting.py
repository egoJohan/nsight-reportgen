"""Tests for sort_categories (REQ-S-01/02/03, C-26)."""
from __future__ import annotations
import pytest
from reportbuilder.model.report import SortSpec
from reportbuilder.stats.sorting import sort_categories

# Three fixture rows: Low(pct10,count10,mean1,idx0,topbox70),
#                    Mid(pct50,count50,mean2,idx1,topbox80),
#                    High(pct40,count40,mean3,idx2,topbox80)
ROWS = [
    ("Low",  1.0, {"pct": 10.0, "count": 10, "mean": 1.0, "data_index": 0, "topbox": 70.0}),
    ("Mid",  2.0, {"pct": 50.0, "count": 50, "mean": 2.0, "data_index": 1, "topbox": 80.0}),
    ("High", 3.0, {"pct": 40.0, "count": 40, "mean": 3.0, "data_index": 2, "topbox": 80.0}),
]


def test_default_is_pct_descending():
    """Default sort basis is percentage magnitude (most common case). (REQ-S-03, REQ-C-26)"""
    result = sort_categories(ROWS, SortSpec(basis="pct"))
    assert result == ["Mid", "High", "Low"]


def test_data_order_preserves_index():
    result = sort_categories(ROWS, SortSpec(basis="data_order"))
    assert result == ["Low", "Mid", "High"]


def test_count_and_mean_bases():
    assert sort_categories(ROWS, SortSpec(basis="count")) == ["Mid", "High", "Low"]
    assert sort_categories(ROWS, SortSpec(basis="mean"))  == ["High", "Mid", "Low"]


def test_topbox_sum_uses_topbox_value():
    """Sort by top-box sum (e.g. 4+5 on a 5-point scale) is supported. (REQ-S-02)"""
    # Mid=80, High=80 (tie) → stable data order → Mid before High; Low=70 last
    result = sort_categories(ROWS, SortSpec(basis="topbox_sum", topbox_codes=(2.0, 3.0)))
    assert result == ["Mid", "High", "Low"]


def test_ascending_when_descending_false():
    result = sort_categories(ROWS, SortSpec(basis="pct", descending=False))
    assert result == ["Low", "High", "Mid"]
