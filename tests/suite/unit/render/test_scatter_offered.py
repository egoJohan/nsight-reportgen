"""Scatter is reachable.

It was listed as a required chart type, had a working renderer, and could not
be produced: `suitability` returned None unconditionally and its whole config
schema was the note "Scatter configuration coming soon." A chart type the
product names and nobody can reach is worse than one it does not name.
"""
from __future__ import annotations

import pytest

import reportbuilder.render.charts  # noqa: F401 — registers the plugins
from reportbuilder.render.plugins import CHART_PLUGINS
from reportbuilder.stats.series import Cell, SeriesResult

pytestmark = pytest.mark.unit


def _series(segments: tuple[str, ...]) -> SeriesResult:
    cats = ("A", "B")
    cells = {(c, s): Cell(pct=10.0, count=10.0, mean=None)
             for c in cats for s in segments}
    return SeriesResult(categories=cats, segments=segments, cells=cells,
                        base_n={s: 100 for s in segments}, statistic="pct")


def test_it_is_configurable_at_all():
    schema = {f.key for f in CHART_PLUGINS["scatter"].config_schema}
    assert "scatter_xy" in schema
    assert "classifying_var" in schema, "the axes come from a classifier's groups"


def test_it_is_offered_once_there_are_two_groups():
    score = CHART_PLUGINS["scatter"].suitability(None, _series(("2025", "2026")))
    assert score is not None and score > 0


def test_it_is_not_offered_with_one_group():
    """Nothing to plot against."""
    assert CHART_PLUGINS["scatter"].suitability(None, _series(("Total",))) is None
    assert CHART_PLUGINS["scatter"].suitability(None, _series(("2025",))) is None


def test_it_is_never_the_suggestion():
    """Offered, not suggested: a scatter answers a question nobody asks by
    accident, and suggesting it would bury the types people do want."""
    p = CHART_PLUGINS["scatter"]
    assert p.suggest is None
    assert p.suitability(None, _series(("2025", "2026"))) < 0.2
