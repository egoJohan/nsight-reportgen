"""Oracle 1: no text is printed over any other text.

The first duty of the suite, because it is the defect that keeps reaching us
from customers looking at a slide: names printed through each other, "4 %2 %"
where two numbers shared a spot.

Two things here are deliberately not reused from the existing regression tests,
both because they are approximations that a mixed chart breaks:

* **The geometry is a real separating-axis test.**
  `test_category_labels_never_overlap.py:114-121` transforms the centre delta
  into ONE rectangle's frame and compares half-extents — correct only when both
  share a rotation, which holds for tick labels in a set and fails for a
  rotated row name against a flat number.
  `test_value_labels_never_collide.py:86-88` is a plain axis-aligned box
  intersection, which overstates a rotated label's footprint badly.

* **The census is its own.** `label_fit._obstacles` lists what a category name
  must not hit, so it deliberately SKIPS the tick labels being fitted
  (`if (id(ax), axis) in named: continue`) and excludes legends by design.
  Those are exactly the pairs this oracle exists to check.

A rotated label's screen bbox is much larger than its text, so every box is
measured flat and carried with its own angle.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from oracles.census import drawn_texts

#: How deep two boxes must interpenetrate before it counts, as a fraction of
#: the SMALLER box's height.
#:
#: Relative, not a pixel count, for two measured reasons. A text's box includes
#: leading and side bearing well beyond its ink, so neighbouring labels graze
#: routinely on charts that read as perfectly clear: on the customer's own
#: clustered bar, 31 rows at the 5.5pt floor put every neighbouring pair
#: 0.59px — 0.211pt — into each other, which is 4.2% of a 14.0px box and
#: invisible. A genuine collision ("4 %2 %") is ~100% of the box.
#:
#: And a pixel threshold makes the verdict depend on render resolution: the
#: figure dpi is a product constant (`_new_agg_figure(..., dpi=200)`) that
#: §Performance proposes changing to 110, which would silently move every
#: answer. A fraction of a measured height cannot.
_GRAZE_FRACTION = 0.12


@dataclass(frozen=True)
class Collision:
    """Two texts that are printed over each other."""

    a: str
    b: str
    overlap_px: float

    def __str__(self) -> str:  # pragma: no cover - reporting convenience
        return f"{self.a!r} over {self.b!r} ({self.overlap_px:.1f}px)"


@dataclass(frozen=True)
class _Box:
    """An oriented rectangle: centre, its own flat size, and its angle."""

    text: str
    cx: float
    cy: float
    w: float
    h: float
    angle: float          # radians


def _oriented(artist, renderer) -> _Box | None:
    """The rectangle a text really occupies.

    Measured with the rotation removed and carried as an angle instead: a
    rotated label's `get_window_extent` is the axis-aligned box AROUND it,
    which is far bigger than the text and reads as colliding when it is not.
    """
    from matplotlib.text import Text

    try:
        deg = artist.get_rotation()
        # An annotation's own extent wraps its leader line, whose box covers
        # ground the line never touches. The NUMBER is what must not collide.
        if hasattr(artist, "xyann"):
            artist.update_positions(renderer)
            box = Text.get_window_extent(artist, renderer)
            artist.set_rotation(0)
            flat = Text.get_window_extent(artist, renderer)
        else:
            box = artist.get_window_extent(renderer)
            artist.set_rotation(0)
            flat = artist.get_window_extent(renderer)
        artist.set_rotation(deg)
    except Exception:  # noqa: BLE001 — an artist that cannot say where it is
        return None
    if flat.width <= 0 or flat.height <= 0:
        return None
    return _Box(text=artist.get_text(),
                cx=(box.x0 + box.x1) / 2, cy=(box.y0 + box.y1) / 2,
                w=flat.width, h=flat.height, angle=math.radians(deg))


def _gap_on(axis_angle: float, a: _Box, b: _Box) -> float:
    """Separation along one rectangle's axes; > 0 means a separating axis."""
    cs, sn = math.cos(axis_angle), math.sin(axis_angle)
    dx, dy = b.cx - a.cx, b.cy - a.cy
    u = abs(dx * cs + dy * sn)
    v = abs(-dx * sn + dy * cs)

    def _reach(box: _Box) -> tuple[float, float]:
        rel = box.angle - axis_angle
        c, s = abs(math.cos(rel)), abs(math.sin(rel))
        return ((box.w * c + box.h * s) / 2, (box.w * s + box.h * c) / 2)

    au, av = _reach(a)
    bu, bv = _reach(b)
    return max(u - (au + bu), v - (av + bv))


def _overlap_px(a: _Box, b: _Box) -> float:
    """How far two oriented rectangles interpenetrate; <= 0 when clear.

    Separating-axis test over BOTH rectangles' axes: if either finds daylight,
    they do not touch.
    """
    return -max(_gap_on(a.angle, a, b), _gap_on(b.angle, a, b))


#: The census moved to `oracles.census` once the legibility oracle needed the
#: same answer. Kept under the old name because the diagnostic probes call
#: `ov._texts(fig)` directly.
_texts = drawn_texts


def collisions(fig, *, graze_fraction: float = _GRAZE_FRACTION) -> list[Collision]:
    """Every pair of texts printed over each other, worst first."""
    renderer = fig.canvas.get_renderer()
    boxes = [b for b in (_oriented(t, renderer) for t in _texts(fig)) if b]

    hits: list[Collision] = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            deep = _overlap_px(a, b)
            # Scaled to the smaller box: the same absolute bite means something
            # different on 5.5pt numbers and a 24pt title.
            if deep > graze_fraction * min(a.h, b.h):
                hits.append(Collision(a=a.text, b=b.text, overlap_px=deep))
    hits.sort(key=lambda c: -c.overlap_px)
    return hits
