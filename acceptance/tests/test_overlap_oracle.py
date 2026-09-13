"""The overlap oracle, proved against pictures that really are broken.

A gate that passes everything looks exactly like a gate that works, so every
rule here is shown a genuinely bad figure and required to complain about it —
and a good one, and required to stay quiet. The quiet half matters just as
much: this runs on every chart, and nearly all of them have nothing wrong.

The geometry has to be a real separating-axis test. Neither existing overlap
test is one — tests/suite/unit/render/test_category_labels_never_overlap.py
compares in ONE rectangle's frame (sound only because tick labels in a set
share a rotation) and test_value_labels_never_collide.py is a plain
axis-aligned box intersection. A stacked chart mixes flat numbers with rotated
names, which is exactly where both approximations go wrong.
(Johan, 2026-09-12)
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

import oracles.overlap as overlap


def _fig():
    fig = Figure(figsize=(6.0, 3.0), dpi=100)
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    return fig, ax


def test_it_finds_two_numbers_printed_on_top_of_each_other():
    """The customer's "4 %2 %": two numbers sharing a spot."""
    fig, ax = _fig()
    ax.text(50, 50, "4 %", ha="center", va="center", fontsize=9)
    ax.text(50, 50, "2 %", ha="center", va="center", fontsize=9)
    fig.canvas.draw()

    hits = overlap.collisions(fig)

    assert len(hits) == 1, hits
    assert {hits[0].a, hits[0].b} == {"4 %", "2 %"}


def test_it_stays_quiet_when_the_numbers_sit_clear():
    """The half that decides whether anyone trusts it: this runs on every
    chart, and nearly all of them have nothing wrong. A rule that cries on a
    good picture is worse than no rule."""
    fig, ax = _fig()
    for x in (10, 50, 90):
        ax.text(x, 50, "44 %", ha="center", va="center", fontsize=9)
    fig.canvas.draw()

    assert overlap.collisions(fig) == []


def test_two_slanted_names_that_merely_share_a_bounding_box_are_not_a_collision():
    """The case that decides the geometry.

    Two 45-degree labels offset PERPENDICULAR to the direction they run: the
    text does not touch, but the axis-aligned box around each is a big square
    and those squares overlap heavily. A plain bbox intersection calls this a
    defect; so does a test that compares in only one rectangle's frame when the
    two are rotated differently. Both are in tests/suite today, which is why
    this oracle computes its own separating axes.
    """
    fig, _ax = _fig()
    label = "Erittäin todennäköisesti"
    # 45 degrees runs along (0.707, 0.707); step across it, not along it.
    fig.text(0.500, 0.500, label, rotation=45, fontsize=9,
             ha="center", va="center")
    fig.text(0.476, 0.547, label, rotation=45, fontsize=9,
             ha="center", va="center")
    fig.canvas.draw()

    assert overlap.collisions(fig) == [], (
        "two slanted names standing clear of each other were reported as "
        "printed over each other")


def _two_numbers_grazing(dpi: int):
    """Two numbers stacked 98% of their own height apart: their boxes graze by
    2%, the shape adjacent clustered bars actually make."""
    fig = Figure(figsize=(6.0, 3.0), dpi=dpi)
    FigureCanvasAgg(fig)
    fig.text(0.5, 0.5, "35 %", ha="center", va="center", fontsize=5.5)
    fig.canvas.draw()
    box = fig.texts[0].get_window_extent(fig.canvas.get_renderer())
    frac = box.height / (fig.get_figheight() * dpi)
    fig.text(0.5, 0.5 - 0.98 * frac, "36 %", ha="center", va="center", fontsize=5.5)
    fig.canvas.draw()
    return fig


def test_boxes_that_merely_graze_are_not_a_collision_at_any_dpi():
    """Measured on the customer's own clustered bar: 31 of its rows put value
    labels at the 5.5pt floor, one row pitch apart, and every neighbouring pair
    interpenetrated by 0.59px — 0.211pt, about a fifth of a point, on digits
    that have no descenders. Nothing is printed over anything there.

    A tolerance counted in PIXELS also makes the answer depend on render
    resolution: the same picture at 110dpi and 200dpi gets different verdicts,
    and §Performance proposes changing exactly that constant. So the rule is
    relative to type size, and this asserts both halves — grazing is clear, and
    the verdict does not move with dpi.
    """
    at_200 = overlap.collisions(_two_numbers_grazing(200))
    at_400 = overlap.collisions(_two_numbers_grazing(400))

    assert len(at_200) == len(at_400), (
        f"the verdict changed with render dpi: {len(at_200)} at 200dpi, "
        f"{len(at_400)} at 400dpi")
    assert at_200 == [], at_200


def test_an_axis_that_is_not_drawn_contributes_no_obstacles():
    """A word cloud's shape: `ax.axis("off")` over an imshow'd raster.

    The tick labels still report `get_visible() == True` with real text
    (-0.5, 0.0, ...) while nothing of them is drawn, so a census that trusts
    `get_visible()` alone invents obstacles and fails every word cloud against
    its own picture. Mutation-checked: drop the `axison` filter and this figure
    alone contributes 14 phantom obstacles across its two tick-label sets.
    """
    fig = Figure(figsize=(4.0, 3.0), dpi=100)
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    ax.imshow([[1, 2], [3, 4]])
    ax.axis("off")
    fig.canvas.draw()

    counted = [t.get_text() for t in overlap._texts(fig)]

    assert counted == [], f"phantom obstacles from an axis that is not drawn: {counted}"
