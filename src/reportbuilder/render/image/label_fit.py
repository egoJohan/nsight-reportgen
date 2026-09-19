"""Category names never print on top of each other.

A builder names its categories at a size and a wrap it picks before it knows
how much room a row or a column will get. The Taffel battery is what that looks
like when the guess is wrong: thirteen statements wrapped at 30 characters and
set at 11.5pt, in rows 18pt apart. Two lines of 11.5pt need 28, and six pairs
were printed through each other at every slide size. (Johan, 2026-09-11)

So the guess is checked against the finished figure. A builder that names
categories says so with `register_category_labels`; `render_png` then calls
`fit_category_labels`, which measures every registered label where it is drawn
and — only if one touches another, or the legend, a title, a group label, a
neighbouring panel, the value axis's numbers — sets them again, preferring:

1. the same size, wrapped differently: wider, so a row name takes one line
   instead of two; narrower, so a name under a column stops reaching its
   neighbour;
2. a step smaller (10% at a time, never below `_MIN_PT`), with those wraps again;
3. last, cut to the lines there is room for, with an ellipsis.

The first setting that touches nothing is kept. When none does, the one that
touches least is — and never one worse than what the builder drew.

A legend under the chart is not in the names' way: once they are settled, a
legend they run into is lowered until it clears them. The names are what a
reader needs beside the bars; the legend can go lower.

A figure whose labels already sit clear is left exactly as drawn. This runs on
every chart, and nearly all of them have nothing to fix.

Labels are compared as the rectangles they really are. A name under a column is
rotated, and its screen box is far bigger than its text: side by side, two such
boxes overlap when the names do not.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Iterator, Sequence

from reportbuilder.render.image._mpl import wrap_label, wrap_label_capped

_ATTR = "_nsight_category_labels"
#: The smallest a category name is set to. Below this a slide is not read.
_MIN_PT: float = 7.5
_STEP: float = 0.9
#: Wraps tried at each size, as multiples of the builder's own width — wider
#: first (fewer lines, what a row name needs), narrower last (what a name set
#: flat under a column needs).
_WIDTHS: tuple[float, ...] = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 0.8, 0.65)
#: How deep a label band may grow, as a share of the figure. The saved picture is
#: cropped to what is drawn and then fitted to the slot, so a band that grows
#: shrinks the whole chart on the slide; past this, smaller type is the better
#: trade. Never shallower than the builder drew it.
_GROW: dict[str, float] = {"y": 0.34, "x": 0.30}
_TOL: float = 0.5   # px: boxes that merely touch do not collide
#: Clear space each name keeps from another NAME, in units of its own type size.
#: Not touching is not enough: flush against each other, "…hintaan kuin
#: Estrella" and "laskisi kilohintaa" read as one name. Two of these make the
#: space between names twice the leading within one (0.2 em at matplotlib's 1.2
#: line spacing), which is what tells the eye where one ends.
_GAP_EM: float = 0.2
#: Clear space between the lowest name and a legend lowered out of its way.
_LEGEND_GAP_PT: float = 6.0


@dataclass
class _Entry:
    ax: object
    axis: str                         # "x" or "y"
    raw: tuple[str, ...]              # full text per tick; "" = blank on purpose
    wrap: Callable[[str, int], str]
    width: int                        # chars per line the builder wrapped at

    def labels(self) -> list:
        got = self.ax.get_yticklabels() if self.axis == "y" else self.ax.get_xticklabels()
        return [t for t in got if t.get_visible() and t.get_text().strip()]

    def set(self, texts: Sequence[str], fontsize: float) -> None:
        getattr(self.ax, f"set_{self.axis}ticklabels")(list(texts), fontsize=fontsize)


def register_category_labels(ax, axis: str, raw: Sequence[str], *,
                             wrap: Callable[[str, int], str] = wrap_label,
                             width: int | None = None) -> None:
    """Mark `ax`'s `axis` tick labels as category NAMES, which the fit may set again.

    `raw` is the full text for each tick, in tick order ("" for a tick the builder
    blanks on purpose). `wrap(text, width)` is how the builder wraps, and `width`
    the width it wrapped at — None when it does not wrap at all. Value axes are
    never registered: their numbers are not the builder's guess to correct."""
    raw = tuple("" if s is None else str(s) for s in raw)
    base = width or max((len(s) for s in raw), default=1)
    entries = getattr(ax.figure, _ATTR, None)
    if entries is None:
        entries = []
        setattr(ax.figure, _ATTR, entries)
    entries.append(_Entry(ax, axis, raw, wrap, max(1, int(base))))


