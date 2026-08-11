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

    def cell(self, category: str, segment: str) -> Cell:
        return self.cells[(category, segment)]

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
