# Several Pie Charts On One Slide — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pie, doughnut or funnel slide can be split by one background variable into up to three side-by-side charts, each its own 100%, with every omitted group named on the slide.

**Architecture:** One pure function, `panel_segments`, answers "which groups become panels?" — applying the existing base floor, excluding the bare `"Total"` segment, and capping at three. The feasibility check, the image renderers and the methodology footer all read that one answer, so they cannot disagree. The image pie renderer grows a panel loop of its own rather than borrowing the bar renderer's panel machinery, which measures axis furniture a pie does not have.

**Tech Stack:** Python 3.13, matplotlib (Agg), python-pptx, pytest (`uv run pytest`), React + TypeScript frontend (Vite, no test runner).

**Spec:** `docs/superpowers/specs/2026-08-22-multi-pie-panels-design.md`

## Global Constraints

- `MAX_PANELS = 3` — at most three pies on a slide.
- `MIN_SEGMENT_BASE = 10` — the existing base floor in `render/image/_mpl.py:233`. Import it; never redefine it.
- Panels are drawn in the **series' own segment order**, never reordered by base size. The cap *selects* by base; the row *displays* in order.
- Ties in the cap break on segment order, so selection is deterministic.
- A slide with **no** classifier must render byte-identically to today: one pie, no panel title, legend to the right.
- No `percent_base`, `classifying_var_2`, `xtab_layout` or `show_total` control is added to these three chart types.
- Every omission — thin base, cap, or a fully degraded split — is named in the slide footer.
- Commit after every task. Run `uv run pytest tests/suite -q` before each commit.

---

### Task 1: The panel-selection rule

The single source of truth every later task reads. Pure — no matplotlib, no pptx, no I/O.

**Files:**
- Create: `src/reportbuilder/render/panels.py`
- Test: `tests/suite/unit/render/test_panels.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `MAX_PANELS: int` (= 3)
  - `@dataclass(frozen=True) class PanelSelection` with fields `labels: tuple[str, ...]`, `thin: tuple[str, ...]`, `capped: tuple[str, ...]`, `degraded: bool`, `split: bool`
  - `def panel_segments(series) -> PanelSelection`

**Behaviour, exactly:**

| Input | `labels` | `split` | Notes |
|---|---|---|---|
| segments `("Total",)` | `("Total",)` | `False` | today's un-split slide |
| segments `("Naiset", "Miehet", "Total")`, all bases ≥ 10 | `("Naiset", "Miehet")` | `True` | `"Total"` is never a panel |
| one group with base 8 | that group lands in `thin` | `True` | base floor applies before the cap |
| five groups ≥ 10 | the three largest, in segment order | `True` | the other two land in `capped` |
| every group thin | `("Total",)`, `degraded=True` | `True` | must not be zero panels |

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/render/test_panels.py`:

```python
"""The one rule for which classifier groups become pie panels.

Read by the feasibility check, the image renderers and the methodology
footer alike — see docs/superpowers/specs/2026-08-22-multi-pie-panels-design.md.
"""
from __future__ import annotations

from reportbuilder.render.panels import MAX_PANELS, panel_segments
from reportbuilder.stats.series import Cell, SeriesResult


def _series(segments, bases) -> SeriesResult:
    cats = ("A", "B")
    cells = {(c, s): Cell(pct=50.0, count=1.0, mean=None)
             for c in cats for s in segments}
    return SeriesResult(categories=cats, segments=tuple(segments), cells=cells,
                        base_n=dict(bases), statistic="pct")


def test_no_classifier_is_not_split():
    sel = panel_segments(_series(("Total",), {"Total": 100}))
    assert sel.labels == ("Total",)
    assert sel.split is False
    assert sel.thin == () and sel.capped == () and sel.degraded is False


def test_total_is_never_a_panel():
    sel = panel_segments(_series(
        ("Naiset", "Miehet", "Total"),
        {"Naiset": 60, "Miehet": 40, "Total": 100}))
    assert sel.labels == ("Naiset", "Miehet")
    assert sel.split is True


def test_thin_group_is_dropped_and_named():
    sel = panel_segments(_series(
        ("Naiset", "Miehet", "Muut", "Total"),
        {"Naiset": 60, "Miehet": 40, "Muut": 8, "Total": 108}))
    assert sel.labels == ("Naiset", "Miehet")
    assert sel.thin == ("Muut",)


def test_cap_keeps_the_three_largest_in_segment_order():
    sel = panel_segments(_series(
        ("18-29", "30-44", "45-59", "60+", "Total"),
        {"18-29": 50, "30-44": 90, "45-59": 70, "60+": 30, "Total": 240}))
    # Largest three are 30-44, 45-59, 18-29 — but they DISPLAY in data order.
    assert sel.labels == ("18-29", "30-44", "45-59")
    assert sel.capped == ("60+",)
    assert len(sel.labels) == MAX_PANELS


def test_cap_ties_break_on_segment_order():
    sel = panel_segments(_series(
        ("A", "B", "C", "D", "Total"),
        {"A": 50, "B": 50, "C": 50, "D": 50, "Total": 200}))
    assert sel.labels == ("A", "B", "C")
    assert sel.capped == ("D",)


def test_all_groups_thin_degrades_to_total_not_to_nothing():
    sel = panel_segments(_series(
        ("Naiset", "Miehet", "Total"),
        {"Naiset": 4, "Miehet": 6, "Total": 10}))
    assert sel.labels == ("Total",)
    assert sel.degraded is True
    assert sel.split is True
    assert sel.thin == ("Naiset", "Miehet")


def test_one_surviving_group_still_counts_as_split():
    sel = panel_segments(_series(
        ("Naiset", "Miehet", "Total"),
        {"Naiset": 60, "Miehet": 3, "Total": 63}))
    assert sel.labels == ("Naiset",)
    assert sel.split is True
    assert sel.thin == ("Miehet",)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/suite/unit/render/test_panels.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reportbuilder.render.panels'`

