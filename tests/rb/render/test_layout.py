"""Tests for native-chart layout solver (design §9a step 1, R3)."""
from __future__ import annotations
import pytest
from reportbuilder.render.layout import (
    measure_label_width,
    solve_column_layout,
)


def test_measure_label_width_monotonic_in_length():
    short = measure_label_width("AB", 10)
    long_ = measure_label_width("ABCDEFGH", 10)
    assert short < long_, "wider text must produce a larger fraction"


def test_measure_label_width_monotonic_in_point_size():
    small = measure_label_width("AB", 10)
    large = measure_label_width("AB", 20)
    assert small < large, "larger point size must produce a larger fraction"


def test_solve_column_layout_coords_in_unit_square():
    result = solve_column_layout(("Yes", "No"), ("Total",))
    for box in (result.plot, result.legend):
        assert 0.0 <= box.x <= 1.0
        assert 0.0 <= box.y <= 1.0
        assert 0.0 < box.w <= 1.0
        assert 0.0 < box.h <= 1.0
        assert box.x + box.w <= 1.0 + 1e-9, f"x+w={box.x + box.w} exceeds 1"


def test_solve_column_layout_legend_right_of_plot():
    result = solve_column_layout(("Yes", "No"), ("Total",))
    plot, legend = result.plot, result.legend
    assert plot.x + plot.w <= legend.x + 1e-9, (
        f"legend ({legend.x}) must start at or after plot right edge ({plot.x + plot.w})"
    )


def test_solve_column_layout_longer_label_shrinks_plot():
    short_label = solve_column_layout(("A",), ("X",))
    long_label = solve_column_layout(("A",), ("A very long segment legend label",))
    assert long_label.plot.w < short_label.plot.w, (
        "a longer legend label should shrink the plot area"
    )
