"""SeriesShape — a generic, principled description of a chart's data shape.

Chart plugins decide feasibility/suitability by reading *named structural
properties* of the data (how many series, are the categories a partition, are
they temporal, …) instead of ad-hoc numeric thresholds scattered through chart
code.  This module is generic: it describes the DATA, never a specific graph,
so adding a new chart type never requires touching it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from reportbuilder.stats.series import SeriesResult

# Category labels that look like a time axis (waves, years, Finnish months) →
# an ordered/temporal series for which a line chart is the natural default.
TIME_RE = re.compile(
    r"\b(20\d\d|q[1-4]|h[12]|wave|aalto|kuukausi|kuu|tammi|helmi|maalis|huhti"
    r"|touko|kesä|heinä|elo|syys|loka|marras|joulu)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SeriesShape:
    """Structural facts about a (question, series) pair, read by chart plugins."""

    n_series: int          # number of segments (series); 1 = one overall series
    n_categories: int      # number of category rows
    max_label_len: int     # longest category label (chars)
    is_multi: bool         # question is a multi-response (tick-box) set
    is_temporal: bool      # categories look like a time/wave axis
    is_partition: bool     # categories partition the base → parts-of-a-whole
    statistic: str         # "pct" | "count" | "mean"

    @classmethod
    def of(cls, question, series: SeriesResult) -> "SeriesShape":
        cats = list(series.categories)
        kind = getattr(question, "kind", None)
        return cls(
            n_series=series.n_series,
            n_categories=len(cats),
            max_label_len=max((len(c) for c in cats), default=0),
            is_multi=(kind == "multi"),
            is_temporal=any(TIME_RE.search(c) for c in cats),
            is_partition=series.is_partition(),
            statistic=series.statistic,
        )


# Statistics whose category values are additive parts of a whole (a pie/
# doughnut/100%-stack is only meaningful for these — never for a mean).
ADDITIVE_STATISTICS = frozenset({"pct", "count"})
