"""_resolve_xtab_layout — grouped vs small-multiples decision for cross-tabs."""
from __future__ import annotations

from types import SimpleNamespace

from reportbuilder.render.image.bars import _resolve_xtab_layout
from reportbuilder.stats.series import SeriesResult


def _ctx(segment_primary, options=None):
    s = SeriesResult(categories=("a",), segments=tuple(segment_primary or ()),
                     cells={}, base_n={}, statistic="pct",
                     segment_primary=segment_primary)
    return SimpleNamespace(series=s, spec=SimpleNamespace(options=options or {}))


def test_not_a_cross_tab_returns_none():
    s = SeriesResult(categories=("a",), segments=("Total",), cells={}, base_n={},
                     statistic="pct")
    assert _resolve_xtab_layout(SimpleNamespace(series=s, spec=SimpleNamespace(options={}))) is None


def test_auto_groups_when_few_combos():
    sp = {f"{p} · {i}": p for p in ("M", "F") for i in range(3)}   # 6 combos
    assert _resolve_xtab_layout(_ctx(sp)) == "grouped"


def test_auto_panels_when_many_combos():
    sp = {f"{p} · {i}": p for p in ("A", "B", "C") for i in range(4)}   # 12 combos
    assert _resolve_xtab_layout(_ctx(sp)) == "small_multiples"


def test_explicit_option_overrides_auto():
    sp = {f"{p} · {i}": p for p in ("A", "B", "C") for i in range(4)}   # 12 → auto=panels
    assert _resolve_xtab_layout(_ctx(sp, {"xtab_layout": "grouped"})) == "grouped"
    sp2 = {f"{p} · {i}": p for p in ("M", "F") for i in range(2)}       # 4 → auto=grouped
    assert _resolve_xtab_layout(_ctx(sp2, {"xtab_layout": "small_multiples"})) == "small_multiples"