def names_flat_unless_they_cannot_be(fig, ax, raw: Sequence[str], *, fontsize: float,
                                     color, width: int,
                                     wrap: Callable[[str, int], str] = wrap_label,
                                     rotation: float = 30.0,
                                     rotated_fontsize: float | None = None) -> bool:
    """Name the columns along `ax`'s x axis flat, and rotate them only as a last resort.

    Every column builder rotated its names unconditionally: two names,
    "Mieheksi" and "Naiseksi", under columns half the slide wide, were printed
    at 30 degrees, and "Muualla Etelä-Suomessa" came out wrapped AND rotated.
    The combo stopped doing that first (it tries flat and lets the fitter have
    its turn); this is the same rule in one place, for every builder.

    Flat is kept only when the fitter makes every name stand clear WITHOUT
    cutting one — a flat row of "Alennukset…" x5 is worse than the rotated
    names in full. Otherwise the names are set exactly as the builders always
    set them: wrapped at `width`, rotated by `rotation`. Either way they are
    registered, so `render_png` fits them once more. Returns True when flat.
    (visual QA, 2026-09-19)
    """
    raw = tuple("" if s is None else str(s) for s in raw)
    shown = [wrap(s, width) if s else "" for s in raw]
    # Flat, a name is wrapped to its COLUMN: as many characters as fit in most
    # of one column's width. `width` is the rotated names' wrap, and the fitter
    # tries wider before narrower — started from it, a row of one-line names
    # was accepted a hair apart, "…lääni Oulun lääni Mikkelin lääni…", which
    # reads as one name running along the axis.
    x0, x1 = ax.get_xlim()
    pitch_px = ax.bbox.width / max(abs(x1 - x0), 1e-6)
    char_px = 0.55 * fontsize * fig.dpi / 72.0
    flat_width = max(6, int(0.85 * pitch_px / char_px))
    ax.set_xticklabels([wrap(s, flat_width) if s else "" for s in raw],
                       fontsize=fontsize, color=color, rotation=0, ha="center")
    register_category_labels(ax, "x", raw, wrap=wrap, width=flat_width)
    registry = getattr(fig, _ATTR)
    entry = registry[-1]
    if _usable(entry):
        fig.draw_without_rendering()
        r = fig.canvas.get_renderer()
        _refit(fig, [entry], r)
        clear = _touching([entry], _obstacles(fig, [entry], r), r) == 0
        # Cut short, or a word chopped in two by the narrowest wraps
        # ("Ammatt / itaito / inen"): either way a name the reader cannot read.
        cut = any(("…" in t.get_text() and "…" not in s)
                  or not set(s.split()) <= set(t.get_text().replace("-\n", "-").split())
                  for t, s in zip(_axis(entry).get_ticklabels(), raw))
        if clear and not cut:
            return True
    registry.remove(entry)
    ax.set_xticklabels(shown, fontsize=rotated_fontsize or fontsize, color=color,
                       rotation=rotation, ha="right", rotation_mode="anchor")
    register_category_labels(ax, "x", raw, wrap=wrap, width=width)
    return False


