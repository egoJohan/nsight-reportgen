"""Shared matplotlib helpers for image-mode chart builders (Task 5.11).

Sets the Agg backend at module level before importing pyplot so that callers
can safely import this module in headless/test environments without a display.
"""
from __future__ import annotations

import math
import os
import tempfile
import textwrap
import matplotlib
matplotlib.use("Agg")
import numpy as np
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402

from reportbuilder.render.house_style import (
    register_fonts, CREAM, INK, GRIDC, MUTED, furniture_colors,
)


#: The resolution every chart is drawn and saved at. Named once because the
#: PLACEMENT needs it too: it is what one saved pixel is worth on the slide, and
#: therefore the ceiling on how far a picture may be scaled up. See
#: `place_picture_square`.
_RENDER_DPI = 200


def _new_agg_figure(w_in: float, h_in: float, dpi: int = _RENDER_DPI) -> Figure:
    """Create a standalone Agg Figure (OO API — NOT pyplot).

    Chart rendering runs on FastAPI's threadpool, so figures are created and
    destroyed concurrently across threads. The pyplot interface (the global Gcf
    figure manager) is not thread-safe; using Figure()+FigureCanvasAgg keeps each
    figure entirely local to its thread, eliminating that race."""
    fig = Figure(figsize=(w_in, h_in), dpi=dpi)
    FigureCanvasAgg(fig)
    return fig

def series_label(ctx, seg: str) -> str:
    """A series' name with the number of people behind it: "Naiset (n=501)".

    A slide comparing groups gave the reader two percentages and no way to know
    one was 501 people and the other 502; the footer's N is the whole slide's
    base, which is neither group's. (customer, 2026-09-09)

    For a series that IS a group. A stacked bar's legend names answer
    categories — its bars are the groups — so those labels are built without
    this, and a category has no base of its own to state.

    Falls back to the bare name when the base is unknown, which is what a
    segment carrying no count means.
    """
    if not wants_group_base(ctx):
        return seg
    base = (getattr(getattr(ctx, "series", None), "base_n", None) or {}).get(seg)
    return with_base(seg, base)


def wants_group_base(ctx) -> bool:
    """Whether a group states its own base on this slide.

    ONE switch for every group's "n", wherever it is drawn: a legend entry, a
    bar's name, a pie or funnel panel's second line. A row of pies had a switch
    of its own (`show_panel_base`), so on those slides the one the author found
    — "Group sizes" — did nothing: "on tilanteita joissa ne ei näytä tekevän
    mitään" (reported 2026-09-17).

    The old per-panel switch is still obeyed where a saved slide turned it off,
    so nobody's hidden number comes back; nothing offers it any more.

    Read through `getattr` at every step: a spec from an older report has
    neither field, and the answer for one of those is the behaviour it already
    had — on. (Johan, 2026-09-16)
    """
    spec = getattr(ctx, "spec", None)
    elements = getattr(spec, "elements", None)
    if not bool(getattr(elements, "group_base", True)):
        return False
    return bool(getattr(spec, "show_panel_base", True))


def with_base(name: str, base) -> str:
    """A group's name with its base, "Naiset (n=501)" — the one wording every
    chart uses for it. The bare name when the base is unknown or zero."""
    try:
        n = int(base)
    except (TypeError, ValueError):
        return name
    return f"{name} (n={n})" if n > 0 else name


def chart_text_font(style) -> str:
    """The face a chart's own text is drawn in.

    The TEMPLATE's content font when it states one, else the house default.
    There is no third source: the admin-wide "chart font" setting this replaced
    could not tell one customer's deck from another's, and a font is a property
    of the template the deck is drawn on. (Johan, 2026-09-08)
    """
    from reportbuilder.render.house_style import (
        _DEFAULT_CHART_FONT, available_chart_fonts,
    )

    stated = (getattr(style, "body_font", "") or "").strip()
    if not stated:
        return _DEFAULT_CHART_FONT
    # A face this host cannot draw degrades to the HOUSE default, not to
    # matplotlib's DejaVu — an unavailable setting should land on a deliberate
    # choice rather than an accidental one. (The same rule the admin-wide
    # setting this replaced applied to its own picker.)
    return stated if stated in set(available_chart_fonts()) else _DEFAULT_CHART_FONT


def _remember_font(fig, ctx) -> None:
    """Stash this figure's face on the figure itself.

    Not on matplotlib's rcParams: those are process-global, and FastAPI runs
    these endpoints on a threadpool, so two previews of two templates build
    figures at the same time. A global family was safe only while every deck
    shared one; the moment it comes from the template, one report's font would
    land on another's chart. `render_png` reads it back.
    """
    style = getattr(ctx, "style", None) if ctx is not None else None
    fig._nsight_chart_font = chart_text_font(style)
    # …and the spec it is being drawn for, so a pass that needs the
    # author's choices can run at the one point every builder passes
    # through. See `hide_values_when_off`.
    fig._nsight_spec = getattr(ctx, "spec", None)


_EMU_PER_IN = 914400.0


def force_break_token(token: str, width: int) -> list[str]:
    """Break a single word longer than *width* into width-sized chunks.

    Last-resort splitting so a pathological unbroken long word (e.g. erroneous
    survey data with no spaces) cannot overflow the chart bounds. Normal words
    shorter than *width* are returned unchanged.
    """
    if len(token) <= width:
        return [token]
    return [token[i:i + width] for i in range(0, len(token), width)]


#: A panel's heading, and the floor it may shrink to before it is cut instead.
PANEL_TITLE_PT: float = 12.5
PANEL_TITLE_MIN_PT: float = 8.5


def _title_extent(fig, text: str, fontsize: float) -> tuple[float, float]:
    """(width, height) in px of *text* as a panel title on this figure."""
    kw = {"fontsize": fontsize, "fontweight": "bold"}
    family = getattr(fig, "_nsight_chart_font", "")
    if family:
        kw["fontfamily"] = family
    art = fig.text(0, 0, text, **kw)
    try:
        box = art.get_window_extent(fig.canvas.get_renderer())
        return box.width, box.height
    finally:
        art.remove()


#: The gap `label_fit` leaves between a legend and the names above it.
_LEGEND_DROP_GAP_PT = 6.0


