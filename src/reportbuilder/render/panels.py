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

# A classifier group (or cross-tab combo) whose base is below this is SMALL: its
# percentages rest on few people, and the editor warns the author about it. It is
# still drawn, with its own base in its label ("Amazon (n=3)"). Until 2026-09-17
# such groups were not plotted at all — a number picked in development ("e.g. <
# 20, tunable"), never a methodology decision — and a 41-respondent study split
# by six companies lost every group without a word on the slide. Defined here (not in
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

    `thin` names the SMALL groups — under MIN_SEGMENT_BASE respondents. They are
    drawn like any other (since 2026-09-17; they used to be dropped) and named
    here so the editor can warn that their percentages rest on few people.
    `capped` groups fit the data but not the page, and are NOT drawn.
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
                 if 0 < series.base_n.get(s, 0) < MIN_SEGMENT_BASE)
    # Every group with respondents is drawn, small ones included — see
    # `series_values`. Only a group nobody is in has nothing to show.
    kept = [s for s in groups if series.base_n.get(s, 0) > 0]

    if not kept:
        # Nobody in any group. Fall back to the whole-sample segment rather than
        # to zero panels — a blank slide discloses nothing.
        return PanelSelection(labels=("Total",), thin=thin, degraded=True,
                              split=True)

    # The whole study as a panel of its own, when the author asks for it —
    # "Total next to 25–34-vuotiaat". First, where a reader looks for the
    # reference, and always kept: it is the one panel the author named for
    # itself rather than picked from a list, so a group gives way to it.
    # (2026-09-19)
    total = ("Total",) if (getattr(series, "total_panel", False)
                           and "Total" in series.segments) else ()
    room = MAX_PANELS - len(total)

    capped: tuple[str, ...] = ()
    if len(kept) > room:
        order = {s: i for i, s in enumerate(series.segments)}
        largest = set(sorted(kept, key=lambda s: (-series.base_n.get(s, 0),
                                                  order[s]))[:room])
        capped = tuple(s for s in kept if s not in largest)
        kept = [s for s in kept if s in largest]

    return PanelSelection(labels=total + tuple(kept), thin=thin, capped=capped,
                          split=True)
