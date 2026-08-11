"""A stacked bar may only be normalised to 100% where its stack really partitions
the bar's base — otherwise the TRUE widths are drawn (spec: rendering honesty).

The defect: `stacked_horizontal_bar` scaled every bar to fill exactly 100% while
the data labels kept the true percentages. Correct for a single-choice question
(the categories partition the base); a lie for a multi-response one, where
respondents pick several options and the shares sum to ~465% — a segment labelled
"85 %" was drawn at ~18% of the bar. Nothing revalidates a saved chart_type
(render/deck.py dispatches straight off the stored id), so the RENDERER is the
only place that can refuse to draw the lie.

These tests drive the real builders and read the geometry off the figure (via the
`render_png` spy idiom used elsewhere in this suite) rather than trusting the
decision helper alone: what matters is the picture, not the predicate.
"""
from __future__ import annotations

import pandas as pd
import pytest

import reportbuilder.render.image.bars as bars_mod
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.stats.engine import compute
from reportbuilder.stats.series import Cell, SeriesResult

from suite._helpers import make_ctx, make_spec

STACKED = ["stacked_horizontal_bar", "stacked_vertical_bar"]


# ---------------------------------------------------------------------------
# Geometry capture
# ---------------------------------------------------------------------------

def _capture_axes(monkeypatch) -> list[dict]:
    """Record each rendered axes' bar geometry + value-axis limit.

    `render_png` clears the figure right after saving it, so the snapshot has to
    be taken inside the call. One dict per axes (the SEPARATE layout draws
    several), in draw order."""
    shots: list[dict] = []
    real = bars_mod.render_png

    def _spy(fig):
        for ax in fig.axes:
            shots.append({
                "widths": [p.get_width() for p in ax.patches],
                "heights": [p.get_height() for p in ax.patches],
                "xlim": ax.get_xlim(),
                "ylim": ax.get_ylim(),
                "texts": [(t.get_position(), t.get_text()) for t in ax.texts],
            })
        return real(fig)

    monkeypatch.setattr(bars_mod, "render_png", _spy)
    return shots


def _bar_totals(shot: dict, chart_type: str, n_bars: int) -> list[float]:
    """Total drawn length of each stacked bar. matplotlib keeps one Rectangle per
    (stack member × bar), added stack-member by stack-member, so summing every
    `n_bars`-th value recovers each bar's own total."""
    key = "widths" if chart_type == "stacked_horizontal_bar" else "heights"
    vals = shot[key]
    return [sum(vals[i::n_bars]) for i in range(n_bars)]


def _value_axis_max(shot: dict, chart_type: str) -> float:
    return shot["xlim" if chart_type == "stacked_horizontal_bar" else "ylim"][1]


def _render(chart_type: str, series, monkeypatch, **spec_kw) -> list[dict]:
    _prs, _slide, _slot, ctx = make_ctx(chart_type, series, **spec_kw)
    shots = _capture_axes(monkeypatch)
    IMAGE_BUILDERS[chart_type](ctx)
    return shots


# ---------------------------------------------------------------------------
# Fixtures — hand-built series, so each bar's shape is exactly the point
# ---------------------------------------------------------------------------

def _series(bars_pcts: dict[str, dict[str, float]], base: int = 100,
            **kw) -> SeriesResult:
    """A stacked series from {bar: {category: pct}}; counts follow the pcts on a
    base of `base`, so `is_partition` sees the same shape the renderer draws."""
    cats = tuple(next(iter(bars_pcts.values())).keys())
    segs = tuple(bars_pcts)
    cells = {
        (c, b): Cell(pct=p[c], count=p[c] / 100.0 * base)
        for b, p in bars_pcts.items() for c in cats
    }
    return SeriesResult(categories=cats, segments=segs, cells=cells,
                        base_n={b: base for b in segs} | {"Total": base},
                        statistic="pct", **kw)