def panel_band(fig, ax) -> tuple[float, float]:
    """(bottom, top) in px of everything this panel draws: its plot, its title,
    the names under it and its own legend.

    The legend is counted where it will END UP, not where it sits now: the
    label fitter lowers it below the rotated names once they are final, so a
    band measured from its current place reserves too little and the lowered
    legend lands on the panel below. (2026-09-22)
    """
    r = fig.canvas.get_renderer()
    boxes = [ax.bbox]
    title = ax.title
    if title is not None and title.get_text().strip():
        boxes.append(title.get_window_extent(r))
    names = [label.get_window_extent(r)
             for label in list(ax.get_xticklabels()) + list(ax.get_yticklabels())
             if label.get_visible() and label.get_text().strip()]
    boxes += names
    bottom, top = min(b.y0 for b in boxes), max(b.y1 for b in boxes)
    legend = ax.get_legend()
    if legend is not None:
        box = legend.get_window_extent(r)
        under_names = (min((b.y0 for b in names), default=ax.bbox.y0)
                       - r.points_to_pixels(_LEGEND_DROP_GAP_PT) - box.height)
        bottom = min(bottom, box.y0, under_names)
        top = max(top, box.y1)
    return bottom, top


def separate_panel_rows(fig, *, margin_pt: float = 8.0, passes: int = 8) -> None:
    """Pull stacked panels apart until each has the page to itself.

    A panel is not its plot: it is its title, its plot, the names under it and
    its own legend, and on a chart split by two variables those bands met — the
    lower panel's title was printed in the middle of the upper panel's legend.
    Reported 2026-09-22: "the title of the lower overlaps with the legend of
    the upper … ensure that those have clearly separate areas to render, with
    small margin."

    The panels are given the room by widening the gap between the rows, which
    is the one number that means "space between panels"; everything anchored to
    an axes — title, legend — travels with it.

    Measured and re-measured until they clear: widening the gap shrinks the
    panels, and a legend anchored under its own panel moves with it, so one
    nudge does not settle it. Each pass removes what is left of the overlap,
    and a little more than the measurement asks for, since an exact step lands
    just short every time.
    """
    for _pass in range(passes):
        fig.draw_without_rendering()
        columns: dict[int, list] = {}
        for ax in fig.axes:
            if ax.get_visible():
                columns.setdefault(round(ax.bbox.x0), []).append(ax)
        need = 0.0
        heights = []
        for axes in columns.values():
            axes.sort(key=lambda a: a.bbox.y0, reverse=True)     # top row first
            for upper, lower in zip(axes, axes[1:]):
                heights += [upper.bbox.height, lower.bbox.height]
                gap = panel_band(fig, upper)[0] - panel_band(fig, lower)[1]
                need = max(need, margin_pt * fig.dpi / 72.0 - gap)
        if need <= 1.0 or not heights:
            return
        pars = fig.subplotpars
        grown = pars.hspace + 1.25 * need / (sum(heights) / len(heights))
        if grown >= 2.0:
            return              # more gap than plot: leave it, something is odd
        fig.subplots_adjust(hspace=grown)


def fit_panel_titles(fig, titled, *, colour, pad: int = 3,
                     max_lines: int = 2) -> None:
    """Set each panel's title, wrapped and sized to the panel it names.

    Set close to its own plot (`pad`), so a reader pairs it with the chart
    under it rather than with whatever is above.

    A title was set at one size whatever the panel's width, and a value label
    like "Suuressa kaupungissa (yli 150 000 asukasta)" is three times as wide
    as the panel it heads: five of them printed straight through each other
    across the top of the chart. Reported from the field, 2026-09-22 —
    "Second classifyingin kanssa tulee vielä tekstien sijoitteluongelmia".

    The room a title has is its own panel plus half the gap to its neighbours,
    which is exactly the room its neighbours are not using. Wrapped to that
    first, then a step smaller at a time, and at the floor cut to `max_lines`
    with an ellipsis — a title that cannot fit is shortened here, where it is
    still legible, rather than drawn over the next panel's.

    `titled` is [(axes, text)]. Call it once the panels are laid out
    (`subplots_adjust`), since that is the width being fitted to.
    """
    if not titled:
        return
    # Lays the panels out without painting them, so the boxes being fitted to
    # are the ones the saved picture will have.
    fig.draw_without_rendering()
    sizes = [PANEL_TITLE_PT]
    while sizes[-1] * 0.9 >= PANEL_TITLE_MIN_PT:
        sizes.append(sizes[-1] * 0.9)
    fitted: list[tuple[object, str, float]] = []
    for ax, text in titled:
        flat = " ".join(str(text or "").split())
        if not flat:
            continue
        others = [a.bbox for a in fig.axes if a is not ax and a.get_visible()]
        right = min((b.x0 for b in others if b.x0 >= ax.bbox.x1), default=fig.bbox.x1)
        left = max((b.x1 for b in others if b.x1 <= ax.bbox.x0), default=fig.bbox.x0)
        room = min(ax.bbox.x0 - left, right - ax.bbox.x1) + ax.bbox.width
        wrapped, chosen = flat, sizes[-1]
        for size in sizes:
            per_char = _title_extent(fig, flat, size)[0] / max(len(flat), 1)
            chars = max(6, int(room / max(per_char, 0.1)))
            candidate = wrap_label(flat, chars)
            while (_title_extent(fig, candidate, size)[0] > room
                   and chars > 6):
                chars = int(chars * 0.92)
                candidate = wrap_label(flat, chars)
            if (candidate.count("\n") + 1 <= max_lines
                    and _title_extent(fig, candidate, size)[0] <= room):
                wrapped, chosen = candidate, size
                break
            if size == sizes[-1]:
                wrapped, chosen = wrap_label_capped(flat, chars, max_lines), size
        fitted.append((ax, wrapped, chosen))
    # ONE size for the row: a title set a step larger than the one beside it
    # reads as emphasis nobody meant. The smallest that any of them needed is
    # the size they all take, and each is re-wrapped to it.
    if not fitted:
        return
    smallest = min(size for _ax, _text, size in fitted)
    for (ax, _wrapped, size), (_ax2, text) in zip(fitted, titled):
        if size > smallest:
            flat = " ".join(str(text or "").split())
            per_char = _title_extent(fig, flat, smallest)[0] / max(len(flat), 1)
            others = [a.bbox for a in fig.axes if a is not ax and a.get_visible()]
            right = min((b.x0 for b in others if b.x0 >= ax.bbox.x1), default=fig.bbox.x1)
            left = max((b.x1 for b in others if b.x1 <= ax.bbox.x0), default=fig.bbox.x0)
            room = min(ax.bbox.x0 - left, right - ax.bbox.x1) + ax.bbox.width
            chars = max(6, int(room / max(per_char, 0.1)))
            _wrapped = wrap_label(flat, chars)
        ax.set_title(_wrapped, fontsize=smallest, fontweight="bold", color=colour, pad=pad)