def fit_category_labels(fig) -> None:
    """Set the registered category names again if any of them collide, then
    lower any legend they still run into. See module."""
    entries = [e for e in getattr(fig, _ATTR, ()) if _usable(e)]
    if not entries:
        return
    r = fig.canvas.get_renderer()
    _refit(fig, entries, r)
    _clear_legends(fig, entries, r)


def _refit(fig, entries, r) -> None:
    obstacles = _obstacles(fig, entries, r)
    worst = _touching(entries, obstacles, r)
    if not worst:
        return
    drawn = [_as_drawn(e) for e in entries]
    caps = [_cap(e, r, fig) for e in entries]
    best, best_hits = None, worst
    for setting in _settings(entries, [size for _t, size in drawn]):
        _apply(entries, setting)
        hits = _touching(entries, obstacles, r, caps)
        if hits == 0:
            return
        if hits is not None and hits < best_hits:
            best, best_hits = setting, hits
    _apply(entries, best if best is not None else drawn)


# ── the settings tried ───────────────────────────────────────────────────────

def _axis(e: _Entry):
    return e.ax.yaxis if e.axis == "y" else e.ax.xaxis


def _usable(e: _Entry) -> bool:
    return len(_axis(e).get_majorticklocs()) == len(e.raw)


def _as_drawn(e: _Entry) -> tuple[tuple[str, ...], float]:
    """What the builder set, to put back if nothing tried is better. Read off the
    ticks: matplotlib keeps the strings in whichever formatter it chose."""
    axis = _axis(e)
    ticks = axis.get_major_ticks(len(axis.get_majorticklocs()))
    shown = e.labels()
    size = shown[0].get_fontsize() if shown else 10.0
    return tuple(tk.label1.get_text() for tk in ticks), size


def _apply(entries, setting) -> None:
    for e, (texts, size) in zip(entries, setting):
        e.set(texts, size)


def _settings(entries, sizes) -> Iterator[list[tuple[tuple[str, ...], float]]]:
    scales = [1.0]
    while any(sz * scales[-1] > _MIN_PT for sz in sizes):
        scales.append(scales[-1] * _STEP)

    def pt(sz: float, scale: float) -> float:
        return sz if sz <= _MIN_PT else max(_MIN_PT, sz * scale)

    def width(e: _Entry, mult: float) -> int:
        return max(6, round(e.width * mult))

    seen: set = set()

    def fresh(setting) -> bool:
        key = tuple((texts, round(size, 3)) for texts, size in setting)
        if key in seen:
            return False
        seen.add(key)
        return True

    for scale in scales:
        for mult in _WIDTHS:
            setting = [(tuple(e.wrap(s, width(e, mult)) if s else "" for s in e.raw),
                        pt(sz, scale)) for e, sz in zip(entries, sizes)]
            if fresh(setting):
                yield setting
    # Last resort: what there is room for, the rest cut with an ellipsis — but
    # never the part that tells a row from its neighbours (cap_keeping_tail).
    for lines in (2, 1):
        for mult in _WIDTHS:
            setting = [(tuple(cap_keeping_tail(s, width(e, mult), lines) if s else ""
                              for s in e.raw), pt(sz, scales[-1]))
                       for e, sz in zip(entries, sizes)]
            if fresh(setting):
                yield setting


#: What tells a row from its neighbours, at the END of its name: a combined
#: name's group ("… · Suomi (n=1016)"), or a bare base ("… (n=97)").
_TAIL = re.compile(r"( · .+| \(n=\d+\))$")