def _partition_series() -> SeriesResult:
    """Single-choice: every respondent in exactly one category (sums to 100)."""
    return _series({"Nainen": {"Kyllä": 62.0, "Ei": 38.0},
                    "Mies": {"Kyllä": 55.0, "Ei": 45.0},
                    "Total": {"Kyllä": 58.0, "Ei": 42.0}})


def _shortfall_series() -> SeriesResult:
    """98% of base: a small unnamed "no answer" slice counted in the base but not
    among the categories — ordinary single-choice data, NOT overlap."""
    return _series({"Nainen": {"Kyllä": 60.0, "Ei": 38.0},
                    "Mies": {"Kyllä": 53.0, "Ei": 45.0},
                    "Total": {"Kyllä": 56.5, "Ei": 41.5}})


def _overlap_series() -> SeriesResult:
    """var7-shaped multi-response: shares sum to 465% of the base."""
    picks = {"Pyykinpesuaine": 85.0, "Vartalonpesu": 77.0, "Shampoo": 74.0,
             "Huuhteluaine": 47.0, "Muotoilutuote": 45.0, "Kasvovoide": 41.0,
             "Puhdistusaine": 39.0, "Jauhepesuaine": 34.0, "Pyykkietikka": 23.0}
    return _series({"Finland": picks, "Total": picks})


# ---------------------------------------------------------------------------
# The no-op guard: a genuine partition must keep normalising, exactly as before
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("chart_type", STACKED)
def test_partition_stack_still_normalises(chart_type, monkeypatch):
    """Categories partition the base → each bar fills the axis and the axis is
    the fixed 0-100 composition scale (unchanged behaviour)."""
    shots = _render(chart_type, _partition_series(), monkeypatch)
    assert len(shots) == 1
    totals = _bar_totals(shots[0], chart_type, n_bars=3)
    assert all(abs(t - 100.0) < 1e-6 for t in totals), totals
    assert _value_axis_max(shots[0], chart_type) == 100.0


@pytest.mark.parametrize("chart_type", STACKED)
def test_stack_summing_to_98_still_normalises(chart_type, monkeypatch):
    """Falling a couple of points SHORT of 100 is a handful of non-respondents,
    not overlap: it keeps the 100% reading (the same asymmetric allowance the
    offering side gives a pie — `PARTITION_UNDERSHOOT_TOL_PCT`), so the bars are
    stretched to fill the axis."""
    s = _shortfall_series()
    assert not s.is_partition("Nainen"), "premise: strictly, 98 != 100"
    shots = _render(chart_type, s, monkeypatch)
    totals = _bar_totals(shots[0], chart_type, n_bars=3)
    assert all(abs(t - 100.0) < 1e-6 for t in totals), totals
    assert _value_axis_max(shots[0], chart_type) == 100.0


# ---------------------------------------------------------------------------
# The defect: genuine overlap must be drawn true
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("chart_type", STACKED)
def test_overlapping_multi_draws_true_widths(chart_type, monkeypatch):
    """465% of base → the bars are NOT rescaled: each segment is drawn at the
    value its own label prints, and the value axis reaches the real maximum."""
    shots = _render(chart_type, _overlap_series(), monkeypatch)
    totals = _bar_totals(shots[0], chart_type, n_bars=2)
    assert all(abs(t - 465.0) < 1e-6 for t in totals), totals
    axis_max = _value_axis_max(shots[0], chart_type)
    assert axis_max >= 465.0, f"axis must reach the real maximum, got {axis_max}"
    # The individual segment, not just the bar total: the "85 %" label sat on an
    # 18-unit box before the fix.
    drawn = shots[0]["widths" if chart_type == "stacked_horizontal_bar" else "heights"]
    assert abs(max(drawn) - 85.0) < 1e-6, drawn