def wrap_label(text: str, width: int) -> str:
    """Wrap *text* at word boundaries onto lines of at most *width* chars.

    Never truncates and never adds an ellipsis. Hyphenated compounds are kept
    intact at word level; a single token longer than *width* is force-broken
    mid-character (the only case a word is split) so erroneous long labels can't
    run off the chart. Returns the text with embedded newlines.
    """
    text = (text or "").strip()
    if len(text) <= width:
        return text
    out: list[str] = []
    for ln in textwrap.wrap(
        text, width=width, break_long_words=False, break_on_hyphens=True
    ):
        out.extend(force_break_token(ln, width))
    return "\n".join(out) if out else text


def wrap_label_capped(text: str, width: int, max_lines: int) -> str:
    """Like wrap_label but caps the result to *max_lines* lines, truncating the
    last visible line with an ellipsis when the text doesn't fit.

    Ellipsis truncation is a deliberate last resort (user-approved): when a label
    has too many categories / too-long text to fit its row band, an ellipsis is
    preferred over labels overlapping each other. Full text is preserved whenever
    it fits in *max_lines*."""
    max_lines = max(1, max_lines)
    full = wrap_label(text, width)
    lines = full.split("\n")
    if len(lines) <= max_lines:
        return full
    kept = lines[:max_lines]
    last = kept[-1]
    if len(last) >= width:                 # make room for the ellipsis
        last = last[: max(1, width - 1)]
    kept[-1] = last.rstrip() + "…"
    return "\n".join(kept)


def render_empty_chart(ctx, message: str = "") -> None:
    """Render a BLANK placeholder as a picture, so a chart with no categories
    (e.g. a scale variable with no value labels) degrades cleanly instead of
    crashing the deck. Counts as the chart's one picture.

    It used to print "No data to show" across the chart area — in English, on a
    deck read by the client. What a slide could not show is a warning to its
    AUTHOR, raised in the editor like every other slide problem; the preview
    endpoint says so with the `X-Chart-Empty` header. `message` is kept for a
    caller that genuinely wants text on the slide; nothing passes one today.
    (Johan, 2026-09-16)
    """
    fig, ax = new_figure(ctx)
    ax.axis("off")
    if message:
        _ink, muted, _grid = chart_furniture(ctx)
        ax.text(0.5, 0.5, message, ha="center", va="center",
                fontsize=13, color=muted, transform=ax.transAxes)
    place_picture(ctx, render_png(fig))


def series_is_empty(series) -> bool:
    """True when a series has nothing to plot (no categories, or every value is
    None/zero across all segments)."""
    cats = getattr(series, "categories", ())
    if not cats:
        return True
    stat = getattr(series, "statistic", "pct")
    for cat in cats:
        for seg in series.segments:
            cell = series.cells.get((cat, seg))
            if cell is not None and cell.value(stat) not in (None, 0, 0.0):
                return False
    return True


def _capped_height(ctx, w_in: float, h_in: float, *, rows: int = 1) -> float:
    """A caller-chosen figure height, floored at the slot's height and ceilinged
    at `rows` times the slot's aspect. See `new_tall_figure` for why the ceiling
    exists.

    `rows` is the number of STACKED bands of panels. The ceiling is per band,
    because a band is its own slot-shaped chart: two rows of panels genuinely
    hold two charts' worth of content, and capping the pair at one slot-aspect
    collapses the second row onto the first — the rotated tick labels and the
    second legend land on top of the first row, which is the defect
    `test_vertical_stacked_panels_grow_figure_height` exists to catch.

    Note what the ceiling does NOT claim: a 2-row figure is still letterboxed
    down to about half size on the slide. Height is the wrong lever for that —
    the fix for a picture with too much in it is fewer panels in it, not a
    taller figure, which is the same trade `new_tall_figure` documents.

    The ceiling is never below the floor: `w_in` is `max(9.0, slot_w)` and
    `rows >= 1`, so `rows * w_in * slot_h / slot_w >= slot_h`.
    """
    slot_w_in = ctx.slot.width / _EMU_PER_IN
    slot_h_in = ctx.slot.height / _EMU_PER_IN
    if slot_w_in <= 0 or slot_h_in <= 0:        # a slot with no area to fill
        return max(h_in, slot_h_in)
    ceiling = max(1, rows) * w_in * slot_h_in / slot_w_in
    return min(max(h_in, slot_h_in), ceiling)


