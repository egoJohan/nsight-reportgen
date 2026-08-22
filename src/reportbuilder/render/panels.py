"""Which classifier groups become panels on a single-series chart (pie, doughnut,
funnel) — the ONE answer, read by every caller that needs it.

Four things depend on this question: the feasibility check that decides whether a
pie is offered at all, the renderer that draws the panels, the methodology footer
that names what was left out, and the tests that assert on all three. If any two
answered it separately they would drift, and the tool would offer a chart it then
draws differently. So the rule lives here and nothing re-derives it.

(spec 2026-08-22-multi-pie-panels-design)
"""
from __future__ import annotations

from dataclasses import dataclass

# A classifier segment (or cross-tab combo) whose base is below this is too small
# to chart — its percentages would be noise (a "won't say" group of 1 -> 100%). The
# engine still computes it exactly; we just don't PLOT it. Defined here (not in
# image._mpl) so this module has no dependency on the image package — `panels` is
# imported by callers (the pie/doughnut suitability check, native builders) that
# must not have to pull in matplotlib-backed rendering just to ask this question.
# image._mpl imports it back from here. Tunable.
MIN_SEGMENT_BASE = 10

# Three circles is what a 4:3 slot holds while each stays readable. A fourth is the
# case the feature exists to prevent, not a layout to support.
MAX_PANELS: int = 3


@dataclass(frozen=True)
class PanelSelection:
    """The panels to draw, plus every group that will NOT be drawn and why.

    `thin` and `capped` are kept apart because they mean different things to a
    reader: a thin group could not be reported at all, while a capped group fits
    the data but not the page.
    """

    labels: tuple[str, ...]
    thin: tuple[str, ...] = ()
    capped: tuple[str, ...] = ()
    degraded: bool = False
    split: bool = False


def panel_segments(series) -> PanelSelection:
    """Resolve `series` into the panels a single-series chart should draw."""
    groups = tuple(s for s in series.segments if s != "Total")
    if not groups:
        # No classifier: the lone segment IS the chart, exactly as before.
        return PanelSelection(labels=series.segments[:1])

    thin = tuple(s for s in groups
                 if series.base_n.get(s, 0) < MIN_SEGMENT_BASE)
    kept = [s for s in groups if s not in thin]

    if not kept:
        # Everything is too thin to report. Fall back to the whole-sample segment
        # rather than to zero panels — a blank slide discloses nothing.
        return PanelSelection(labels=("Total",), thin=thin, degraded=True,
                              split=True)

    capped: tuple[str, ...] = ()
    if len(kept) > MAX_PANELS:
        order = {s: i for i, s in enumerate(series.segments)}
        largest = set(sorted(kept, key=lambda s: (-series.base_n.get(s, 0),
                                                  order[s]))[:MAX_PANELS])
        capped = tuple(s for s in kept if s not in largest)
        kept = [s for s in kept if s in largest]

    return PanelSelection(labels=tuple(kept), thin=thin, capped=capped,
                          split=True)
