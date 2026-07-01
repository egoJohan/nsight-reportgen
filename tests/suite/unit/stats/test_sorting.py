"""Unit tests for reportbuilder.stats.sorting.sort_categories."""
from __future__ import annotations

import pytest

from reportbuilder.model.report import SortSpec
from reportbuilder.stats.sorting import sort_categories


def _rows():
    # (label, code, vals). B and C tie on pct (30); C has larger count.
    return [
        ("A", 1.0, {"pct": 10.0, "count": 5.0, "mean": 1.0, "data_index": 0, "topbox": 10.0}),
        ("B", 2.0, {"pct": 30.0, "count": 2.0, "mean": 3.0, "data_index": 1, "topbox": 30.0}),
        ("C", 3.0, {"pct": 30.0, "count": 9.0, "mean": 2.0, "data_index": 2, "topbox": 5.0}),
    ]


def test_data_order_preserves_data_index():
    assert sort_categories(_rows(), SortSpec(basis="data_order")) == ["A", "B", "C"]


def test_pct_descending_is_default():
    # descending default True: 30(B), 30(C), 10(A); B before C by tie->data order
    assert sort_categories(_rows(), SortSpec(basis="pct")) == ["B", "C", "A"]


def test_pct_ascending_via_descending_false():
    assert sort_categories(_rows(), SortSpec(basis="pct", descending=False)) == ["A", "B", "C"]


def test_count_basis():
    assert sort_categories(_rows(), SortSpec(basis="count")) == ["C", "A", "B"]


def test_mean_basis():
    assert sort_categories(_rows(), SortSpec(basis="mean")) == ["B", "C", "A"]


def test_topbox_sum_basis_reads_topbox_key():
    assert sort_categories(_rows(), SortSpec(basis="topbox_sum")) == ["B", "A", "C"]


def test_tie_keeps_data_order_stability():
    # Both tie on pct 30 -> keep original data order B then C
    ordered = sort_categories(_rows(), SortSpec(basis="pct"))
    assert ordered.index("B") < ordered.index("C")


def test_unknown_basis_raises_keyerror():
    with pytest.raises(KeyError):
        sort_categories(_rows(), SortSpec(basis="does_not_exist"))