- [ ] **Step 3: Write minimal implementation**

Create `src/reportbuilder/render/panels.py`:

```python
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

# The base floor is the renderer's own, defined once next to the segment filter it
# already guards (a tiny classifier group must never render a misleading 100%).
from reportbuilder.render.image._mpl import MIN_SEGMENT_BASE

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/suite/unit/render/test_panels.py -q`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/reportbuilder/render/panels.py tests/suite/unit/render/test_panels.py
git commit -m "feat(render): one answer to which groups become panels"
```

---

### Task 2: The three chart types gain a classifying variable

**Files:**
- Modify: `src/reportbuilder/render/config_schema.py:281-283`
- Modify: `tests/suite/unit/render/test_config_schema.py:182-189`

**Interfaces:**
- Consumes: nothing.
- Produces: `single_series_schema()` now returns keys `["statistic", "classifying_var", "sort", "number_format", "show_not_answered", "show_empty_categories", "not_answered_codes", "category_label_overrides"]`. Task 8 relies on `classifying_var` being present in the catalog for these types.

- [ ] **Step 1: Replace the existing test, which asserts the opposite**

`tests/suite/unit/render/test_config_schema.py` currently holds
`test_single_series_schema_omits_classifying_var`. Replace that whole function with:

```python
def test_single_series_schema_has_classifying_var_but_no_crosstab_controls():
    # Pie/doughnut/funnel split into one panel per group (spec 2026-08-22), so they
    # DO take a classifier — but never a second one, a cross-tab layout, or a Total
    # reference series, none of which a row of pies can express.
    keys = _keys(single_series_schema())
    assert keys == [
        "statistic", "classifying_var", "sort", "number_format",
        "show_not_answered", "show_empty_categories", "not_answered_codes",
        "category_label_overrides",
    ]
    for absent in ("classifying_var_2", "xtab_layout", "show_total", "percent_base"):
        assert absent not in keys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/suite/unit/render/test_config_schema.py -q`
Expected: FAIL — the returned keys have no `classifying_var`

- [ ] **Step 3: Write minimal implementation**

In `src/reportbuilder/render/config_schema.py`, replace `single_series_schema`:

```python
def single_series_schema() -> tuple[ConfigField, ...]:
    """Pie/doughnut/funnel: ONE classifying variable, drawn as up to three panels.

    No second classifier, no `xtab_layout`, no `show_total` — a row of pies can
    express none of them. The percentage direction needs no control either:
    `resolve_percent_base` always answers "classifier", so each panel already sums
    to 100% within its own group. (spec 2026-08-22-multi-pie-panels-design)
    """
    return (statistic_field(), classifying_var_field(), *_common_tail())
```

- [ ] **Step 4: Run the schema and catalog tests**

Run: `uv run pytest tests/suite/unit/render/test_config_schema.py tests/rb/api/test_chart_types.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole suite to find what else assumed single-series**

Run: `uv run pytest tests/suite -q`
Expected: PASS. If a test fails because it assumed pie has no classifier, fix that test to the new intent — do not weaken the schema.

- [ ] **Step 6: Commit**

```bash
git add src/reportbuilder/render/config_schema.py tests/suite/unit/render/test_config_schema.py
git commit -m "feat(charts): a pie may be split by one background variable"
```

---

### Task 3: Feasibility judges every panel, not the first series

Without this the chart type **disappears from the picker** the moment a classifier is set: `_is_parts_of_whole` returns False for `n_series != 1`, and both `pie_suitability` and `pie_suggest` return None through it.

**Files:**
- Modify: `src/reportbuilder/render/charts/pie.py:50-57`
- Modify: `tests/suite/unit/render/test_suitability_matrix.py:59-60`
- Modify: `tests/suite/unit/render/_builders.py` (add one builder)

**Interfaces:**
- Consumes: `panel_segments` from Task 1.
- Produces: `_is_parts_of_whole(question, series)` now True when every drawn panel partitions its own base. `charts/doughnut.py` imports `pie_suitability` and inherits this unchanged.

- [ ] **Step 1: Add a builder for a split whose thin group fails to partition**

Append to `tests/suite/unit/render/_builders.py`:

```python
def split_partition_series() -> SeriesResult:
    """2 classifier groups + Total; EVERY group partitions its own base."""
    s = build_series(("Yes", "No"), segs=("Naiset", "Miehet", "Total"),
                     statistic="pct", base=100,
                     pct={"Yes": 60.0, "No": 40.0},
                     count={"Yes": 60.0, "No": 40.0})
    return s


def split_with_nonpartition_group_series() -> SeriesResult:
    """2 classifier groups; the SECOND does not partition its base (counts fall
    far short), so a pie of it would not add up."""
    cells = {}
    for c, pct, cnt in (("Yes", 60.0, 60.0), ("No", 40.0, 40.0)):
        cells[(c, "Naiset")] = Cell(pct=pct, count=cnt, mean=None)
        cells[(c, "Total")] = Cell(pct=pct, count=cnt, mean=None)
        cells[(c, "Miehet")] = Cell(pct=pct, count=cnt / 4.0, mean=None)
    return SeriesResult(categories=("Yes", "No"),
                        segments=("Naiset", "Miehet", "Total"), cells=cells,
                        base_n={"Naiset": 100, "Miehet": 100, "Total": 200},
                        statistic="pct")
```

- [ ] **Step 2: Write the failing tests**

In `tests/suite/unit/render/test_suitability_matrix.py`, replace
`test_pie_none_for_multi_series` with:

```python
def test_pie_offered_for_a_split_where_every_panel_partitions():
    # A pie split by a background variable is one pie per group (spec 2026-08-22).
    # The old rule rejected any multi-series outright, which would have made the
    # chart type vanish from the picker the moment a classifier was chosen.
    assert plugin("pie").suitability(B.q(), B.split_partition_series()) is not None


def test_pie_dropped_when_a_drawn_panel_does_not_partition():
    # A question can partition overall and still fail inside one group; that
    # group's pie would be the one that quietly does not add up.
    s = B.split_with_nonpartition_group_series()
    assert plugin("pie").suitability(B.q(), s) is None
    assert plugin("doughnut").suitability(B.q(), s) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/suite/unit/render/test_suitability_matrix.py -q`