def cap_keeping_tail(text: str, width: int, lines: int) -> str:
    """`wrap_label_capped`, except that the cut never takes what tells a row apart.

    Cutting from the end is right for an ordinary name and wrong for a combined
    one: "Olen luottavainen, että saan työstä … · Suomi (n=1016)" cut to one line
    was "Olen luottavainen, että saan…" — three rows reading the same, the
    country gone. So a group or a base at the end is kept whole and the words
    before it are the ones shortened; a name with neither is cut as before.
    (Johan, 2026-09-11)"""
    full = wrap_label(text, width)
    if len(full.split("\n")) <= lines:
        return full
    m = _TAIL.search(text)
    if not m:
        return wrap_label_capped(text, width, lines)
    tail, words = m.group(1), text[: m.start()].split()
    while words:
        candidate = wrap_label(" ".join(words) + "…" + tail, width)
        if len(candidate.split("\n")) <= lines:
            return candidate
        words.pop()
    room = max(1, width * lines - len(tail) - 1)
    return wrap_label(text[: m.start()][:room].rstrip() + "…" + tail, width)


# ── measuring ────────────────────────────────────────────────────────────────

def _touching(entries, obstacles, r, caps=None) -> int | None:
    """How many label pairs, and labels against obstacles, intersect — or None
    when a label band has grown past its cap (that setting is not allowed)."""
    placed = []
    for i, e in enumerate(entries):
        rects = [(*_rect(t, r), e.ax, r.points_to_pixels(_GAP_EM * t.get_fontsize()))
                 for t in e.labels()]
        if caps is not None and rects and _depth([b for b, *_rest in rects], e.axis) > caps[i] + _TOL:
            return None
        placed.extend(rects)
    hits = 0
    for i, (box_a, poly_a, ax_a, gap_a) in enumerate(placed):
        for box_b, poly_b, _ax, gap_b in placed[i + 1:]:
            hits += _meet(box_a, poly_a, box_b, poly_b, gap_a + gap_b)
        for owner, box_o, poly_o in obstacles:
            if owner is not ax_a:
                hits += _meet(box_a, poly_a, box_o, poly_o)
    return hits


def _obstacles(fig, entries, r) -> list:
    """Everything a category name must not be printed over, other than another
    name. A plot area is tagged with its axes: an axes' own names sit beside its
    plot by construction, but must not grow into a NEIGHBOURING panel's.

    Not a legend: that moves out of the names' way afterwards (`_clear_legends`).
    Kept as an obstacle, the stacked column's legend — a fixed 8% under the axis,
    on top of the rotated names — left only the ellipsis, and every name was cut
    to its first word."""
    named = {(id(e.ax), e.axis) for e in entries}
    out: list = []

    def add(artist, owner=None) -> None:
        try:
            box = artist.get_window_extent(r)
        except Exception:  # noqa: BLE001 — an artist that cannot say where it is
            return
        if box.width > 0 and box.height > 0:
            out.append((owner, _box(box), _corners(box)))

    for ax in fig.axes:
        out.append((ax, _box(ax.bbox), _corners(ax.bbox)))
        for t in ax.texts:
            if t.get_visible() and t.get_text().strip():
                add(t)
        if ax.title.get_text().strip():
            add(ax.title)
        for axis, labels in (("x", ax.get_xticklabels), ("y", ax.get_yticklabels)):
            if (id(ax), axis) in named:
                continue
            for t in labels():
                if t.get_visible() and t.get_text().strip():
                    add(t)
    for t in fig.texts:
        if t.get_visible() and t.get_text().strip():
            add(t)
    return out


