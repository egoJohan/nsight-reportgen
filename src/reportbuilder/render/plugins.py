"""ChartPlugin registry — graph styles as plugins (REQ-C-13, R2 task A).

Each chart type is registered as a :class:`ChartPlugin` that carries its
image_build and native_build callables, a human label, a suitability scorer,
and an optional ``requires`` tuple for special prerequisites (e.g. scatter_xy).

Usage::

    from reportbuilder.render.plugins import plugin, suggest_chart_type
    builder = plugin("horizontal_bar").image_build
    default  = suggest_chart_type(question, series)

The module is imported for side-effects by ``deck.py``; the plugins dict is
populated at import time from the existing NATIVE_BUILDERS / IMAGE_BUILDERS
backing dicts, which remain intact so legacy coverage tests keep passing.

Suitability rules
-----------------
horizontal_bar   : high when > 6 categories or any label > 14 chars
vertical_bar     : high when ≤ 6 categories with short labels
stacked_v/h_bar  : high for Likert-like distributions (≥ 4 response options)
line             : high when categories look like time labels (waves, years)
pie / doughnut   : parts-of-whole ONLY — returns None for multi-response
radar            : high for multi-dimensional profiles (≥ 4 attributes)
funnel           : high for ordered-descending single-series
scatter          : always None (requires explicit scatter_xy, no auto-suggest)
combo            : moderate for dual-axis comparison

``suggest_chart_type`` returns the chart_type with the highest suitability
score → used as the wizard default picker.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from reportbuilder.stats.series import SeriesResult

# ---------------------------------------------------------------------------
# Plugin dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChartPlugin:
    id: str                         # canonical chart_type key
    label: str                      # human label for UI
    image_build: Callable | None    # ctx -> None (matplotlib, house style)
    native_build: Callable | None   # ctx -> graphic frame (OOXML)
    suitability: Callable           # (question, series) -> float | None
    requires: tuple[str, ...] = ()  # e.g. ("scatter_xy",) — prerequisites


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CHART_PLUGINS: dict[str, ChartPlugin] = {}


def register(p: ChartPlugin) -> None:
    """Register a ChartPlugin in the global registry."""
    CHART_PLUGINS[p.id] = p


def plugin(chart_type: str) -> ChartPlugin:
    """Return the ChartPlugin for *chart_type*.

    Raises KeyError for unknown types.
    """
    try:
        return CHART_PLUGINS[chart_type]
    except KeyError:
        raise KeyError(
            f"No ChartPlugin registered for chart_type={chart_type!r}. "
            f"Known types: {sorted(CHART_PLUGINS)}"
        )


def suggest_chart_type(question, series: SeriesResult) -> str:
    """Return a chart_type for *question* using question-shape heuristics (R4.3).

    Shape-based approach: the suggestion is driven by what the question *is*
    (kind, category count, label lengths) rather than by synthetic data values.
    This prevents false funnel suggestions when values happen to be equal/ordered.

    Funnel, radar, and scatter are NEVER auto-suggested — they are opt-in chart
    types that require deliberate selection.

    Rules (applied in order of precedence):
    - multi-response (tickbox set)               → horizontal_bar
    - categories contain time/wave labels        → line
    - > 6 categories or any label > 14 chars     → horizontal_bar
    - single segment AND ≤ 4 categories          → pie
    - default (few short labels)                 → vertical_bar
    """
    kind = getattr(question, "kind", "single")
    cats = list(series.categories)
    segs = list(series.segments)

    # multi-response → always horizontal bar (many categories, one checkbox each)
    if kind == "multi":
        return "horizontal_bar"

    # time-wave labels → line chart
    if any(_TIME_RE.search(c) for c in cats):
        return "line"

    # many categories or long labels → horizontal bar for readability
    if len(cats) > 6 or any(len(c) > 14 for c in cats):
        return "horizontal_bar"

    # parts-of-whole: single segment with few categories → pie
    if len(segs) == 1 and len(cats) <= 4:
        return "pie"

    # default: vertical bar for few short labels
    return "vertical_bar"


# ---------------------------------------------------------------------------
# Suitability helpers
# ---------------------------------------------------------------------------

_TIME_RE = re.compile(
    r"\b(20\d\d|q[1-4]|h[12]|wave|aalto|kuukausi|kuu|tammi|helmi|maalis|huhti"
    r"|touko|kesä|heinä|elo|syys|loka|marras|joulu)\b",
    re.IGNORECASE,
)


def _cats(series: SeriesResult) -> list[str]:
    return list(series.categories)


def _segs(series: SeriesResult) -> list[str]:
    return list(series.segments)


def _suit_horizontal_bar(question, series: SeriesResult) -> float:
    """High for many (>6) or long labels (any >14 chars); always applicable."""
    cats = _cats(series)
    if len(cats) > 6 or any(len(c) > 14 for c in cats):
        return 0.85
    return 0.55


def _suit_vertical_bar(question, series: SeriesResult) -> float:
    """High for few (≤6) short labels; lower for many/long categories."""
    cats = _cats(series)
    if len(cats) <= 6 and all(len(c) <= 14 for c in cats):
        return 0.80
    return 0.35


def _suit_stacked_vertical(question, series: SeriesResult) -> float:
    """High for Likert/ordered distributions (≥4 response options)."""
    cats = _cats(series)
    if len(cats) >= 4:
        return 0.75
    return 0.40


def _suit_stacked_horizontal(question, series: SeriesResult) -> float:
    """High for multi-group comparisons or Likert-like (≥4 options, multi-seg)."""
    cats = _cats(series)
    segs = _segs(series)
    if len(segs) > 1 and len(cats) >= 2:
        return 0.80
    if len(cats) >= 4:
        return 0.70
    return 0.40


def _suit_line(question, series: SeriesResult) -> float:
    """High when categories contain time/wave labels (ordered trend)."""
    cats = _cats(series)
    if any(_TIME_RE.search(c) for c in cats):
        return 0.90
    # Also reasonable for ≥3 ordered categories even without time labels
    if len(cats) >= 3:
        return 0.60
    return 0.35


def _suit_pie(question, series: SeriesResult) -> float | None:
    """Parts-of-whole ONLY: None for multi-response (multi kind)."""
    kind = getattr(question, "kind", None)
    if kind == "multi":
        return None  # pie is not appropriate for multi-response
    segs = _segs(series)
    cats = _cats(series)
    if len(segs) > 1:
        return None  # pie is single-segment only
    if len(cats) <= 6:
        return 0.75
    return 0.50


def _suit_doughnut(question, series: SeriesResult) -> float | None:
    """Same rules as pie."""
    return _suit_pie(question, series)


def _suit_radar(question, series: SeriesResult) -> float:
    """High for multi-dimensional profiles (≥4 attributes)."""
    cats = _cats(series)
    if len(cats) >= 4:
        return 0.80
    return 0.40


def _suit_funnel(question, series: SeriesResult) -> float:
    """High for ordered-descending single-series (awareness-funnel shape)."""
    cats = _cats(series)
    segs = _segs(series)
    if len(segs) != 1 or len(cats) < 3:
        return 0.30
    # Check if values are roughly descending
    stat = series.statistic
    vals = [series.cell(c, segs[0]).value(stat) or 0.0 for c in cats]
    is_desc = all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
    return 0.85 if is_desc else 0.50


def _suit_scatter(question, series: SeriesResult) -> float | None:
    """Always None — scatter requires explicit scatter_xy configuration."""
    return None


def _suit_combo(question, series: SeriesResult) -> float:
    """Moderate for dual-axis comparison (multi-series)."""
    segs = _segs(series)
    if len(segs) >= 2:
        return 0.60
    return 0.30


def _suit_wordcloud(question, series: SeriesResult) -> None:
    """Always None — word cloud is never auto-suggested for normal questions.

    Free-text questions get the wordcloud type explicitly via the questions route
    (Task J.3), not through generic suitability; returning None keeps it out of the
    compatible-types list for non-text questions (Task J.2)."""
    return None


# ---------------------------------------------------------------------------
# Registration — wrap the existing NATIVE_BUILDERS / IMAGE_BUILDERS
# ---------------------------------------------------------------------------
# Import backing dicts here (they remain unchanged for legacy test compatibility)

from reportbuilder.render.native import NATIVE_BUILDERS as _NB  # noqa: E402
from reportbuilder.render.image import IMAGE_BUILDERS as _IB      # noqa: E402

_PLUGINS_SPEC: list[tuple[str, str, Callable, tuple[str, ...]]] = [
    # (id,                     label,                        suitability,             requires)
    ("vertical_bar",           "Vertical Bar",               _suit_vertical_bar,      ()),
    ("horizontal_bar",         "Horizontal Bar",             _suit_horizontal_bar,    ()),
    ("stacked_vertical_bar",   "Stacked Vertical Bar",       _suit_stacked_vertical,  ()),
    ("stacked_horizontal_bar", "Stacked Horizontal Bar",     _suit_stacked_horizontal,()),
    ("line",                   "Line Chart",                 _suit_line,              ()),
    ("pie",                    "Pie Chart",                  _suit_pie,               ()),
    ("doughnut",               "Doughnut Chart",             _suit_doughnut,          ()),
    ("radar",                  "Radar Chart",                _suit_radar,             ()),
    ("scatter",                "Scatter Plot",               _suit_scatter,           ("scatter_xy",)),
    ("funnel",                 "Funnel Chart",               _suit_funnel,            ()),
    ("combo",                  "Combo Chart",                _suit_combo,             ()),
    ("wordcloud",              "Word Cloud",                 _suit_wordcloud,         ()),
]

for _id, _label, _suit, _req in _PLUGINS_SPEC:
    register(ChartPlugin(
        id=_id,
        label=_label,
        image_build=_IB.get(_id),
        native_build=_NB.get(_id),
        suitability=_suit,
        requires=_req,
    ))

del _id, _label, _suit, _req  # clean up loop vars