Expected: FAIL — `test_pie_offered_for_a_split_where_every_panel_partitions` gets None

- [ ] **Step 4: Write minimal implementation**

In `src/reportbuilder/render/charts/pie.py`, add the import and replace `_is_parts_of_whole`:

```python
from reportbuilder.render.panels import panel_segments
```

```python
def _is_parts_of_whole(question, series) -> bool:
    """The structural precondition shared by pie and doughnut.

    With a classifier the chart is one pie PER GROUP, so the question is asked of
    every panel that will actually be drawn: a question can partition the whole
    sample and still fail inside a thin group, and that group's pie is the one that
    would not add up. Groups that will NOT be drawn — dropped for a thin base or
    beyond the three-panel cap — cannot veto the chart type, because nothing will
    render them. (spec 2026-08-22)
    """
    s = SeriesShape.of(question, series)
    if s.statistic not in ADDITIVE_STATISTICS:
        return False
    panels = panel_segments(series).labels
    if not panels:
        return False
    return all(series.is_partition(seg, undershoot_tol=_UNDERSHOOT_TOL_PCT)
               for seg in panels)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/suite/unit/render/test_suitability_matrix.py -q`
Expected: PASS

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest tests/suite tests/rb -q -m "not judge and not integration"`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/reportbuilder/render/charts/pie.py tests/suite/unit/render/test_suitability_matrix.py tests/suite/unit/render/_builders.py
git commit -m "fix(charts): a split pie is judged panel by panel, not rejected outright"
```

---

### Task 4: The image renderer draws the panel row

**Files:**
- Modify: `src/reportbuilder/render/image/pie.py`
- Test: `tests/suite/unit/render/test_pie_panels.py`

**Interfaces:**
- Consumes: `panel_segments`, `PanelSelection` from Task 1.
- Produces: `_build_pie_figure(ctx, *, donut: bool) -> Figure` — builds the figure without placing it, so tests can inspect axes, titles and x-labels. `_render_pie` becomes a two-liner over it. `build_image_pie` / `build_image_doughnut` keep their signatures.

**Layout contract:**
- Un-split (`split=False`): one axes, `get_title() == ""`, legend to the right — today's slide, unchanged.
- Split: one axes per label, `get_title()` is the group label, `get_xlabel()` is `f"n = {base}"`, one shared legend below the row.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/render/test_pie_panels.py`:

```python
"""A pie split by a background variable draws one titled panel per group."""
from __future__ import annotations

from reportbuilder.render.image.pie import _build_pie_figure
from reportbuilder.stats.series import Cell, SeriesResult

from suite._helpers import make_ctx


def _series(segments, bases, *, statistic="pct") -> SeriesResult:
    cats = ("En voi", "Kyllä voin")
    cells = {(c, s): Cell(pct=50.0, count=float(bases[s]) / 2, mean=None)
             for c in cats for s in segments}
    return SeriesResult(categories=cats, segments=tuple(segments), cells=cells,
                        base_n=dict(bases), statistic=statistic)


def _pie_axes(fig):
    return list(fig.axes)


def test_unsplit_pie_is_a_single_untitled_panel():
    series = _series(("Total",), {"Total": 1023})
    _prs, _slide, _slot, ctx = make_ctx("pie", series)
    fig = _build_pie_figure(ctx, donut=False)
    axes = _pie_axes(fig)
    assert len(axes) == 1
    assert axes[0].get_title() == ""
    assert axes[0].get_xlabel() == ""


def test_three_groups_draw_three_titled_panels_in_segment_order():
    series = _series(("Naiset", "Miehet", "Muut", "Total"),
                     {"Naiset": 512, "Miehet": 486, "Muut": 25, "Total": 1023})
    _prs, _slide, _slot, ctx = make_ctx("pie", series, classifying_var="sex")
    fig = _build_pie_figure(ctx, donut=False)
    axes = _pie_axes(fig)
    assert [ax.get_title() for ax in axes] == ["Naiset", "Miehet", "Muut"]
    assert [ax.get_xlabel() for ax in axes] == ["n = 512", "n = 486", "n = 25"]


def test_five_groups_draw_only_the_three_largest():
    series = _series(("18-29", "30-44", "45-59", "60+", "Total"),
                     {"18-29": 50, "30-44": 90, "45-59": 70, "60+": 30,
                      "Total": 240})
    _prs, _slide, _slot, ctx = make_ctx("pie", series, classifying_var="age")
    fig = _build_pie_figure(ctx, donut=False)
    assert [ax.get_title() for ax in _pie_axes(fig)] == ["18-29", "30-44", "45-59"]


def test_count_statistic_split_draws_no_total_panel():
    # show_total resolves True for a count statistic, so "Total" survives into
    # `segments`; it must still never become a fourth circle. (spec 2026-08-22)
    series = _series(("Naiset", "Miehet", "Total"),
                     {"Naiset": 60, "Miehet": 40, "Total": 100},
                     statistic="count")
    _prs, _slide, _slot, ctx = make_ctx("pie", series, classifying_var="sex",
                                        statistic="count")
    fig = _build_pie_figure(ctx, donut=False)
    assert [ax.get_title() for ax in _pie_axes(fig)] == ["Naiset", "Miehet"]


def test_all_groups_thin_degrades_to_one_whole_sample_pie():
    series = _series(("Naiset", "Miehet", "Total"),
                     {"Naiset": 4, "Miehet": 6, "Total": 10})
    _prs, _slide, _slot, ctx = make_ctx("pie", series, classifying_var="sex")
    fig = _build_pie_figure(ctx, donut=False)
    axes = _pie_axes(fig)
    assert len(axes) == 1
    assert axes[0].get_title() == ""