# Moved here from bars.py, 2026-09-16: the LINE and RADAR builders each
# carried their own copy of the percentage half of this rule and capped
# every statistic at 100, so a line of counts ran off the top of its own
# chart. One axis rule, in the module every builder already imports.
def _value_axis(max_val: float, statistic: str) -> tuple[float, list[float]]:
    """Return (axis_max, gridline/tick positions) for the VALUE axis.

    Percentages use the fixed 0..100 scale (capped, 20-step gridlines). Counts
    and means have no 100 cap — the axis scales to the data with ~5 "nice" ticks,
    otherwise a count of e.g. 600 would overflow a 0..100 axis and its data
    labels (placed at x=value) would blow up the tight bounding box, shrinking
    the whole chart to a stamp.

    A percentage above 100 is not a rounding artefact to be clipped: it is a
    stacked chart whose segments genuinely overlap (a multi-response question,
    shares summing to e.g. 465%) drawn at its TRUE widths (`_stack_scaling`).
    Capping that at 100 would push most of every bar off the axis — precisely
    the dishonesty this axis exists to avoid — so it falls through to the
    nice-tick branch and the axis reads to the real maximum."""
    if statistic == "pct" and max_val <= 100.0:
        ax_max = min(100.0, max(max_val * 1.15, 10.0))
        ticks = [v for v in [0, 20, 40, 60, 80, 100] if v <= ax_max]
        if len(ticks) < 3:
            # A chart whose biggest bar is small got one or two rungs off the
            # fixed ladder — and under 9%, where the axis sits on its own 10.0
            # floor, exactly one: the zero. Twenty-five departments, none above
            # 5%, and the axis read "0" and nothing else, so no bar could be
            # measured against anything. The ladder is right for the ordinary
            # chart and stays; it steps down only where it had stopped saying
            # anything. (Johan, 2026-09-16)
            step = 5.0 if ax_max > 12.0 else 2.0
            ticks = [round(i * step, 6) for i in range(int(ax_max // step) + 1)]
        return ax_max, ticks
    # count / mean: nice round ticks covering the data range.
    vmax = max(max_val * 1.12, 1.0)
    raw = vmax / 5.0
    mag = 10.0 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    top = math.ceil(vmax / step) * step
    n = int(round(top / step))
    ticks = [round(i * step, 6) for i in range(n + 1)]
    return top, ticks

def new_figure(ctx):
    """Create a matplotlib Figure/Axes sized to ctx.slot, with nSight house style applied.

    Applies cream background and Liberation Sans font (REQ-C-25/27a).
    Minimum size enforced to maintain legibility at any slot dimension.
    """
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(4.5, ctx.slot.height / _EMU_PER_IN)
    fig = _new_agg_figure(w_in, h_in)
    _remember_font(fig, ctx)
    ax = fig.subplots()
    # The template's own background, so the chart does not sit on a cream
    # rectangle in the middle of a white deck. Falls back to house cream when no
    # template applies.
    bg = chart_background(ctx)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    return fig, ax


def new_figure_grid(ctx, n: int, *, tall_in: float | None = None, rows: int = 1,
                     sharey: bool = True, width_ratios=None):
    """Figure with n subplots, house style applied — for cross-tab SMALL MULTIPLES
    (one panel per primary classifier value) and for the SEPARATE layout (one
    panel per classifying VARIABLE). `rows` > 1 stacks the panels one above the
    other, which the separate layout uses when the category labels need the full
    width. (spec 2026-08-04)

    `sharey` defaults to True (panels share one category axis — small multiples
    and the clustered separate-panel renderer all draw the SAME categories in
    every panel, just different classifying groups). Matplotlib's `sharey=True`
    links the y VIEW LIMITS across every axes in the grid (not just the visible
    tick labels) — verified: with two panels of a different bar COUNT each,
    `ax.set_ylim(...)` on the second panel silently overwrites the first
    panel's limits too, and the second panel's `set_yticks` overwrites the
    first's ticks. The stacked separate-panel renderer draws a DIFFERENT set of
    bars per panel (one variable's classifier segments, not the shared answer
    categories) and must pass `sharey=False` to keep each panel's ticks/limits
    independent. (spec 2026-08-04-separate-classifier-panels)

    `width_ratios` (one number per COLUMN, default equal) hands the columns
    unequal widths. The funnel panel row uses it: only its rightmost panel draws
    the stage labels, so only that one needs the wide label gutter, and giving it
    a proportionally wider column keeps a data unit worth the same number of
    pixels in every panel — which is what makes the funnel widths comparable
    across groups. (spec 2026-08-22)"""
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    # Capped for the same reason a single tall figure is — a grid is placed by
    # the same letterboxing rule, so anything more portrait than the slot is
    # scaled away. Per STACKED BAND, not per figure: see `_capped_height`.
    h_in = _capped_height(ctx, w_in, tall_in or 4.5, rows=rows)
    fig = _new_agg_figure(w_in, h_in)
    _remember_font(fig, ctx)
    cols = max(1, -(-n // max(1, rows)))          # ceil(n / rows)
    gridspec_kw = {"width_ratios": list(width_ratios)} if width_ratios else None
    axes = fig.subplots(max(1, rows), cols, sharey=sharey, sharex=False,
                        gridspec_kw=gridspec_kw)
    # `fig.subplots` returns a bare Axes only for a 1x1 grid; with rows > 1 it
    # returns an ndarray even when n == 1 (the separate layout hits exactly that
    # when one classifying variable resolves to no groups and the labels want two
    # rows). np.atleast_1d + ravel flattens BOTH shapes to a plain list of Axes;
    # wrapping in a list unconditionally would leave an ndarray element behind and
    # blow up on the first `ax.set_facecolor`. (spec 2026-08-04)
    axes = list(np.ravel(np.atleast_1d(axes)))
    for extra in axes[n:]:                        # an odd count leaves a blank cell
        extra.set_visible(False)
    axes = axes[:n]
    # The template's own background — see new_figure's identical comment; a
    # small-multiples/separate-panel grid is still one chart on one slide.
    bg = chart_background(ctx)
    fig.patch.set_facecolor(bg)
    for ax in axes:
        ax.set_facecolor(bg)
    return fig, axes


def new_tall_figure(ctx, h_in: float):
    """Like new_figure but with a caller-chosen height, between the slot's own
    height and the slot's own ASPECT.

    Horizontal-bar charts grow taller as categories increase so every row keeps
    room for a ~2-line wrapped label at a legible font (instead of shrinking the
    font / truncating).

    That growth has a ceiling, and it is not a matter of taste: `place_picture`
    letterboxes, scaling by `min(slot_w/px_w, slot_h/px_h)`. The moment the
    figure is more portrait than the slot, HEIGHT is the limiting dimension and
    the entire picture — every bar, every label — is scaled down to fit it,
    leaving the slide's width empty. Growing past the aspect therefore makes the
    labels SMALLER on the slide, which is the opposite of why the figure grows.

    Measured on a 12.3x4.4in slot: 25 categories asked for 14.2in and were
    placed at 31 % of the slot width, printing a 9pt tick label at 2.8pt. The
    loss starts at 7 categories. Past the cap the rows compress and the
    builders' font floors take over. (Johan, 2026-09-16)"""
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = _capped_height(ctx, w_in, h_in)
    fig = _new_agg_figure(w_in, h_in)
    _remember_font(fig, ctx)
    ax = fig.subplots()
    # The template's own background, so the chart does not sit on a cream
    # rectangle in the middle of a white deck. Falls back to house cream when no
    # template applies.
    bg = chart_background(ctx)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    return fig, ax


def hide_values_when_off(fig, spec) -> int:
    """Take every printed value off *fig* when the author turned them off.

    `elements.data_labels` used to be read by the native OOXML path and by the
    image SCATTER builder, and by nothing else — so in image mode, which is
    what a preview and a rendered deck both use, unticking "Data labels" left
    the picture exactly as it was on a bar, column, line, pie, doughnut,
    funnel, combo or stacked chart. An author clicks a control, nothing moves,
    and the only available conclusion is that the editor is broken.

    One pass rather than nine builders: every value a builder prints already
    carries `VALUE_GID` — the shrink and declash passes are built on that — and
    every builder goes through `new_figure*` (which remembers the spec) and
    `render_png` (which calls this). A builder written later inherits it
    without knowing it exists, which is the property the old arrangement
    lacked.

    Hidden, not removed: the layout passes have already run and some of them
    read these artists. Returns how many were hidden.
    """
    el = getattr(spec, "elements", None) if spec is not None else None
    if el is None or getattr(el, "data_labels", True):
        return 0
    hidden = 0
    for ax in getattr(fig, "axes", ()) or ():
        for artist in list(getattr(ax, "texts", ()) or ()):
            if artist.get_gid() == VALUE_GID and artist.get_visible():
                artist.set_visible(False)
                hidden += 1
    return hidden


def author_label_floor(spec, statistic: str, all_vals) -> float:
    """The author's own "hide values below X" — and nothing when they set none.

    `label_floor` answers with the chart TYPE's default when nobody has set a
    cut-off, which is what a pie and a stack want: their numbers sit inside
    wedges and slivers and collide as soon as the piece is small. A plain bar,
    column or line prints its number in free space beside the point, where a
    small value costs nothing — so those builders had no floor at all, and in
    having none they ignored the author's too. The control did nothing on the
    three commonest chart types in the product.

    This gives them the author's answer without inventing a default, so a deck
    written before it renders unchanged.

    A percentage is measured against 100, not against the axis top, so "hide
    below 10" means ten per cent on every chart — the same thing it already
    means on a pie and on a 100 %-stacked bar. A count or a mean has no such
    scale, so there it stays a share of the axis, as `label_floor` documents.
    """
    fmt = getattr(spec, "number_format", None) if spec is not None else None
    if getattr(fmt, "hide_below_pct", None) is None:
        return 0.0
    axis_max = 100.0 if statistic == "pct" else max(
        (v for v in (all_vals or ()) if v is not None), default=100.0)
    return label_floor(fmt, default_pct=0.0, axis_max=axis_max)


def _grown(start: float, size: float, by: float) -> tuple[float, float]:
    """(start, size) grown by *by* inside 0..1, spilling into the near margin
    when the far edge is reached."""
    size = min(1.0, size + by)
    start = min(start, max(0.0, 1.0 - size))
    return start, min(size, 1.0 - start)


def _use_the_whole_figure(fig) -> None:
    """Give the plot the height nothing else is using.

    The figure is drawn at the size of the slot, and `bbox_inches="tight"` then
    trims it to its ink. A chart WITH a legend fills that size — the legend
    hangs below the axes and the trim keeps it — but a chart without one saves
    a PNG a fifth of an inch shorter, and `place_picture` never magnifies, so
    that fifth of an inch stayed empty under the chart on the slide. Reported
    as "if there is no legend we do not want to preserve empty space for those.
    Now there is empty space below the chart if there is no legend."
    (Johan, 2026-09-21)

    So the axes take the slack instead: the ink grows to the figure it was
    given, at the same point sizes, and the picture fills its slot. Only for
    the ordinary one-plot figure — a grid of small multiples, a chart with a
    legend beside it and anything that placed its own axes are left alone.
    """
    try:
        axes = [ax for ax in fig.axes if ax.get_visible()]
        if len(axes) != 1 or axes[0].get_legend() is not None:
            return
        if any(getattr(child, "get_visible", lambda: False)()
               and child.__class__.__name__ == "Legend" for child in fig.legends):
            return
        ax = axes[0]
        fig_w, fig_h = fig.get_figwidth(), fig.get_figheight()
        # Twice: growing the axes moves the labels that were being measured, so
        # the first pass takes most of the slack and the second what is left.
        # Both ways — a horizontal bar's row names are trimmed off the side
        # just as a column chart's are trimmed off the foot.
        for _pass in range(2):
            fig.draw_without_rendering()
            ink = fig.get_tightbbox()
            if ink is None:
                return
            slack_w, slack_h = fig_w - ink.width, fig_h - ink.height
            if slack_w >= fig_w * 0.5 or slack_h >= fig_h * 0.5:
                return                  # something unusual; leave it alone
            if slack_w <= 0.02 and slack_h <= 0.02:
                return                  # the ink already fills the figure
            box = ax.get_position()
            # Grow, and where that runs into the figure's edge take the rest
            # from the margin on the other side — the labels that live there
            # are what `bbox_inches="tight"` keeps, so nothing is lost.
            x0, w = _grown(box.x0, box.width, max(0.0, slack_w) / fig_w)
            y0, h = _grown(box.y0, box.height, max(0.0, slack_h) / fig_h)
            ax.set_position([x0, y0, w, h])
    except Exception:  # noqa: BLE001 — a chart that will not measure is drawn as it is
        pass


def render_png(fig) -> str:
    """Save figure to a temp PNG file at high quality and free it. Returns the path.

    The figure is an OO Agg Figure (not pyplot-managed), so there is no global
    registry entry to close — clearing it just releases its artists/memory."""
    # Deleted by place_picture_square once python-pptx has embedded it; the
    # caller is not expected to clean up.
    hide_values_when_off(fig, getattr(fig, "_nsight_spec", None))
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    # transparent: the chart is placed ON a slide whose layout already paints
    # the customer's background. An opaque panel behind the plot shows up as a
    # white box on any template whose background is not exactly its theme lt1 —
    # Attendo's off-white, for one. Letting the slide show through is what
    # "use the template as is" means for the chart, and it is correct for the
    # house default too, which now paints its cream in the layout.
    # The template's face, applied per FIGURE. Tick labels and legend text are
    # created during a draw, so the figure is drawn once first and every Text
    # artist is then set — family only, never size or colour, which each
    # builder has already decided for good reasons (a white number inside a
    # bar, a muted tick).
    family = getattr(fig, "_nsight_chart_font", "")
    if family:
        from matplotlib.text import Text

        fig.canvas.draw()
        for artist in fig.findobj(Text):
            artist.set_fontfamily(family)
    # Category names that would print over each other are set again until they
    # do not — after the face, since the face decides how wide they are.
    from reportbuilder.render.image import label_fit
    label_fit.fit_category_labels(fig)
    _use_the_whole_figure(fig)
    fig.savefig(path, dpi=_RENDER_DPI, bbox_inches="tight", pad_inches=0.04,
                transparent=True)
    fig.clear()
    return path


def place_picture(ctx, png_path: str) -> None:
    """Place png_path onto ctx.slide, scaled to FIT the slot preserving aspect.

    No chart element may ever be stretched or squeezed: the PNG is scaled by the
    limiting slot dimension (letterbox), so the rendered chart keeps its true
    aspect ratio.  Top-aligned so bar/line/funnel charts hug the question text
    above them rather than floating mid-slot with a large gap."""
    place_picture_square(ctx, png_path, valign="top")


# Defined in render.panels (not here) so that module has no dependency on the
# image package; re-exported here because every caller in this file already
# imports from _mpl and MIN_SEGMENT_BASE has always lived at this name.
from reportbuilder.render.panels import MIN_SEGMENT_BASE  # noqa: F401


def series_values(series):
    """Decompose a SeriesResult into (cats, segs, data) for chart rendering.

    Every group with respondents is drawn, however few. A group under
    MIN_SEGMENT_BASE used to be dropped so that one person never drew as 100 % —
    and a study of 41 split by six companies (3–9 each) lost every group, drew
    the whole sample instead, and read as a classifying variable that did not
    work. A group states its own base ("Amazon (n=3)"), so the reader sees what a
    percentage rests on; the editor warns the author about small groups. Decided
    2026-09-17. Only a group with NO respondents is left out.

    Returns:
        cats: list of category labels (x-axis / bar groups)
        segs: list of segment labels (series)
        data: dict of seg -> list[float] (one value per category)
    """
    cats = list(series.categories)
    segs = [
        s for s in series.segments
        if s == "Total" or series.base_n.get(s, 0) > 0
    ]
    if not segs:  # no group has anyone in it — fall back to the overall column
        segs = [s for s in series.segments if s == "Total"] or list(series.segments)
    # Drop the "Total" reference series when the chart opts out (show_total=False),
    # unless it is the ONLY series (a single-series 'Total'-only chart). (2026-07-10)
    if getattr(series, "show_total", True) is False:
        non_total = [s for s in segs if s != "Total"]
        if non_total:
            segs = non_total
    data = {
        seg: [
            float(series.cell(c, seg).value(series.statistic) or 0.0)
            for c in cats
        ]
        for seg in segs
    }
    return cats, segs, data


def is_total(seg: str) -> bool:
    """A Total series: the overall "Total", or a separate panel's "<variable> · Total"."""
    return seg == "Total" or seg.endswith(" · Total")


def place_total(segs, position: str, *, top_is_last: bool = False) -> list:
    """`segs` with its Total(s) moved to where the author asked for them.

    `position` is the chart's `total_position`: "top" puts Total first as the
    reader meets it, "bottom" last, and anything else ("auto") leaves the order
    exactly as it was. `top_is_last` is for a builder that draws its list from
    the bottom up — a grouped horizontal bar stacks the series of each group
    upwards, so the reader's top is the END of the list there. (2026-09-11)
    """
    segs = list(segs)
    if position not in ("top", "bottom"):
        return segs
    totals = [s for s in segs if is_total(s)]
    rest = [s for s in segs if not is_total(s)]
    return totals + rest if (position == "top") != top_is_last else rest + totals


def coded_order(series, segs) -> list:
    """*segs* in the order their colours are dealt: as coded in the data.

    The same as *segs* unless Survey order Descending reversed the groups, in
    which case the series carries their coded order and a group keeps the colour
    it has everywhere else in the report (`SeriesResult.segments_as_coded`)."""
    coded = getattr(series, "segments_as_coded", ()) or ()
    if not coded:
        return list(segs)
    present = set(segs)
    order = [s for s in coded if s in present]
    return order + [s for s in segs if s not in set(order)]


def colours_by_series(clrs, default_order, drawn_order) -> list:
    """`clrs`, dealt along `default_order`, handed to the same series in `drawn_order`.

    Colours were given out by position, so putting Total on top gave "Naiset"
    the colour Total had and moved every group along one. The author moved one
    bar; a series keeps its colour wherever it is drawn. (2026-09-11)"""
    at = dict(zip(default_order, clrs))
    return [at.get(s, c) for s, c in zip(drawn_order, clrs)]


def chart_background(ctx) -> str:
    """The colour a chart paints onto — resolved in ONE place.

    render/resolved_style.ground is that place: the text beside this chart reads
    the same function, so the two cannot disagree about the ground they are on.
    """
    from reportbuilder.render.resolved_style import ground
    return ground(ctx.style)


def chart_ink(ctx) -> str:
    """Body-text colour: the template's dk1, else house ink."""
    value = getattr(ctx.style, "ink", "") or ""
    return f"#{value}" if value else INK


def template_palette(ctx) -> list[str] | None:
    """The client template's accent colours, or None when no template applies.

    Keyed on from_template because that is set only by load_style_spec on a
    real .pptx — the base StyleSpec carries matplotlib's default blue/orange,
    which would be worse than the house ramp. The house DEFAULT template also
    goes through load_style_spec, so its teal-led theme arrives by the same
    path and there is no "is this a template" branch anywhere else.

    It used to key on chart_layout_index, which stopped meaning "a template" the
    moment a template whose design lives on its slides was given no layout to
    build from — a client deck would have lost the client's chart colours.

    A template with no BRAND palette (untouched Office accents) returns None on
    purpose: the ramp built from `chart_accent` applies instead, which is the
    colour that template's own slides are actually drawn in.
    """
    if not getattr(ctx.style, "from_template", False):
        return None
    brand = getattr(ctx.style, "brand_palette", None)
    if not brand:
        return None
    try:
        return [f"#{c}" for c in brand]
    except Exception:  # noqa: BLE001 — styling must not break a render
        return None


def chart_furniture(ctx) -> tuple[str, str, str]:
    """(ink, muted, grid) for THIS chart's slide background (house_style.furniture_colors).

    One call per builder instead of re-deriving contrast against
    chart_background(ctx) piecemeal in eight files — see house_style.py for why
    a light background is untouched and only a dark one gets a derived set.

    An author's CONTENT colour replaces the derived ink. The derivation exists
    to keep text legible on a ground nobody told us about; somebody who states
    the colour has looked at the slide, and their answer wins. `muted` and
    `grid` stay derived — they are contrast furniture, not text.
    (Johan, 2026-09-08)
    """
    ink, muted, grid = furniture_colors(chart_background(ctx))
    stated = (getattr(getattr(ctx, "style", None), "chart_text_colour", "") or "").strip()
    if stated:
        # Stored bare ("B3005E") the way every other colour on the style is;
        # matplotlib wants the hash.
        ink = stated if stated.startswith("#") else f"#{stated}"
    return ink, muted, grid


def chart_accent(ctx) -> str:
    """The colour this deck's charts lead with: the template's, else house teal.

    Series ramps are built from it, so a template that states only one colour —
    the bar beside its titles, the rule under them — still gets charts in its
    own colour rather than in ours.
    """
    return getattr(ctx.style, "accent", "") or ""


def colors(ctx, n: int) -> list[str]:
    """Return n matplotlib hex color strings from ctx.style (prepend '#').

    Retained for backwards-compatibility; prefer `series_colors(n)` for house style.
    """
    return ["#" + ctx.style.color_for(i) for i in range(n)]


def auto_decimals(values: list[float], statistic: str) -> int:
    """Choose decimal places automatically from value range and statistic (REQ-N-01/02/03).

    pct:   0 when all values are ≥ 10 or fractional parts are negligible;
           1 when any value is < 10 with a non-trivial fraction or the spread
           between adjacent sorted values is < 1.
    mean:  0 if values span a wide, integer-ish range (spread ≥ 5 and fracs trivial);
           1 otherwise (Likert-style or close values).
    count: always 0.
    """
    if statistic == "count":
        return 0
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return 1 if statistic == "mean" else 0
    if statistic == "pct":
        all_large = all(v >= 10.0 for v in clean)
        # Distance to the NEAREST integer, not the fraction above the floor:
        # a share recomputed as v/total*100 lands a hair either side of a
        # whole number, and `v % 1` reads 28.999999999999996 as 0.99999 --
        # a large fraction -- so one binary artefact put a decimal on every
        # number of the slide. See test_auto_decimals_pct_whole_numbers_a
        # _hair_BELOW_the_integer_zero.
        frac_trivial = all(abs(v - round(v)) < 0.05 for v in clean)
        if all_large or frac_trivial:
            return 0
        sorted_vals = sorted(clean)
        if len(sorted_vals) > 1:
            min_spread = min(b - a for a, b in zip(sorted_vals, sorted_vals[1:]))
        else:
            min_spread = 1.0
        if any(v < 10.0 for v in clean) or min_spread < 1.0:
            return 1
        return 0
    if statistic == "mean":
        spread = max(clean) - min(clean)
        int_ish = all(abs(v % 1) < 0.1 for v in clean)
        if spread >= 5.0 and int_ish:
            return 0  # wide integer-ish range
        return 1  # Likert-style or close values
    return 0


#: Where each chart type stops printing a value inside its own piece, when the
#: author has not said. A pie's labels sit on a curve and run into each other
#: sooner than a bar's, which is the only reason these differ.
#:
#: Stated ONCE. The editor shows the default beside the field and the renderer
#: applies it, and when the two were written out separately they were one edit
#: away from disagreeing about what the chart does.
LABEL_FLOOR_DEFAULT_PCT: dict[str, float] = {
    "pie": 4.0,
    "doughnut": 4.0,
}
LABEL_FLOOR_FALLBACK_PCT: float = 1.0

#: Marks a text as a VALUE a chart drew, as opposed to a category name, a
#: group name, a legend entry or a title. Two things need to tell them apart:
#: "a number on its own bar" (expected) from "a number on ANOTHER bar" (a
#: defect), and which of the five font floors applies to a given text.
#:
#: It lives here rather than in `bars.py` because every builder draws values
#: and every builder already depends on this module; reaching into a peer
#: builder for it would be a dependency pointing the wrong way.
VALUE_GID: str = "nsight-value"


def default_label_floor(chart_type: str) -> float:
    """The cut-off this chart type uses when the author has not set one."""
    return LABEL_FLOOR_DEFAULT_PCT.get(chart_type, LABEL_FLOOR_FALLBACK_PCT)


def label_floor(fmt, *, default_pct: float, axis_max: float = 100.0) -> float:
    """The value below which a data label is not worth drawing.

    A share of the value axis, never a number of units: on a true-width 0-465
    axis a one-unit sliver is invisible but would still be labelled, and the
    labels pile onto each other.

    `default_pct` is what the chart type has always used — 1% of the axis for a
    stack, 4% for a pie wedge, whose labels sit on a curve and run into each
    other sooner. The author's own cut-off, when they set one, wins: on a
    100%-stacked scale the whole tail (the 1%, the 2%, the 3%) lands in slivers
    narrower than the number that belongs in them, and where to stop drawing
    them depends on how wide the chart is and how much of the tail they are
    willing to lose. 0 is a real answer and means "draw every value", so this
    tests for None rather than falsiness.
    """
    pct = getattr(fmt, "hide_below_pct", None) if fmt else None
    if pct is None:
        pct = default_pct
    # Clamped where it is READ, so it means something wherever it came from: the
    # editor offers 0-100, but the API and the saved document take any number,
    # and a hand-edited -5 compares against widths as a floor below zero while
    # 500 takes every value off every chart.
    return axis_max * min(100.0, max(0.0, float(pct))) / 100.0


#: What a picture nSight drew a CHART into is called on the slide.
#:
#: The completeness check counts chart objects, and in image mode a chart IS a
#: picture — but so is a template's harvested furniture, which is redrawn with
#: `add_picture` by design. Counting every picture made one logo plus one chart
#: read as two charts where one was expected, and refused a deck that was
#: complete. Named, so the count can tell them apart.
CHART_PICTURE_NAME = "nsight-chart"


def name_chart_picture(pic):
    """Mark a placed picture as the slide's chart. Returns it, for chaining."""
    try:
        pic.name = CHART_PICTURE_NAME
    except Exception:  # noqa: BLE001 — a name is bookkeeping, never a render
        pass
    return pic


def format_value(v: float, statistic: str, fmt, all_values: list[float] | None = None) -> str:
    """Format a single data-label value, honouring NumberFormat.mode (REQ-N-01/02/03).

    mode='auto'   → choose decimals from all_values (or [v] if not supplied).
    mode='manual' → use fmt.pct_decimals / fmt.mean_decimals.

    Appends ' %' for pct when show_pct_sign is True.
    """
    show_sign = getattr(fmt, "show_pct_sign", True) if fmt else True
    mode = getattr(fmt, "mode", "auto") if fmt else "auto"

    if mode == "auto":
        vals = list(all_values) if all_values is not None else [float(v)]
        dec = auto_decimals(vals, statistic)
    else:
        if statistic == "pct":
            dec = getattr(fmt, "pct_decimals", 0) if fmt else 0
        elif statistic == "mean":
            dec = getattr(fmt, "mean_decimals", 1) if fmt else 1
        else:
            dec = 0

    if statistic == "pct":
        return f"{v:.{dec}f} %" if show_sign else f"{v:.{dec}f}"
    if statistic == "mean":
        return f"{v:.{dec}f}"
    return f"{v:.0f}"


def fmt_value(v: float, statistic: str, number_format=None) -> str:
    """Legacy label formatter — delegates to format_value (auto mode; single-value context).

    Prefer format_value(v, statistic, fmt, all_values) for correct auto-decimals.
    """
    return format_value(v, statistic, number_format, all_values=[v])


def new_square_figure(ctx):
    """Create a square matplotlib Figure sized to min(slot width, slot height).

    Used by pie, doughnut, and radar builders so the circle is not stretched
    when placed in a landscape slide slot.  Returns (fig, ax) with a cartesian
    Axes (caller replaces ax with a polar Axes if needed).
    """
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(4.5, ctx.slot.height / _EMU_PER_IN)
    sq = min(w_in, h_in)
    fig = _new_agg_figure(sq, sq)
    _remember_font(fig, ctx)
    ax = fig.subplots()
    bg = chart_background(ctx)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    return fig, ax


def place_picture_square(ctx, png_path: str, valign: str = "center") -> None:
    """Place a PNG in ctx.slot preserving the PNG's true aspect ratio (letterbox).

    Reads the PNG's real pixel dimensions and scales it to fit *inside* the slot
    (scale to the limiting dimension).  This keeps a circular pie/radar chart
    circular — even when ``bbox_inches="tight"`` trimmed the saved PNG
    asymmetrically — instead of squishing a non-square PNG into an oval.

    Horizontally always centred.  Vertically: ``valign='center'`` (default, for
    symmetric charts like pie/radar) or ``valign='top'`` (for bar/line/funnel
    charts, so the chart hugs the question text above it instead of floating in
    the middle of the slot with a big gap).
    """
    from PIL import Image

    with Image.open(png_path) as im:
        px_w, px_h = im.size

    slot_w = ctx.slot.width
    slot_h = ctx.slot.height
    # Scale to fit within the slot, preserving aspect ratio (never upscale-distort).
    #
    # …and never MAGNIFY. Every font in a chart is chosen in points — row labels
    # clamp at 11.5, value labels at 9.5, against a 13.8pt subtitle — and those
    # numbers were true of the figure but not of the slide. `bbox_inches="tight"`
    # trims the drawing to its ink, so a chart with short labels and bars
    # reaching 25 % saves a PNG far narrower than the figure it came from; this
    # then stretched it across the whole slot and took every point size with it.
    # Reported as "why is the chart font so big… it is now bigger than the
    # question subtitle" — measured at roughly 17pt for an 11.5pt label.
    #
    # A chart too big for its slot still shrinks, which is what letterboxing is
    # for. One that came out small is left at the size it was drawn, so a point
    # size means on the slide what it says in the builder. (Johan, 2026-09-17)
    scale = min(slot_w / px_w, slot_h / px_h, _EMU_PER_IN / _RENDER_DPI)
    disp_w = int(round(px_w * scale))
    disp_h = int(round(px_h * scale))
    left = ctx.slot.left + (slot_w - disp_w) // 2
    if valign == "top":
        top = ctx.slot.top
    else:
        top = ctx.slot.top + (slot_h - disp_h) // 2
    try:
        name_chart_picture(
            ctx.slide.shapes.add_picture(png_path, left, top, disp_w, disp_h))
    finally:
        # render_png() mkstemp'd this file and nothing else owns it: python-pptx
        # has copied the bytes into the package by now, so the temp copy is
        # dead weight. Without this every chart ever rendered leaks a PNG into
        # /tmp — 1572 of them had accumulated on this machine, and a
        # long-running container would eventually fill its disk.
        # finally, not a plain call: a failed add_picture must not leak either.
        try:
            os.unlink(png_path)
        except OSError:
            # Already gone, or a read-only temp dir. Not worth failing a render.
            pass


def style_legend(ax, ctx, loc: str = "best") -> None:
    """Apply house-style formatting to an axes legend (shared by all image builders).

    Transparent frame, a grid-tone edge, ink text (both derived from *ctx*'s
    slide background — light on dark, INK/GRIDC unchanged on light), 9.5 pt font.
    """
    ink, _muted, grid = chart_furniture(ctx)
    leg = ax.legend(fontsize=9.5, loc=loc, frameon=True)
    if leg is None:
        return
    # Transparent to match the figure: an opaque pill would reintroduce exactly
    # the panel the transparent save exists to avoid.
    leg.get_frame().set_facecolor("none")
    leg.get_frame().set_edgecolor(grid)
    leg.get_frame().set_linewidth(0.8)
    for t in leg.get_texts():
        t.set_color(ink)


def apply_axis_titles(ax, spec, ink: str) -> None:
    """Draw the author's axis titles on *ax*, if this chart has any.

    P-C-27's fourth text property. Empty means no axis title — the way every
    chart looked before the field existed — and `elements.axis_names` still
    governs axis text as a whole, so one control continues to mean "no axis
    text on this slide".

    Both renderers must agree about this: a preview that omits what the deck
    draws is exactly the class of bug the preview pipeline exists to prevent,
    so render/elements.py does the same thing for the native path.
    """
    elements = getattr(spec, "elements", None)
    if elements is not None and not getattr(elements, "axis_names", True):
        return
    x = getattr(spec, "axis_x_title", "") or ""
    y = getattr(spec, "axis_y_title", "") or ""
    if x:
        ax.set_xlabel(x, fontsize=10.5, color=ink)
    if y:
        ax.set_ylabel(y, fontsize=10.5, color=ink)