@pytest.mark.parametrize("chart_type", STACKED)
def test_one_overshooting_bar_makes_every_bar_true(chart_type, monkeypatch):
    """The decision is per CHART, not per bar: a normalised bar next to a true
    one in the same axes would be incomparable — worse than either alone."""
    s = _series({"Yksi": {"A": 60.0, "B": 40.0},          # a clean partition
                 "Kaksi": {"A": 180.0, "B": 120.0},       # overlaps
                 "Total": {"A": 120.0, "B": 80.0}})
    shots = _render(chart_type, s, monkeypatch)
    totals = _bar_totals(shots[0], chart_type, n_bars=3)
    assert [round(t, 6) for t in totals] == [100.0, 300.0, 200.0], (
        "the partition bar must be drawn at its true 100 too — not stretched")
    assert _value_axis_max(shots[0], chart_type) >= 300.0


@pytest.mark.parametrize("chart_type", STACKED)
def test_unjudgeable_bar_keeps_the_100_percent_reading(chart_type, monkeypatch):
    """Cells carrying neither a count nor a percentage (e.g. a mean-statistic
    stack) say nothing about overlap. Missing information must not be read as
    evidence of it, so such a chart keeps normalising."""
    cats = ("A", "B")
    cells = {(c, "Total"): Cell(mean=2.0 if c == "A" else 3.0) for c in cats}
    s = SeriesResult(categories=cats, segments=("Total",), cells=cells,
                     base_n={"Total": 100}, statistic="mean")
    shots = _render(chart_type, s, monkeypatch)
    totals = _bar_totals(shots[0], chart_type, n_bars=1)
    assert abs(totals[0] - 100.0) < 1e-6
    assert _value_axis_max(shots[0], chart_type) == 100.0


# ---------------------------------------------------------------------------
# End-to-end through compute(): a real multi-response question
# ---------------------------------------------------------------------------

def _multi_model_and_df():
    """3-option "select all that apply", every respondent picks 2 → shares sum
    to 200% of the base."""
    names = ("m1", "m2", "m3")
    variables = {
        n: Variable(name=n, label=f"Option {i + 1}", measurement="nominal",
                    value_labels=(ValueLabel(0.0, "No"), ValueLabel(1.0, "Yes")),
                    missing_values=frozenset())
        for i, n in enumerate(names)
    }
    model = QuestionModel(variables=variables, questions=[])
    q = Question(qid="m", kind="multi", variables=names, text="Valitse kaikki")
    df = pd.DataFrame({"m1": [1.0] * 30 + [0.0] * 30,
                       "m2": [1.0] * 30 + [1.0] * 30,
                       "m3": [0.0] * 30 + [1.0] * 30})
    return model, q, df


@pytest.mark.parametrize("chart_type", STACKED)
def test_real_multi_question_renders_true_widths(chart_type, monkeypatch):
    """The whole product path — compute() → the image builder — for a genuinely
    overlapping multi question."""
    model, q, df = _multi_model_and_df()
    series = compute(q, make_spec(chart_type, classifying_var=None), df, model)
    assert not series.is_partition("Total"), "premise: the options overlap"
    shots = _render(chart_type, series, monkeypatch, classifying_var=None)
    totals = _bar_totals(shots[0], chart_type, n_bars=1)
    assert abs(totals[0] - 200.0) < 1e-6, totals
    assert _value_axis_max(shots[0], chart_type) >= 200.0


# ---------------------------------------------------------------------------
# The two shared consumers: the row-summary column and the panel renderer
# ---------------------------------------------------------------------------