def test_panel_percentages_are_the_engine_s_own_numbers():
    """The invariant that keeps the slice labels honest.

    `resolve_percent_base` always answers "classifier", so each group already sums
    to 100% before the renderer sees it — which makes `_draw_one_pie`'s
    renormalisation a no-op. Were the engine ever to hand over "% of total sample"
    instead, the renderer would silently rewrite those numbers and the printed
    percentages would stop being the ones the engine computed. (spec 2026-08-22)
    """
    cats = ("En voi", "Kyllä voin")
    cells = {}
    for seg, (a, b) in (("Naiset", (54.0, 46.0)), ("Miehet", (41.0, 59.0)),
                        ("Total", (48.0, 52.0))):
        cells[("En voi", seg)] = Cell(pct=a, count=a, mean=None)
        cells[("Kyllä voin", seg)] = Cell(pct=b, count=b, mean=None)
    series = SeriesResult(categories=cats, segments=("Naiset", "Miehet", "Total"),
                          cells=cells,
                          base_n={"Naiset": 512, "Miehet": 486, "Total": 998},
                          statistic="pct")
    _prs, _slide, _slot, ctx = make_ctx("pie", series, classifying_var="sex")
    fig = _build_pie_figure(ctx, donut=False)
    naiset = fig.axes[0]
    printed = [t.get_text() for t in naiset.texts if t.get_text()]
    assert any("54" in t for t in printed), printed
    assert any("46" in t for t in printed), printed


def test_split_pie_places_exactly_one_picture():
    from reportbuilder.render.image.pie import build_image_pie
    from suite._helpers import assert_single_picture

    series = _series(("Naiset", "Miehet", "Total"),
                     {"Naiset": 512, "Miehet": 486, "Total": 998})
    _prs, slide, slot, ctx = make_ctx("pie", series, classifying_var="sex")
    build_image_pie(ctx)
    assert_single_picture(slide, slot)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/suite/unit/render/test_pie_panels.py -q`
Expected: FAIL — `ImportError: cannot import name '_build_pie_figure'`

- [ ] **Step 3: Write the implementation**

In `src/reportbuilder/render/image/pie.py`, add the import:

```python
from reportbuilder.render.panels import panel_segments
```

Add the panel figure builder next to `_make_square_fig_ax`:

```python
# Vertical share of the figure reserved for the shared legend under a panel row.
_PANEL_LEGEND_FRAC: float = 0.18
# Gap between neighbouring panels, as a fraction of one panel's width. Pies have no
# axis furniture to keep apart, so this only has to stop two circles touching.
_PANEL_GAP_FRAC: float = 0.06


def _make_panel_axes(ctx, bg: str, n_panels: int):
    """A wide figure holding `n_panels` EQUAL square pie axes in one row, with room
    for a shared legend beneath them.

    Each axes is square and `set_aspect("equal")`, so every circle stays a circle;
    `place_picture_square` then scales the whole PNG on its limiting dimension and
    preserves that geometry in the slot.
    """
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(4.5, ctx.slot.height / _EMU_PER_IN)
    fig = Figure(figsize=(w_in, h_in), dpi=200)
    FigureCanvasAgg(fig)
    fig.patch.set_facecolor(bg)

    bottom = _PANEL_LEGEND_FRAC
    height = 1.0 - bottom - 0.10          # 0.10 leaves room for the panel titles
    span = 1.0 / n_panels
    axes = []
    for i in range(n_panels):
        left = i * span + span * _PANEL_GAP_FRAC / 2.0
        width = span * (1.0 - _PANEL_GAP_FRAC)
        ax = fig.add_axes([left, bottom, width, height])
        ax.set_facecolor(bg)
        axes.append(ax)
    return fig, axes
```

Replace `_render_pie` with a figure builder plus a thin renderer:

```python
def _draw_one_pie(ax, cats, vals, clrs, statistic, fmt, bg: str, donut: bool):
    """Draw a single pie onto `ax`. Returns its wedge artists."""
    total = sum(v or 0.0 for v in vals) or 1.0
    fracs = [(v or 0.0) / total * 100.0 for v in vals]

    def _autopct(pct: float) -> str:
        return format_value(pct, statistic, fmt, fracs) if pct >= _MIN_WEDGE_PCT else ""

    wedgeprops = dict(linewidth=1.4, edgecolor=bg)
    if donut:
        wedgeprops["width"] = 0.42

    wedges, _texts, autotexts = ax.pie(
        vals, labels=None, colors=clrs, autopct=_autopct,
        pctdistance=0.80 if donut else 0.72,
        startangle=90, counterclock=False, wedgeprops=wedgeprops,
    )
    ax.set_aspect("equal")
    for t, wedge in zip(autotexts, wedges):
        t.set_fontsize(10.0)
        t.set_fontweight("bold")
        t.set_color(contrast_ink(wedge.get_facecolor()))
    return wedges


