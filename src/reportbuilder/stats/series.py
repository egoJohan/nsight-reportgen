"""SeriesResult — the sole numeric contract every renderer/export reads (design §7)."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Cell:
    pct: float | None = None        # 0..100
    count: float | None = None
    mean: float | None = None
    extra: tuple[tuple[str, float | None], ...] = ()  # registered non-core stat values

    def value(self, stat: str) -> float | None:
        """Return the cell value for the given statistic name."""
        if stat in ("pct", "count", "mean"):
            return getattr(self, stat)
        return dict(self.extra).get(stat)


# The ONE asymmetric partition allowance, shared by every caller that must decide
# "do these categories really partition the base?" on real survey data rather than
# assert an exact shape: a percent-of-base SHORTFALL up to this much is ordinary
# (a small "no answer"/other slice counted in the base but not named among the
# categories — an audit of the store's saved charts found ~50 legitimate
# single-choice questions at 98-99.8% of base), while OVERSHOOT gets no slack at
# all (see `is_partition`). Kept here, next to the predicate, so the offering side
# (`render/charts/pie.py`) and the renderer (`render/image/bars.py`) cannot drift
# into two differently-tuned rules for the same question.
PARTITION_UNDERSHOOT_TOL_PCT = 3.0


@dataclass(frozen=True)
class SeriesResult:
    categories: tuple[str, ...]               # row labels, already in final sort order
    # Column labels. Usually ends with a "Total" reference column, but NOT always:
    # the SEPARATE layout (one panel per classifying variable) emits a per-variable
    # "<variable> · Total" instead, because a bare overall Total belongs to no panel.
    # Read a segment's presence, never assume it. (spec 2026-08-04)
    segments: tuple[str, ...]
    cells: dict[tuple[str, str], Cell]        # (category, segment) -> Cell
    # segment -> N (REQ-C-24h). "Total" is ALWAYS a key here — the slide's N footer
    # indexes it directly — even where "Total" is not one of `segments`. (2026-08-04)
    base_n: dict[str, int]
    statistic: str                            # "pct" | "count" | "mean"
    # What an INDIVIDUAL segment measures, where that differs from `statistic`
    # above. Only the two-variable combo needs it so far: its bars are the
    # question's distribution and its line is the mean of another variable, so
    # one word cannot describe both. The mean was formatted as a percentage and
    # a 1-8 work-life index printed as "7.5 %".
    #
    # None means "every segment is `statistic`", which is every other chart.
    # Read it with `statistic_of(segment)`, never directly — a renderer that
    # indexes it has to handle both the None and the missing-key case itself,
    # and forgetting either brings the percent sign back. (Johan, 2026-09-16)
    segment_statistics: dict[str, str] | None = None
    # The segments that are a combo's SECONDARY VARIABLE, as opposed to the
    # question's own series. Recorded because it cannot always be read off the
    # statistics: a categorical secondary is drawn as the share of one of its
    # groups, a percentage like the bars beside it, so "measures something
    # else" finds nothing and the renderer fell back to guessing by position.
    # Empty for every chart that has no secondary variable. (Johan, 2026-09-17)
    secondary_segments: tuple[str, ...] = ()
    # Optional caption rendered under the chart — e.g. the endpoint legend of a
    # partially-labelled numeric scale ("1 = täysin eri mieltä · 7 = …"). (REQ-C-24c)
    caption: str | None = None
    # Cross-tab only: maps each combo segment ("Mies · 18-30") to its PRIMARY classifier
    # group ("Mies"), so renderers can group the bars/stacks by primary with gaps. None
    # for single-classifier / non-classifier charts. (REQ-C-14c)
    segment_primary: dict[str, str] | None = None
    # Optional right-hand summary value per bar (row_summary feature). None when off.
    # `row_summary_keys` names the bar each value belongs to: the renderer drops bars
    # (a near-empty classifier group, a hidden "Total"), so the values must be looked
    # up by label, never zipped positionally. (spec 2026-07-07)
    row_summaries: tuple[float, ...] | None = None
    row_summary_keys: tuple[str, ...] = ()
    # Whether the "Total" reference series should be drawn. False → renderers drop the
    # "Total" segment (unless it's the only series). Resolved by the engine from
    # ChartSpec.show_total + the percentage direction. (2026-07-10)
    show_total: bool = True
    # Whether a one-panel-per-group chart (pie, doughnut, funnel) draws the
    # whole study as a panel of its own. Explicit rather than read off
    # `show_total`, whose default is True for every series built without the
    # engine: a pie gains a panel only when its author ticked the Total.
    # (2026-09-19)
    total_panel: bool = False
    # The classifier groups the rows were actually NARROWED to, or (). Recorded
    # by the engine because only it knows: a selection naming a group the data
    # no longer has is ignored and the slide is the whole sample, and a slide
    # that then printed the name beside a base covering everyone was asserting
    # something untrue about itself. The renderer says what happened, not what
    # was asked for.
    applied_filter: tuple[str, ...] = ()
    # Whether the segments are GROUPS of people — a classifier's values, or
    # "Total" — as opposed to a battery's statements drawn as bars. Only the
    # engine knows: a battery asked of one group names its bars by statement,
    # though the chart names a classifier. A group is labelled with its base
    # ("Naiset (n=501)"); a statement is not a group and is not. (2026-09-11)
    segments_are_groups: bool = True

    def cell(self, category: str, segment: str) -> Cell:
        return self.cells[(category, segment)]

    def statistic_of(self, segment: str) -> str:
        """What *segment* measures — its own statistic where it has one, the
        series' otherwise. The single place that knows how to read
        `segment_statistics`; see the note on that field."""
        if not self.segment_statistics:
            return self.statistic
        return self.segment_statistics.get(segment, self.statistic)

    @property
    def n_series(self) -> int:
        """Number of segments (series). 1 = a single overall series."""
        return len(self.segments)

    def is_partition(self, segment: str | None = None, *, tol: float = 1.0,
                     undershoot_tol: float | None = None) -> bool:
        """True when *segment*'s categories partition its base: every counted
        unit falls in exactly one category (mutually exclusive AND exhaustive).

        This is the structural precondition for a pie/doughnut — "parts of one
        whole". Because the multi-response base is "respondents with >=1
        selection" (not total selections), a partition is exactly: the category
        counts sum to the base.  Single-choice questions satisfy this by
        construction; a multi-response set satisfies it only when respondents
        effectively chose one option (no overlap).

        Prefers exact integer counts; falls back to the percentage shares
        (sum ~= 100%) when counts are absent.  ``tol`` absorbs float/rounding
        noise only on BOTH sides — it is not slack for genuine overlap — and is
        the only check that runs when ``undershoot_tol`` is left at its default
        (None): the strict, symmetric predicate every caller gets unless it
        explicitly opts into the asymmetric one below.

        ``undershoot_tol``, when given, is a SEPARATE, wider allowance for
        shortfall only (the sum falling below the base / 100%), expressed as
        "percent of the base" so it means the same thing whether the check is
        running on raw counts or on percentages. Real single-choice survey
        data commonly excludes a small "no answer"/other slice from the named
        categories while still counting those respondents in the base — a
        shortfall of a few tenths of a percent up to ~2% is ordinary and,
        once a pie/doughnut renormalises to fill the circle, invisible. It
        deliberately does NOT loosen the overshoot side (still bound by
        ``tol``): overshoot is exactly what flags genuine multi-response
        overlap (a real defect — a pie would double-count / silently
        renormalise the true numbers away), so widening it would hide the
        thing this check exists to catch. Callers that offer a chart type
        rather than assert an exact shape (e.g. ``render/charts/pie.py``)
        should pass this explicitly, with a comment — never rely on a change
        to this method's default to get it.
        """
        seg = segment if segment is not None else (
            self.segments[0] if self.segments else None
        )
        if seg is None:
            return False
        base = self.base_n.get(seg)
        if not base:
            return False
        counts: list[float | None] = []
        pcts: list[float | None] = []
        for cat in self.categories:
            cell = self.cells.get((cat, seg))
            if cell is None:
                return False
            counts.append(cell.count)
            pcts.append(cell.pct)

        def _within(total: float, whole: float) -> bool:
            diff = total - whole  # > 0 overshoot (overlap); < 0 undershoot
            if diff > tol:
                return False
            if undershoot_tol is not None:
                return diff >= -(undershoot_tol / 100.0) * whole
            return diff >= -tol

        if counts and all(c is not None for c in counts):
            return _within(float(sum(counts)), float(base))  # type: ignore[arg-type]
        if pcts and all(p is not None for p in pcts):
            return _within(float(sum(pcts)), 100.0)  # type: ignore[arg-type]
        return False


def shown_segment(spec, series: "SeriesResult", name: str) -> str:
    """The segment a SAVED group name refers to, once the legend renames apply.

    Settings that name a group — the scatter's X and Y — keep the name the data
    gave it, while the series carries the name the author gave it in the legend.
    The renamed name when the series has it, else the name as given: a rename
    that was not applied (a clash, "Total") leaves the series under its own.
    (2026-09-17)
    """
    renames = (spec.series_label_override_map()
               if hasattr(spec, "series_label_override_map") else {})
    renamed = renames.get(name)
    return renamed if renamed and renamed in series.segments else name
