"""Test SeriesResult numeric contract."""

import pytest
from reportbuilder.stats.series import Cell, SeriesResult


def test_cell_lookup_returns_correct_cell():
    """Verify cell(category, segment) lookup returns the right Cell."""
    categories = ("Category A", "Category B")
    segments = ("Segment 1", "Segment 2", "Total")
    cells = {
        ("Category A", "Segment 1"): Cell(pct=50.0, count=10.0, mean=5.0),
        ("Category A", "Segment 2"): Cell(pct=30.0, count=6.0, mean=3.0),
        ("Category A", "Total"): Cell(pct=80.0, count=16.0, mean=8.0),
        ("Category B", "Segment 1"): Cell(pct=20.0, count=4.0, mean=2.0),
        ("Category B", "Segment 2"): Cell(pct=None, count=None, mean=None),
        ("Category B", "Total"): Cell(pct=20.0, count=4.0, mean=2.0),
    }
    base_n = {"Segment 1": 20, "Segment 2": 20, "Total": 20}

    result = SeriesResult(
        categories=categories,
        segments=segments,
        cells=cells,
        base_n=base_n,
        statistic="pct"
    )

    # Test lookup
    cell = result.cell("Category A", "Segment 1")
    assert cell.pct == 50.0
    assert cell.count == 10.0
    assert cell.mean == 5.0

    # Test with None values
    cell_none = result.cell("Category B", "Segment 2")
    assert cell_none.pct is None
    assert cell_none.count is None
    assert cell_none.mean is None


def test_total_always_present_in_segments():
    """Verify 'Total' is always present in segments of a built fixture."""
    categories = ("A", "B")
    segments = ("X", "Y", "Total")
    cells = {
        ("A", "X"): Cell(pct=10.0, count=1.0, mean=1.0),
        ("A", "Y"): Cell(pct=20.0, count=2.0, mean=2.0),
        ("A", "Total"): Cell(pct=30.0, count=3.0, mean=3.0),
        ("B", "X"): Cell(pct=15.0, count=1.5, mean=1.5),
        ("B", "Y"): Cell(pct=25.0, count=2.5, mean=2.5),
        ("B", "Total"): Cell(pct=40.0, count=4.0, mean=4.0),
    }
    base_n = {"X": 10, "Y": 10, "Total": 10}

    result = SeriesResult(
        categories=categories,
        segments=segments,
        cells=cells,
        base_n=base_n,
        statistic="pct"
    )

    assert "Total" in result.segments
    assert result.segments[-1] == "Total"


def test_base_n_per_segment():
    """Verify base_n per-segment value."""
    categories = ("Cat1",)
    segments = ("Seg1", "Seg2", "Total")
    cells = {
        ("Cat1", "Seg1"): Cell(pct=50.0, count=50.0, mean=5.0),
        ("Cat1", "Seg2"): Cell(pct=100.0, count=25.0, mean=2.5),
        ("Cat1", "Total"): Cell(pct=75.0, count=75.0, mean=7.5),
    }
    base_n = {"Seg1": 100, "Seg2": 25, "Total": 125}

    result = SeriesResult(
        categories=categories,
        segments=segments,
        cells=cells,
        base_n=base_n,
        statistic="count"
    )

    assert result.base_n["Seg1"] == 100
    assert result.base_n["Seg2"] == 25
    assert result.base_n["Total"] == 125


def test_keyerror_on_missing_cell():
    """Verify KeyError when cell() is given a missing (category, segment)."""
    categories = ("A",)
    segments = ("X", "Total")
    cells = {
        ("A", "X"): Cell(pct=10.0, count=1.0, mean=1.0),
        ("A", "Total"): Cell(pct=10.0, count=1.0, mean=1.0),
    }
    base_n = {"X": 10, "Total": 10}

    result = SeriesResult(
        categories=categories,
        segments=segments,
        cells=cells,
        base_n=base_n,
        statistic="pct"
    )

    # Should raise KeyError for missing (category, segment)
    with pytest.raises(KeyError):
        result.cell("A", "NonexistentSegment")

    with pytest.raises(KeyError):
        result.cell("NonexistentCategory", "X")
