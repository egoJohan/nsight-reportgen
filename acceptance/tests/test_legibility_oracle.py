"""Oracle 4, first half: nothing is drawn too small to read.

The spec used to say "no font below its floor (7.5pt names, 6.5pt numbers)".
That is wrong: the renderers enforce FIVE floors, per path —

    label_fit._MIN_PT          7.5   category names
    bars._VALUE_LABEL_MIN_PT   7.5   vertical-bar value labels
    bars._GROUP_BLOCK_MIN_FS   7.5   group block labels
    bars._VALUE_MIN_PT         6.5   the stacked shrink floor
    bars.py:1367  max(5.5, …)  5.5   clustered-horizontal value labels

— and the customer's own clustered bar draws at 5.5pt, so a rule encoding
"6.5pt numbers" would fail a correct chart on its first run.

Knowing a text is a VALUE (its gid) still does not pick a floor, because the
floor depends on which path drew it. So this rule is the weakest TRUE statement:
nothing below `bars._MIN_LABEL_BAR_PT` (5.0pt), the point past which no path
draws anything at all. It still catches the regression that matters — type
shrinking away to nothing.

The 7.5pt rule for category names is deliberately NOT here yet: it needs
measuring against real charts first, the way the overlap oracle's tolerance did.
(Johan, 2026-09-12)
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

import oracles.legibility as legibility


def _fig(*sizes: float):
    """A figure carrying one text at each of the given point sizes."""
    fig = Figure(figsize=(6.0, 3.0), dpi=200)
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    for i, pt in enumerate(sizes):
        ax.text(10 + i * 20, 50, f"{pt:g} %", fontsize=pt, ha="center")
    fig.canvas.draw()
    return fig


def test_it_finds_type_shrunk_past_the_floor():
    """4pt is not a number anyone reads; it is decoration."""
    found = legibility.too_small(_fig(9.5, 4.0))

    assert len(found) == 1, found
    assert found[0].points == 4.0
    assert found[0].text == "4 %"


def test_it_stays_quiet_at_the_sizes_real_charts_use():
    """The half that decides whether anyone trusts it. 5.5pt is what the
    customer's clustered bar actually draws, and it is correct — a rule that
    flags it is a rule that gets switched off."""
    assert legibility.too_small(_fig(11.5, 9.5, 7.5, 6.5, 5.5)) == []


def _named_axis(points: float):
    """An axis whose category names are set at *points*."""
    fig = Figure(figsize=(6.0, 3.0), dpi=200)
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Erittäin todennäköisesti", "Melko epätodennäköisesti"],
                       fontsize=points)
    fig.canvas.draw()
    return fig


def test_a_category_name_below_the_name_floor_is_reported():
    """Names have a floor of their own, and it is higher than a number's.

    `label_fit` shrinks long names down a ladder and clamps at `_MIN_PT` (7.5),
    so it can never emit less — a name below 7.5pt means the fitting was
    bypassed. Measured across the customer's 60 charts, the smallest name drawn
    is 7.545pt on a stacked horizontal bar: real reports come within 0.045pt of
    this floor, which is what makes it the right number rather than a guess.
    """
    found = legibility.names_too_small(_named_axis(6.0))

    assert len(found) == 2, found
    assert all(u.points == 6.0 for u in found), found


def test_names_at_the_floor_are_left_alone():
    """7.5pt is legible and is exactly what a crowded battery settles at."""
    assert legibility.names_too_small(_named_axis(7.5)) == []