def _clear_legends(fig, entries, r) -> None:
    """Lower a legend set below the chart until the names above it are clear.

    Only one that is BELOW the names it runs into — a legend inside the plot, or
    beside it, is not in their way. Moved in its own anchor's units (axes or
    figure fractions), since the picture is saved at another dpi than it is
    measured at, and the saved picture is cropped to include it wherever it is."""
    from matplotlib.transforms import Bbox

    names = [(*_rect(t, r), e.ax) for e in entries for t in e.labels()]
    # A primary group's name under its columns belongs to the same band: a
    # legend lowered past the row names must clear it too.
    names += [(*_rect(t, r), ax) for ax in fig.axes for t in ax.texts
              if t.get_gid() == "nsight-group" and t.get_visible() and t.get_text().strip()]
    if not names:
        return
    legends = [ax.get_legend() for ax in fig.axes if ax.get_legend() is not None]
    for legend in legends + list(fig.legends):
        lb = legend.get_window_extent(r)
        hit = [ax for box, poly, ax in names if _meet(box, poly, _box(lb), _corners(lb))]
        # Under the plot of the names it runs into — not their centres: a rotated
        # name reaches far below the axis, and a legend 8% under it sits above
        # the middle of the names it covers.
        if not hit or (lb.y0 + lb.y1) / 2 > min(ax.bbox.y0 for ax in hit):
            continue
        # Clear of every name standing over the legend's width, not just those
        # it touches now — lowered past one, it must not land on a deeper one.
        over = [b for b, _p, _ax in names if min(b[2], lb.x1) - max(b[0], lb.x0) > _TOL]
        floor = min(b[1] for b in over) - r.points_to_pixels(_LEGEND_GAP_PT)
        drop = lb.y1 - floor
        parent = legend.parent
        trans = parent.transAxes if hasattr(parent, "transAxes") else parent.transFigure
        anchor = legend.get_bbox_to_anchor().transformed(trans.inverted())
        step = drop / parent.bbox.height
        legend.set_bbox_to_anchor(
            Bbox.from_extents(anchor.x0, anchor.y0 - step, anchor.x1, anchor.y1 - step),
            transform=trans)


def _cap(e: _Entry, r, fig) -> float:
    boxes = [_rect(t, r)[0] for t in e.labels()]
    room = fig.bbox.width if e.axis == "y" else fig.bbox.height
    return max(_depth(boxes, e.axis), _GROW[e.axis] * room)


def _depth(boxes, axis: str) -> float:
    """How far a label band reaches away from its axis."""
    if not boxes:
        return 0.0
    if axis == "y":
        return max(x1 - x0 for x0, _y0, x1, _y1 in boxes)
    return max(y1 - y0 for _x0, y0, _x1, y1 in boxes)


def _box(b) -> tuple[float, float, float, float]:
    return (b.x0, b.y0, b.x1, b.y1)


def _corners(b) -> list[tuple[float, float]]:
    return [(b.x0, b.y0), (b.x1, b.y0), (b.x1, b.y1), (b.x0, b.y1)]


def _rect(t, r):
    """(screen box, corners of the text's own rectangle) of one label."""
    box = t.get_window_extent(r)
    deg = t.get_rotation()
    if deg % 180 == 0:
        return _box(box), _corners(box)
    t.set_rotation(0)
    flat = t.get_window_extent(r)
    t.set_rotation(deg)
    # A rotated rectangle's screen box is centred on the rectangle, whatever it
    # was rotated about.
    cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    hw, hh = flat.width / 2, flat.height / 2
    poly = [(cx + dx * ca - dy * sa, cy + dx * sa + dy * ca)
            for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
    return _box(box), poly


def _meet(box_a, poly_a, box_b, poly_b, gap: float = 0.0) -> int:
    """1 when two rectangles intersect by more than a hair — or, given a `gap`
    in px, come closer than that — else 0."""
    limit = _TOL - gap
    if (min(box_a[2], box_b[2]) - max(box_a[0], box_b[0]) <= limit
            or min(box_a[3], box_b[3]) - max(box_a[1], box_b[1]) <= limit):
        return 0
    # Separating axes: two convex shapes are apart iff some edge normal of one
    # of them puts them apart.
    for poly in (poly_a, poly_b):
        for i in range(len(poly)):
            (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % len(poly)]
            nx, ny = y0 - y1, x1 - x0
            norm = math.hypot(nx, ny) or 1.0
            nx, ny = nx / norm, ny / norm
            pa = [x * nx + y * ny for x, y in poly_a]
            pb = [x * nx + y * ny for x, y in poly_b]
            if min(max(pa), max(pb)) - max(min(pa), min(pb)) <= limit:
                return 0
    return 1
