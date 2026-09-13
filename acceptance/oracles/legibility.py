"""Oracle 4, first half: nothing is drawn too small to read.

There is no single font floor. The renderers enforce five, per path:

    label_fit._MIN_PT          7.5   category names
    bars._VALUE_LABEL_MIN_PT   7.5   vertical-bar value labels
    bars._GROUP_BLOCK_MIN_FS   7.5   group block labels
    bars._VALUE_MIN_PT         6.5   the stacked shrink floor
    bars.py:1367  max(5.5, …)  5.5   clustered-horizontal value labels

Knowing a text is a VALUE — which `VALUE_GID` now tells us — still does not pick
one, because the floor depends on which path drew it. A vertical bar's numbers
stop at 7.5pt and a clustered horizontal bar's at 5.5pt, and both are correct.

So this rule states only what is true of every text on every chart: below
`bars._MIN_LABEL_BAR_PT` (5.0pt) no path draws anything at all. It is weaker
than the per-kind rule, and it still catches the regression that matters — type
shrinking away until it is decoration rather than a figure anyone reads.

Unlike the overlap oracle's tolerance, this needs no dpi handling: a point size
is a point size at any resolution.

Names get a second, higher floor — `names_too_small` — and it needs no gids,
because a name is a tick label on a drawn axis. 7.5pt is `label_fit._MIN_PT`,
and it was measured before being trusted: across the customer's 60 charts the
smallest name drawn is **7.545pt** on a stacked horizontal bar, so real reports
come within 0.045pt of it. It is safe to encode because `label_fit` clamps with
`max(_MIN_PT, …)` and cannot emit less — a name below 7.5pt means the fitting
was bypassed, which is a defect rather than a threshold artefact.
"""
from __future__ import annotations

from dataclasses import dataclass

# The same census the overlap oracle uses: it already skips axes that are not
# drawn, which is what stops a word cloud's phantom tick labels being judged.
# Two oracles disagreeing about what counts as "a text on this figure" is a
# seam worth not having.
from oracles.census import drawn_texts

#: Below this, no renderer draws a label at all (`bars._MIN_LABEL_BAR_PT`), so
#: anything smaller was not a deliberate choice by any path.
FLOOR_PT: float = 5.0


@dataclass(frozen=True)
class Undersized:
    """A text drawn below the floor."""

    text: str
    points: float

    def __str__(self) -> str:  # pragma: no cover - reporting convenience
        return f"{self.text!r} at {self.points:g}pt"


#: What `label_fit` will never shrink a category name past (`_MIN_PT`).
NAME_FLOOR_PT: float = 7.5


def _undersized(artists, floor_pt: float) -> list[Undersized]:
    found: list[Undersized] = []
    for artist in artists:
        try:
            points = float(artist.get_fontsize())
        except Exception:  # noqa: BLE001 — an artist that cannot state its size
            continue
        if points < floor_pt:
            found.append(Undersized(text=artist.get_text(), points=points))
    found.sort(key=lambda u: u.points)
    return found


def too_small(fig, *, floor_pt: float = FLOOR_PT) -> list[Undersized]:
    """Every text drawn below *floor_pt*, smallest first."""
    return _undersized(drawn_texts(fig), floor_pt)


def _tick_labels(fig):
    """The names on the axes — and only where the axis is actually drawn.

    A word cloud's tick labels still report `get_visible() == True` over an
    `imshow`'d raster that hides them, so trusting visibility alone would judge
    type that nobody can see.
    """
    for ax in fig.axes:
        if not ax.axison:
            continue
        for labels in (ax.get_xticklabels(), ax.get_yticklabels()):
            for artist in labels:
                if artist.get_visible() and artist.get_text().strip():
                    yield artist


def names_too_small(fig, *, floor_pt: float = NAME_FLOOR_PT) -> list[Undersized]:
    """Every axis label below the name floor, smallest first.

    Value-axis ticks are judged by the same rule as category names: a reader
    has to read both, builders set them at 9.5pt, and no real chart measured
    puts any tick below 7.545pt — so holding them to 7.5 costs nothing.
    """
    return _undersized(_tick_labels(fig), floor_pt)