def _build_pie_figure(ctx, *, donut: bool):
    """Build the figure for a pie/doughnut slide — one panel, or one per classifier
    group (spec 2026-08-22). Returns the Figure; placing it is the caller's job."""
    from matplotlib.patches import Patch

    series = ctx.series
    sel = panel_segments(series)
    cats = list(series.categories)
    clrs = series_colors(len(cats), palette=template_palette(ctx),
                          accent=chart_accent(ctx))
    clrs = [MUTED if c == NOT_ANSWERED_LABEL else clr for c, clr in zip(cats, clrs)]

    statistic = series.statistic
    fmt = ctx.spec.number_format
    bg = chart_background(ctx)
    ink, _muted, grid = chart_furniture(ctx)
    want_legend = bool(ctx.spec.elements.axis_names or ctx.spec.elements.legend)

    def _values(seg):
        return [float(series.cell(c, seg).value(statistic) or 0.0) for c in cats]

    if not sel.split or len(sel.labels) == 1:
        # One circle: the un-split slide, or a split that degraded to one panel.
        # Kept on the ORIGINAL layout (legend to the right) so existing slides do
        # not shift.
        fig, ax = _make_square_fig_ax(ctx, bg)
        seg = sel.labels[0]
        wedges = _draw_one_pie(ax, cats, _values(seg), clrs, statistic, fmt, bg, donut)
        if sel.split and not sel.degraded:
            # One group survived: the reader must be told WHICH group this is.
            ax.set_title(seg, fontsize=12.5, fontweight="bold", color=ink, pad=6)
            ax.set_xlabel(f"n = {series.base_n.get(seg, 0)}", fontsize=9.5, color=ink)
        if want_legend:
            _add_category_legend(fig, ax, wedges, cats, [], statistic, fmt,
                                  bg, ink, grid)
        return fig

    fig, axes = _make_panel_axes(ctx, bg, len(sel.labels))
    for ax, seg in zip(axes, sel.labels):
        _draw_one_pie(ax, cats, _values(seg), clrs, statistic, fmt, bg, donut)
        ax.set_title(_wrap_legend_label(seg), fontsize=12.5, fontweight="bold",
                     color=ink, pad=6)
        ax.set_xlabel(f"n = {series.base_n.get(seg, 0)}", fontsize=9.5, color=ink)

    if want_legend:
        # ONE legend for the row: the categories are identical in every panel, so a
        # legend per panel would be the same list three times.
        handles = [Patch(facecolor=clrs[i], edgecolor="none") for i in range(len(cats))]
        leg = fig.legend(handles, [_wrap_legend_label(c) for c in cats],
                         loc="lower center", ncol=min(len(cats), 4),
                         frameon=True, fontsize=10.5, bbox_to_anchor=(0.5, 0.01))
        leg.get_frame().set_facecolor(bg)
        leg.get_frame().set_edgecolor(grid)
        leg.get_frame().set_linewidth(0.8)
        for t in leg.get_texts():
            t.set_color(ink)
    return fig


