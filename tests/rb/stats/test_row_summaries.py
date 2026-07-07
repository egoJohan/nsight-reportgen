"""Row-summary column computation (spec 2026-07-07-row-summary-column)."""
from reportbuilder.stats.engine import _compute_row_summaries
from reportbuilder.stats.series import Cell
from reportbuilder.model.report import (
    ChartSpec, NumberFormat, SortSpec, ElementToggles,
)


def _spec(**kw) -> ChartSpec:
    return ChartSpec(
        question_ref="q", chart_type="stacked_horizontal_bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(), sort=SortSpec(basis="pct"),
        template_slot="s1", elements=ElementToggles(), **kw,
    )


# One statement "A" on a 3-point scale: 20% at point 1, 30% at 2, 50% at 3.
_LEVELS = ["L1", "L2", "L3"]
_POINTS = [1.0, 2.0, 3.0]
_STMTS = ["A"]
_CELLS = {
    ("L1", "A"): Cell(pct=20.0),
    ("L2", "A"): Cell(pct=30.0),
    ("L3", "A"): Cell(pct=50.0),
}


def _rs(**kw):
    return _compute_row_summaries(_spec(**kw), _STMTS, _LEVELS, _POINTS, _CELLS)


def test_none_is_off():
    assert _rs(row_summary_fn="none") is None


def test_top2_sum():
    assert _rs(row_summary_fn="top2_sum") == (80.0,)   # L2 + L3


def test_top3_sum():
    assert _rs(row_summary_fn="top3_sum") == (100.0,)  # all three


def test_sum_of_selected():
    assert _rs(row_summary_fn="sum", row_summary_codes=(3.0,)) == (50.0,)


def test_mean():
    # (1*20 + 2*30 + 3*50) / 100 = 2.3
    assert _rs(row_summary_fn="mean") == (2.3,)


def test_net():
    # pos=3 (50%) − neg=1 (20%) = 30
    assert _rs(
        row_summary_fn="net", row_summary_pos_codes=(3.0,), row_summary_neg_codes=(1.0,)
    ) == (30.0,)