def test_row_summary_column_clears_a_true_width_axis(monkeypatch):
    """The right-hand summary strip is placed at ~109 on a 0-100 axis. On a
    true-width 0-465 axis that hard-coded 109 would land INSIDE the bars, so the
    strip is placed proportionally to the axis instead."""
    s = _overlap_series()
    s = SeriesResult(**{**s.__dict__,
                        "row_summaries": (61.0, 61.0),
                        "row_summary_keys": ("Finland", "Total")})
    shots = _render("stacked_horizontal_bar", s, monkeypatch,
                    row_summary_fn="top2_sum", row_summary_label="Top 2")
    axis_max = shots[0]["xlim"][1]
    summary_x = [x for (x, _y), t in shots[0]["texts"] if t in ("Top 2", "61 %")]
    assert len(summary_x) == 3, "a header + one value per bar"
    assert all(x > 465.0 for x in summary_x), (
        f"the summary column must clear the 465-long bars, got {summary_x}")
    assert axis_max > max(summary_x), "the strip must stay inside the axes"


def test_row_summary_column_unchanged_on_a_normalised_axis(monkeypatch):
    """The no-op guard for the same code: on a 100%-stacked chart the strip stays
    exactly where it has always been (x=109, axes reserved out to 118)."""
    s = _partition_series()
    s = SeriesResult(**{**s.__dict__,
                        "row_summaries": (62.0, 55.0, 58.0),
                        "row_summary_keys": ("Nainen", "Mies", "Total")})
    shots = _render("stacked_horizontal_bar", s, monkeypatch,
                    row_summary_fn="top2_sum", row_summary_label="Top 2")
    assert shots[0]["xlim"] == (0.0, 118.0)
    header_x = [x for (x, _y), t in shots[0]["texts"] if t == "Top 2"]
    assert header_x == [109.0]


def _panel_series(overlap: bool) -> SeriesResult:
    """A two-classifier series in the shape the SEPARATE layout draws: one panel
    per classifying variable, each with its own bars + reference Total."""
    cats = ("A", "B")
    segs = ("Nainen", "Mies", "Sukupuoli · Total",
            "Nuoret", "Vanhat", "Ikä · Total")
    scale = 3.0 if overlap else 1.0
    cells = {}
    for i, seg in enumerate(segs):
        a = (55.0 + i) * scale
        cells[("A", seg)] = Cell(pct=a, count=a)
        cells[("B", seg)] = Cell(pct=(100.0 * scale) - a, count=(100.0 * scale) - a)
    primary = {s: ("Sukupuoli" if i < 3 else "Ikä") for i, s in enumerate(segs)}
    return SeriesResult(categories=cats, segments=segs, cells=cells,
                        base_n={s: 100 for s in segs} | {"Total": 100},
                        statistic="pct", segment_primary=primary)


@pytest.mark.parametrize("chart_type", STACKED)
def test_separate_panels_draw_true_widths_on_one_shared_axis(chart_type, monkeypatch):
    """The panel renderer is shared by both stacked builders, so it gets the same
    treatment — and every panel must use the SAME scale: panels of one chart are
    read against each other."""
    shots = _render(chart_type, _panel_series(overlap=True), monkeypatch,
                    classifying_var="sex", classifying_var_2="age",
                    options={"xtab_layout": "separate"})
    assert len(shots) == 2, "one panel per classifying variable"
    for shot in shots:
        totals = _bar_totals(shot, "stacked_horizontal_bar", n_bars=3)
        assert all(abs(t - 300.0) < 1e-6 for t in totals), totals
    assert shots[0]["xlim"] == shots[1]["xlim"], (
        "panels drawn on different scales would be incomparable")
    assert shots[0]["xlim"][1] >= 300.0


@pytest.mark.parametrize("chart_type", STACKED)
def test_separate_panels_partition_still_normalises(chart_type, monkeypatch):
    """The panel renderer's no-op guard."""
    shots = _render(chart_type, _panel_series(overlap=False), monkeypatch,
                    classifying_var="sex", classifying_var_2="age",
                    options={"xtab_layout": "separate"})
    assert len(shots) == 2
    for shot in shots:
        totals = _bar_totals(shot, "stacked_horizontal_bar", n_bars=3)
        assert all(abs(t - 100.0) < 1e-6 for t in totals), totals
        assert shot["xlim"] == (0.0, 100.0)