def _render_pie(ctx, *, donut: bool) -> None:
    """Shared pie/doughnut renderer — circular, fully contained, labels never overlap."""
    place_picture_square(ctx, render_png(_build_pie_figure(ctx, donut=donut)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/suite/unit/render/test_pie_panels.py -q`
Expected: PASS, 6 passed

- [ ] **Step 5: Verify no existing pie slide shifted**

Run: `uv run pytest tests/rb/render -q -m "not judge and not integration"`
Expected: PASS — the un-split path must be untouched.

- [ ] **Step 6: Look at it**

The tests assert structure — panel count, titles, bases — and structure is not
appearance. Three circles can be correctly titled and still be cramped, overlap
their legend, or lose their percentage labels at panel size. Render one and look:

```bash
uv run python - <<'EOF'
from reportbuilder.render.image.pie import _build_pie_figure
from reportbuilder.render.image._mpl import render_png
from reportbuilder.stats.series import Cell, SeriesResult
import sys; sys.path.insert(0, "tests")
from suite._helpers import make_ctx

cats = ("En voi", "Kyllä voin")
cells = {}
for seg, (a, b) in (("Naiset", (54.0, 46.0)), ("Miehet", (41.0, 59.0)),
                    ("Muut", (60.0, 40.0)), ("Total", (48.0, 52.0))):
    cells[("En voi", seg)] = Cell(pct=a, count=a, mean=None)
    cells[("Kyllä voin", seg)] = Cell(pct=b, count=b, mean=None)
s = SeriesResult(categories=cats,
                 segments=("Naiset", "Miehet", "Muut", "Total"), cells=cells,
                 base_n={"Naiset": 512, "Miehet": 486, "Muut": 25, "Total": 1023},
                 statistic="pct")
_prs, _slide, _slot, ctx = make_ctx("pie", s, classifying_var="sex")
png = render_png(_build_pie_figure(ctx, donut=False))
import shutil; shutil.copy(png, "work/pie_panels_check.png")
print("wrote work/pie_panels_check.png")
EOF
```

Open `work/pie_panels_check.png` and check: three circles of equal size, none
clipped; group names legible above each; `n = …` under each; one legend beneath the
row, not overlapping the circles; percentage labels still readable at panel size.
If the on-slice labels have become too small or crowded, raise `_MIN_WEDGE_PCT` for
the panel path — every value is still in the legend.

**Write the PNG to `work/`, not `/tmp`** — `/tmp` is a ramfs on this machine and
image output there consumes RAM.

- [ ] **Step 7: Commit**

```bash
git add src/reportbuilder/render/image/pie.py tests/suite/unit/render/test_pie_panels.py
git commit -m "feat(render): two or three pies in a row, one per group"
```

---

### Task 5: The footer names what was left out

**Files:**
- Modify: `src/reportbuilder/render/elements.py:146-180`
- Modify: `tests/suite/unit/render/test_filter_annotation.py`

**Interfaces:**
- Consumes: `panel_segments` from Task 1.
- Produces: `add_filter_annotation` unchanged in signature; its textbox now wraps and is `Inches(5.5)` wide.

**Copy, exactly:**
- thin only: `"{var} · Ei raportoitu: {a}, {b}"`
- capped only: `"{var} · Ei mahtunut sivulle: {a}"`
- both: `"{var} · Ei raportoitu: {a} · Ei mahtunut sivulle: {b}"`
- degraded: `"{var} · Ryhmittelyä ei voitu piirtää"`

- [ ] **Step 1: Write the failing tests**

Append to `tests/suite/unit/render/test_filter_annotation.py`:

```python
from reportbuilder.stats.series import Cell as _Cell, SeriesResult as _Series


def _split_series(segments, bases):
    cats = ("A", "B")
    cells = {(c, s): _Cell(pct=50.0, count=1.0, mean=None)
             for c in cats for s in segments}
    return _Series(categories=cats, segments=tuple(segments), cells=cells,
                   base_n=dict(bases), statistic="pct")


def test_capped_group_is_named_in_the_footer():
    s = _split_series(("18-29", "30-44", "45-59", "60+", "Total"),
                      {"18-29": 50, "30-44": 90, "45-59": 70, "60+": 30,
                       "Total": 240})
    _prs, slide, _slot, ctx = make_ctx("pie", s, classifying_var="age")
    add_filter_annotation(ctx)
    text = " ".join(_texts(slide))
    assert "60+" in text
    assert "Ei mahtunut sivulle" in text


def test_thin_group_is_named_and_distinguished_from_a_capped_one():
    s = _split_series(("Naiset", "Miehet", "Muut", "Total"),
                      {"Naiset": 60, "Miehet": 40, "Muut": 4, "Total": 104})
    _prs, slide, _slot, ctx = make_ctx("pie", s, classifying_var="sex")
    add_filter_annotation(ctx)
    text = " ".join(_texts(slide))
    assert "Ei raportoitu" in text and "Muut" in text
    assert "Ei mahtunut sivulle" not in text


def test_unaffected_split_names_only_the_variable():
    s = _split_series(("Naiset", "Miehet", "Total"),
                      {"Naiset": 60, "Miehet": 40, "Total": 100})
    _prs, slide, _slot, ctx = make_ctx("pie", s, classifying_var="sex")
    add_filter_annotation(ctx)
    text = " ".join(_texts(slide))
    assert "sex" in text
    assert "Ei raportoitu" not in text and "Ei mahtunut sivulle" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/suite/unit/render/test_filter_annotation.py -q`
Expected: FAIL — the footer prints only `"sex"`

- [ ] **Step 3: Write the implementation**

In `src/reportbuilder/render/elements.py`, add near the top:

```python
from reportbuilder.render.panels import panel_segments
```

Add the clause builder above `add_filter_annotation`:

```python
def _omission_clause(ctx) -> str:
    """The footer's record of every classifier group the slide did NOT draw.

    The editor's warning stays in the editor; this line travels with the deck, so
    it is the authoritative account of what was omitted. The two reasons are kept
    apart because they mean different things to a reader: a group omitted for a
    thin base could not be reported at all, while a capped group fits the data but
    not the page. (spec 2026-08-22)
    """
    sel = panel_segments(ctx.series)
    if not sel.split:
        return ""
    if sel.degraded:
        return " · Ryhmittelyä ei voitu piirtää"
    parts = []
    if sel.thin:
        parts.append("Ei raportoitu: " + ", ".join(sel.thin))
    if sel.capped:
        parts.append("Ei mahtunut sivulle: " + ", ".join(sel.capped))
    return (" · " + " · ".join(parts)) if parts else ""
```

In `add_filter_annotation`, widen the box, turn on wrapping and append the clause.
Replace the `width = int(Inches(3.0))` line with `width = int(Inches(5.5))`, and
replace the `tf.text = ...` block with:

```python
    tf.word_wrap = True
    opts = getattr(ctx.spec, "options", None) or {}
    cv2 = getattr(ctx.spec, "classifying_var_2", None)
    if cv2 and opts.get("xtab_layout") == "separate":
        tf.text = f"{ctx.spec.classifying_var} · {cv2}"
    else:
        tf.text = f"{ctx.spec.classifying_var}{_omission_clause(ctx)}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/suite/unit/render/test_filter_annotation.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/reportbuilder/render/elements.py tests/suite/unit/render/test_filter_annotation.py
git commit -m "feat(render): the footer names the groups that did not fit"
```

---

### Task 6: The native builders stop guessing which segment they drew

`series_chart_data` adds **every** segment as a chart series and PowerPoint draws only the first, so a native split pie would render one group's distribution looking exactly like a whole-sample slide. Unreachable from the web app, which is what makes it easy to ship and never notice. `native/funnel.py:48` already names the `"Total"` cell and shows the fix.

**Files:**
- Modify: `src/reportbuilder/render/native/pie.py:31`
- Modify: `src/reportbuilder/render/native/doughnut.py:31`
- Test: `tests/suite/unit/render/test_native_pie_total.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `total_chart_data(series, statistic) -> CategoryChartData` in `native/column.py` — one series, the `"Total"` segment.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/render/test_native_pie_total.py`:

```python
"""A native pie must draw the whole sample, never whichever group came first.

PowerPoint renders only the first series of a pie, so handing it every classifier
group would produce one group's distribution wearing the whole sample's clothes.
(spec 2026-08-22)
"""
from __future__ import annotations

from reportbuilder.render.native.pie import build_pie
from reportbuilder.stats.series import Cell, SeriesResult

from suite._helpers import make_ctx


def _split_series() -> SeriesResult:
    cats = ("Yes", "No")
    # The FIRST group is lopsided; the Total is even. If the builder grabs the
    # first segment, the drawn values are 90/10 instead of 50/50.
    per_seg = {"Naiset": (90.0, 10.0), "Miehet": (10.0, 90.0), "Total": (50.0, 50.0)}
    cells = {}
    for seg, (a, b) in per_seg.items():
        cells[("Yes", seg)] = Cell(pct=a, count=a, mean=None)
        cells[("No", seg)] = Cell(pct=b, count=b, mean=None)
    return SeriesResult(categories=cats, segments=("Naiset", "Miehet", "Total"),
                        cells=cells,
                        base_n={"Naiset": 100, "Miehet": 100, "Total": 200},
                        statistic="pct")


def test_native_pie_draws_the_total_not_the_first_group():
    _prs, _slide, _slot, ctx = make_ctx("pie", _split_series(),
                                        classifying_var="sex")
    gf = build_pie(ctx)
    plot = gf.chart.plots[0]
    assert len(plot.series) == 1, "a pie must be handed exactly one series"
    assert list(plot.series[0].values) == [50.0, 50.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/suite/unit/render/test_native_pie_total.py -q`
Expected: FAIL — three series present, values `[90.0, 10.0]`

- [ ] **Step 3: Write the implementation**

In `src/reportbuilder/render/native/column.py`, add beside `series_chart_data`:

```python
def total_chart_data(series: SeriesResult, statistic: str) -> CategoryChartData:
    """CategoryChartData holding ONLY the "Total" segment.

    For the chart types PowerPoint draws from a single series — pie, doughnut.
    Handing them every classifier segment silently renders the first group as
    though it were the whole sample. `base_n["Total"]` is contractually always
    present, and so is the matching cell. (spec 2026-08-22)
    """
    cd = CategoryChartData()
    cd.categories = series.categories
    cd.add_series("Total", tuple(_value_for(series, c, "Total", statistic)
                                  for c in series.categories))
    return cd
```

In `src/reportbuilder/render/native/pie.py` and `src/reportbuilder/render/native/doughnut.py`, change the import and the one call:

```python
from reportbuilder.render.native.column import total_chart_data
```

```python
    cd = total_chart_data(ctx.series, ctx.series.statistic)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/suite/unit/render/test_native_pie_total.py -q`
Expected: PASS

- [ ] **Step 5: Run the native render tests**

Run: `uv run pytest tests/rb -q -m "not judge and not integration" -k "native or render"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/reportbuilder/render/native/ tests/suite/unit/render/test_native_pie_total.py
git commit -m "fix(render): a native pie draws the whole sample, not the first group"
```

---

### Task 7: Funnel gets the same split

Not a free rider: its renderer reads `data[segs[0]]` and its `suitability` scores `n_series != 1` down to 0.30. This is the least-used of the three types and the safest task to defer if the plan must be cut — everything above works without it.

**Files:**
- Modify: `src/reportbuilder/render/image/funnel.py:32-33`
- Modify: `src/reportbuilder/render/charts/funnel.py:12-25`
- Test: `tests/suite/unit/render/test_funnel_panels.py`

**Interfaces:**
- Consumes: `panel_segments` from Task 1.
- Produces: no new public names.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/render/test_funnel_panels.py`:

```python
"""A funnel split by a background variable draws one funnel per group."""
from __future__ import annotations

from reportbuilder.render.charts.funnel import suitability
from reportbuilder.render.image.funnel import build_image_funnel
from reportbuilder.stats.series import Cell, SeriesResult

from suite._helpers import assert_single_picture, make_ctx
from suite.unit.render._builders import q


def _descending_split() -> SeriesResult:
    cats = ("Tuntee", "Harkitsee", "Ostanut")
    cells = {}
    for seg, scale in (("Naiset", 1.0), ("Miehet", 0.8), ("Total", 0.9)):
        for c, v in zip(cats, (90.0, 60.0, 30.0)):
            cells[(c, seg)] = Cell(pct=v * scale, count=v * scale, mean=None)
    return SeriesResult(categories=cats, segments=("Naiset", "Miehet", "Total"),
                        cells=cells,
                        base_n={"Naiset": 100, "Miehet": 100, "Total": 200},
                        statistic="pct")


def test_split_funnel_is_still_offered():
    # The old rule scored any multi-series down to 0.30, which would have buried
    # the funnel in the picker the moment a classifier was chosen.
    assert suitability(q(), _descending_split()) == 0.85


def test_split_funnel_places_one_picture():
    _prs, slide, slot, ctx = make_ctx("funnel", _descending_split(),
                                      classifying_var="sex")
    build_image_funnel(ctx)
    assert_single_picture(slide, slot)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/suite/unit/render/test_funnel_panels.py -q`
Expected: FAIL — `suitability` returns 0.30

- [ ] **Step 3: Rewrite the funnel suitability**

In `src/reportbuilder/render/charts/funnel.py`:

```python
from reportbuilder.render.panels import panel_segments
```

```python
def suitability(question, series) -> float | None:
    """High for an ordered-descending series, judged on every panel drawn.

    Descending-ness is a value property, not captured by the structural
    SeriesShape, so it is read from the data. With a classifier the funnel is one
    funnel PER GROUP (spec 2026-08-22), so every drawn panel must descend — a
    group that climbs would get a funnel pointing the wrong way.
    """
    s = SeriesShape.of(question, series)
    if s.n_categories < 3:
        return 0.30
    panels = panel_segments(series).labels
    if not panels:
        return 0.30
    for seg in panels:
        vals = [series.cell(c, seg).value(series.statistic) or 0.0
                for c in series.categories]
        if not all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)):
            return 0.50
    return 0.85
```

- [ ] **Step 4: Give the funnel renderer its panel row**

In `src/reportbuilder/render/image/funnel.py`, extend the imports:

```python
from reportbuilder.render.image._mpl import (
    new_figure, new_figure_grid, render_png, place_picture, format_value, wrap_label,
    chart_background, chart_furniture,
)
from reportbuilder.render.panels import panel_segments
```

(`series_values` is no longer used — the panel list comes from `panel_segments` and
the values are read from the series directly.)

Extract the existing drawing body verbatim into a per-panel helper:

```python
def _draw_one_funnel(ax, cats, vals, ctx, bg: str, ink: str) -> None:
    """Draw one funnel silhouette onto `ax` — the body this module always had."""
    max_val = max(vals) if vals else 1.0
    bar_h = 0.60
    all_vals = [v for v in vals if v is not None]

    for i, (cat, v) in enumerate(zip(cats, vals)):
        # Centre the bar on the x-axis (symmetric funnel silhouette)
        left = (max_val - v) / 2
        ax.barh(i, v, left=left, height=bar_h, color=TEAL, edgecolor=bg,
                linewidth=0.8, zorder=3)
        lbl = format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals)
        ax.text(left + v / 2, i, lbl, ha="center", va="center",
                fontsize=10.5, fontweight="bold", color="#FFFFFF", zorder=5)

    for i, cat in enumerate(cats):
        ax.text(max_val * 1.04, i, wrap_label(cat, 28), va="center", ha="left",
                fontsize=11.0, color=ink, zorder=5)

    ax.invert_yaxis()
    ax.set_xlim(0, max_val * 2.05)
    ax.axis("off")
```

Then replace `build_image_funnel` with the panel dispatcher:

```python
def build_image_funnel(ctx) -> None:
    """Centered horizontal bar funnel (widest category on top) with house style.

    With a classifying variable, one funnel per group side by side — the same
    panel rule the pie uses. (REQ-C-24b/f, REQ-C-27a; spec 2026-08-22)
    """
    sel = panel_segments(ctx.series)
    cats = list(ctx.series.categories)
    bg = chart_background(ctx)
    ink, _muted, _grid = chart_furniture(ctx)

    def _values(seg):
        return [float(ctx.series.cell(c, seg).value(ctx.series.statistic) or 0.0)
                for c in cats]

    def _label(seg) -> str:
        # `ax.axis("off")` hides the x-axis label, so the base rides in the title's
        # second line rather than under the funnel as it does on a pie.
        return f"{wrap_label(seg, 20)}\nn = {ctx.series.base_n.get(seg, 0)}"

    if not sel.split or len(sel.labels) == 1:
        fig, ax = new_figure(ctx)
        seg = sel.labels[0]
        _draw_one_funnel(ax, cats, _values(seg), ctx, bg, ink)
        if sel.split and not sel.degraded:
            # One group survived: the reader must be told WHICH group this is.
            ax.set_title(_label(seg), fontsize=12.5, fontweight="bold",
                         color=ink, pad=6)
    else:
        # Every panel draws the same categories, so the shared y-axis is correct.
        fig, axes = new_figure_grid(ctx, len(sel.labels))
        for ax, seg in zip(axes, sel.labels):
            _draw_one_funnel(ax, cats, _values(seg), ctx, bg, ink)
            ax.set_title(_label(seg), fontsize=12.5, fontweight="bold",
                         color=ink, pad=6)

    place_picture(ctx, render_png(fig))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/suite/unit/render/test_funnel_panels.py -q`
Expected: PASS

- [ ] **Step 6: Run the full backend suite**

Run: `uv run pytest tests/suite tests/rb -q -m "not judge and not integration"`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/reportbuilder/render/image/funnel.py src/reportbuilder/render/charts/funnel.py tests/suite/unit/render/test_funnel_panels.py
git commit -m "feat(render): a funnel splits into one panel per group too"
```

---

### Task 8: The configure panel warns before the render

**The frontend has no test runner** — `web/package.json` offers only `dev`, `build`, `lint`, `preview`. So this task is verified by typecheck, lint and explicit manual steps, not by an automated test. The backend guarantee that actually holds the behaviour up is Task 2's schema test.

**Files:**
- Modify: `web/src/components/wizard/StepConfigure.tsx` (the classifier `Field` component, around line 384-470)

**Interfaces:**
- Consumes: Task 2's schema — `classifying_var` present in the catalog for `pie`, `doughnut`, `funnel`.
- Produces: no exported names.

- [ ] **Step 1: Add the warning**

Inside the classifier field component, after the existing `const key = field.key as ...` line, add:

```tsx
  // Pie/doughnut/funnel draw one chart per group and a 4:3 slide holds three.
  // Warn on the VARIABLE's own value count — the renderer's own count can be
  // lower (thin groups drop out), so this is advisory and the slide footer is the
  // authoritative record. (spec 2026-08-22)
  const PANEL_CHART_TYPES = ["pie", "doughnut", "funnel"];
  const MAX_PANELS = 3;
  const chosen = key === "classifying_var" && current
    ? (variables ?? []).find((v) => v.name === current)
    : undefined;
  const tooManyGroups =
    PANEL_CHART_TYPES.includes(chart.chart_type) &&
    (chosen?.n_values ?? 0) > MAX_PANELS;
```

Then render the notice **inside the `<Field>`, immediately after the closing
`</Select>`** and before the existing `{key === "classifying_var_2" && current &&
chart.classifying_var && (` swap-link block. Use the bordered `AlertCircleIcon`
block this file already uses for inline messages — **not** `toast.warning`, which
this file also offers: a toast disappears, and a notice about what the deck will
leave out has to stay visible for as long as the variable is chosen.

```tsx
      {tooManyGroups && (
        <div className="mt-2 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
          <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
          <span className="leading-snug">
            {chosen?.label ?? current} has {chosen?.n_values} groups and only{" "}
            {MAX_PANELS} fit on one slide. The three largest will be drawn; the
            slide footer names the rest.
          </span>
        </div>
      )}
```

- [ ] **Step 2: Typecheck and lint**

Run: `cd web && npm run build && npm run lint`
Expected: both clean. `AlertCircleIcon` is already imported in this file (line 3).

- [ ] **Step 3: Verify by hand**

Start the app, open a report, and check each of these:

1. Add a pie slide. The **Classifying variable** picker is present — it was absent before.
2. Choose a two- or three-group variable (gender). No warning; the preview shows one pie per group with a shared legend beneath.
3. Choose a four-group variable (age). The amber warning appears and **stays** while the variable is chosen; the preview shows three pies; the footer names the omitted group.
4. Switch the slide from a gender-split bar chart to a pie. The classifier survives the switch — it used to be silently cleared.
5. Switch a split pie back to a bar chart. It renders as an ordinary classified bar chart.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/wizard/StepConfigure.tsx
git commit -m "feat(web): say so before the deck drops a group"
```

---

## Done

Run the whole backend suite one last time:

```bash
uv run pytest tests/suite tests/rb -q -m "not judge and not integration"
```

Then use `superpowers:finishing-a-development-branch` to decide how `multi-pie-panels` gets integrated.

**Known limitation shipped deliberately:** the AI slide headline still describes the overall distribution, because `_findings_from_series` reads only the `"Total"` column. A split pie gets a true headline that is blind to the split. Making it split-aware is a separate change to the AI prompt and findings shape (spec, *Known limitations*).
