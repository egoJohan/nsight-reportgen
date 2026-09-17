"""A combo's default subtitle names both measures.

"Combo chartin otsikko ja alaotsikko ei mukaudu molempiin kuvaajiin."

The subtitle defaults to the question, and a combo's question describes only its
BARS — the line is another variable entirely. So the default now names both.

Only the DEFAULT. The author's own `slide_description` is never touched: the
code right below this carries a note that nothing is appended to the author's
line, and that stands. (Johan, 2026-09-16)
"""
from __future__ import annotations

import pytest

from reportbuilder.render.image.slide_chrome import _combo_subtitle
from reportbuilder.stats.series import Cell, SeriesResult

pytestmark = pytest.mark.unit

QUESTION = "Minkä kokoisessa kaupungissa tai kunnassa asut?"
INDEX = "index_johtaminenjakulttuuri"


class _Spec:
    def __init__(self, chart_type="combo", options=None):
        self.chart_type = chart_type
        self.options = options if options is not None else {"combo_secondary": INDEX}


class _Ctx:
    def __init__(self, spec, series):
        self.spec, self.series = spec, series


def _series(with_mean=True) -> SeriesResult:
    segs = ("Total",) + ((INDEX,) if with_mean else ())
    cells = {("A", s): Cell(pct=1.0) for s in segs}
    stats = {"Total": "pct", **({INDEX: "mean"} if with_mean else {})}
    return SeriesResult(categories=("A",), segments=segs, cells=cells,
                        base_n={"Total": 10}, statistic="pct",
                        segment_statistics=stats)


def test_a_combo_names_the_second_measure():
    out = _combo_subtitle(_Ctx(_Spec(), _series()), QUESTION)
    assert QUESTION in out and INDEX in out


def test_it_says_the_second_measure_is_a_mean():
    out = _combo_subtitle(_Ctx(_Spec(), _series()), QUESTION)
    assert "keskiarvo" in out


def test_another_chart_type_is_unchanged():
    ctx = _Ctx(_Spec(chart_type="vertical_bar"), _series())
    assert _combo_subtitle(ctx, QUESTION) == QUESTION


def test_a_combo_without_a_secondary_is_unchanged():
    ctx = _Ctx(_Spec(options={}), _series(with_mean=False))
    assert _combo_subtitle(ctx, QUESTION) == QUESTION


def test_a_combo_whose_series_has_no_mean_is_unchanged():
    """The option is set but the engine produced no mean segment — the
    no-secondary fallback. Nothing to name."""
    ctx = _Ctx(_Spec(), _series(with_mean=False))
    assert _combo_subtitle(ctx, QUESTION) == QUESTION


def _mean_series() -> SeriesResult:
    """A combo on a BATTERY: the series' own statistic is already `mean`.

    `_battery` reports `statistic="mean"` whatever the spec asks for, so this is
    an ordinary slide, not a contrivance.
    """
    segs = ("Miehet", "Naiset", INDEX)
    return SeriesResult(
        categories=("A",), segments=segs,
        cells={("A", s): Cell(mean=3.0) for s in segs},
        base_n={s: 10 for s in segs} | {"Total": 20}, statistic="mean",
        segment_statistics={"Miehet": "mean", "Naiset": "mean", INDEX: "mean"})


def test_a_classifier_group_is_never_named_as_the_second_measure():
    """The subtitle asked which segment is a "mean", which is true of EVERY
    segment once the series itself measures means — so it named whichever
    classifier group came first and called it the second measure.

    The question is "does this segment measure something OTHER than the series
    does?", the same one the renderer asks to find its two halves.
    (Johan, 2026-09-17)
    """
    out = _combo_subtitle(_Ctx(_Spec(), _mean_series()), QUESTION)
    assert "Miehet" not in out, f"named a classifier group as the measure: {out}"
