"""Integration: two classifiers rendered as SEPARATE panels, one per variable."""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.render.image.bars import _stack_panels
from reportbuilder.stats.engine import compute

from suite._helpers import assert_single_picture, make_ctx


def _setup():
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Keski"),
                                 ValueLabel(3.0, "Vanhat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex, "age": age}, questions=[])
    question = Question(qid="q", kind="single", variables=("q",), text="Suhtautuminen")
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0, 5.0] * 24,
        "sex": ([1.0] * 60) + ([2.0] * 60),
        "age": [1.0, 2.0, 3.0] * 40,
    })
    return model, question, df


def _setup_stacked():
    """Like `_setup`, but with 7 answer categories — trips `_stack_panels`
    (len(cats) > 6), which `_setup`'s 5 digit-label categories never do. Covers
    the `rows == 2` (panels stacked one above the other) path for BOTH
    orientations; the un-stacked fixture above never exercises it."""
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 8)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Keski"),
                                 ValueLabel(3.0, "Vanhat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex, "age": age}, questions=[])
    question = Question(qid="q", kind="single", variables=("q",), text="Suhtautuminen")
    df = pd.DataFrame({
        "q": [float(i) for i in range(1, 8)] * 18,   # 126 rows, 7 categories
        "sex": ([1.0] * 63) + ([2.0] * 63),
        "age": [1.0, 2.0, 3.0] * 42,
    })
    return model, question, df


def _setup_stale_second():
    """The degradation the design promises: the SECOND classifying variable no
    longer resolves (a stale name / an all-missing column), so only ONE panel
    survives — while the labels still ask for stacked panels (`rows == 2`).

    Deliberately breaks the intersection every other separate-mode fixture in
    this file shares (two healthy variables, short labels): 7 answer categories
    trip `_stack_panels` for the CLUSTERED renderers (which measure the answer
    categories) and the >14-char group labels trip it for the STACKED one
    (which measures the bar labels), so both renderers reach
    `new_figure_grid(n=1, rows=2)`. (2026-08-04 final review, C1)"""
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 8)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Naiset ja muunsukupuoliset"),
                                 ValueLabel(2.0, "Miehet ja muut vastaajat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex}, questions=[])
    question = Question(qid="q", kind="single", variables=("q",), text="Suhtautuminen")
    df = pd.DataFrame({
        "q": [float(i) for i in range(1, 8)] * 18,     # 126 rows, 7 categories
        "sex": ([1.0] * 63) + ([2.0] * 63),
    })
    return model, question, df


@pytest.mark.parametrize("chart_type", ["horizontal_bar", "vertical_bar",
                                        "stacked_horizontal_bar",
                                        "stacked_vertical_bar"])
def test_a_stale_second_variable_still_renders_its_surviving_panel(chart_type):
    """One panel + a two-row layout must not crash.

    Pre-fix this raised `AttributeError: 'numpy.ndarray' object has no attribute
    'set_facecolor'` inside `new_figure_grid`: with `rows=2`, `fig.subplots(2, 1)`
    returns an ndarray even for n == 1, and the old `[axes] if n <= 1` wrapped
    that array instead of flattening it. (2026-08-04 final review, C1)"""
    model, question, df = _setup_stale_second()
    spec_kw = dict(classifying_var="sex", classifying_var_2="ei_ole_enaa",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec(chart_type, classifying_var_2="ei_ole_enaa"),
                     df, model)
    assert len(set(series.segment_primary.values())) == 1, "only one panel survives"
    _prs, slide, slot, ctx = make_ctx(chart_type, series, **spec_kw)
    IMAGE_BUILDERS[chart_type](ctx)
    assert_single_picture(slide, slot)


def _setup_tiny_second():
    """The second variable's groups are ALL under MIN_SEGMENT_BASE (10): only 9
    respondents carry an age at all, three per band. `show_total="off"` denies the
    panel the per-variable Total bar that would otherwise rescue it, so the whole
    Ikäryhmät panel has nothing drawable.

    The other separate-mode fixtures give both variables healthy bases, which is
    what hid the empty-panel crash and the phantom panel.
    (2026-08-04 final review, I3/I4)"""
    model, question, _ = _setup()
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0, 5.0] * 24,
        "sex": ([1.0] * 60) + ([2.0] * 60),
        "age": [1.0, 2.0, 3.0] * 3 + [float("nan")] * 111,
    })
    return model, question, df


@pytest.mark.parametrize("chart_type", ["horizontal_bar", "vertical_bar",
                                        "stacked_horizontal_bar",
                                        "stacked_vertical_bar"])
def test_an_all_tiny_panel_is_omitted_not_drawn_empty(chart_type, monkeypatch):
    """A variable whose every group is below MIN_SEGMENT_BASE contributes no
    panel at all.

    Pre-fix, the CLUSTERED renderers took their panels from `_primary_groups`
    (every segment) but their values from `series_values` (base-filtered), so the
    dead variable still got a titled, legended panel of 0-height bars reading
    "0 %" — the design says it vanishes. The STACKED renderer did worse: an empty
    bar list reached `ax.set_ylim(min(y) - 0.7, …)` and raised
    `ValueError: min() iterable argument is empty`.
    (2026-08-04 final review, I3/I4)"""
    import reportbuilder.render.image.bars as bars_mod

    model, question, df = _setup_tiny_second()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   show_total="off", options={"xtab_layout": "separate"})
    series = compute(question, _spec(chart_type, show_total="off"), df, model)
    # Confirm the premise: the engine DOES emit the age segments (so the phantom
    # panel really came from the renderer), and their bases really are tiny.
    assert [s for s in series.segments if s.startswith("Ikäryhmät")]
    assert all(series.base_n[s] < 10 for s in series.segments
               if s.startswith("Ikäryhmät"))

    _prs, slide, slot, ctx = make_ctx(chart_type, series, **spec_kw)
    captured = {}
    real_render_png = bars_mod.render_png

    def _spy(fig):
        captured["titles"] = [ax.get_title() for ax in fig.axes]
        return real_render_png(fig)

    monkeypatch.setattr(bars_mod, "render_png", _spy)
    IMAGE_BUILDERS[chart_type](ctx)

    assert captured["titles"] == ["Sukupuoli"], "the empty panel must not be drawn"
    assert_single_picture(slide, slot)


def _spec(chart_type, **kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type=chart_type, statistic="pct",
                classifying_var="sex", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="slot1", elements=ElementToggles(),
                options={"xtab_layout": "separate"})
    base.update(kw)
    return ChartSpec(**base)


def test_stack_panels_rule():
    assert _stack_panels(["a", "b", "c"]) is False
    assert _stack_panels([f"c{i}" for i in range(7)]) is True, "more than 6 categories"
    assert _stack_panels(["a" * 15, "b"]) is True, "a label longer than 14 chars"


@pytest.mark.parametrize("chart_type", ["horizontal_bar", "vertical_bar"])
def test_separate_panels_render_one_picture(chart_type):
    model, question, df = _setup()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec(chart_type), df, model)
    _prs, slide, slot, ctx = make_ctx(chart_type, series, **spec_kw)
    IMAGE_BUILDERS[chart_type](ctx)
    assert_single_picture(slide, slot)


def test_one_panel_per_variable_not_per_group():
    model, question, df = _setup()
    series = compute(question, _spec("horizontal_bar"), df, model)
    from reportbuilder.render.image.bars import _primary_groups
    groups = _primary_groups(series)
    assert [p for p, _segs in groups] == ["Sukupuoli", "Ikäryhmät"]
    assert [len(segs) for _p, segs in groups] == [2, 3], "each panel keeps its own groups"


@pytest.mark.parametrize("chart_type", ["horizontal_bar", "vertical_bar"])
def test_separate_panels_render_two_axes_titled_by_variable(chart_type, monkeypatch):
    """assert_single_picture alone would ALSO pass on a crossed/grouped render
    (still one picture) — this test can only pass when the figure that gets
    rendered really has two axes, one per classifying VARIABLE, not one shared
    crossed axes. Spies on render_png (called once, right before the figure is
    handed to place_picture and cleared) to inspect the figure's axes/titles
    before they're discarded."""
    import reportbuilder.render.image.bars as bars_mod

    model, question, df = _setup()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec(chart_type), df, model)
    _prs, slide, slot, ctx = make_ctx(chart_type, series, **spec_kw)

    captured = {}
    real_render_png = bars_mod.render_png

    def _spy(fig):
        captured["n_axes"] = len(fig.axes)
        captured["titles"] = [ax.get_title() for ax in fig.axes]
        return real_render_png(fig)

    monkeypatch.setattr(bars_mod, "render_png", _spy)
    IMAGE_BUILDERS[chart_type](ctx)

    assert captured["n_axes"] == 2, "one panel per classifying variable, not per group"
    assert captured["titles"] == ["Sukupuoli", "Ikäryhmät"]


@pytest.mark.parametrize("chart_type", ["horizontal_bar", "vertical_bar"])
def test_stacked_panels_render_one_picture(chart_type):
    """Covers the `_stack_panels` rows==2 path (7 categories) for BOTH
    orientations — the digit-label fixture used elsewhere in this file never
    trips it, so this is the only coverage of that branch at all."""
    model, question, df = _setup_stacked()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec(chart_type), df, model)
    _prs, slide, slot, ctx = make_ctx(chart_type, series, **spec_kw)
    IMAGE_BUILDERS[chart_type](ctx)
    assert_single_picture(slide, slot)


def test_vertical_stacked_panels_grow_figure_height(monkeypatch):
    """Regression for a Critical review finding: `_render_variable_panels`'s
    vertical branch passed `tall_in=None` regardless of `rows`, so a STACKED
    (rows == 2) vertical figure got the SAME height as an un-stacked one — the
    second row's rotated x-tick labels and its own legend had nowhere to go,
    so they overlapped the first row's legend/title. `assert_single_picture`
    and crash-freedom both stay green through that bug (the reviewer
    reproduced it): the picture count is still 1, and matplotlib silently lets
    artists overlap rather than raising. The only way to detect the collapsed
    layout without rasterising and inspecting pixels is to check that the
    figure actually grew taller when its panels stacked — which this asserts
    directly by spying on render_png (called once, right before place_picture
    consumes and clears the figure).

    Pre-fix this failed: `tall_in` stayed None, so `new_figure_grid` fell back
    to `max(4.5, slot.height/EMU_PER_IN)` = max(4.5, 5.0) = 5.0in regardless of
    `rows` — well under the 8.5in floor asserted below."""
    import reportbuilder.render.image.bars as bars_mod

    model, question, df = _setup_stacked()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec("vertical_bar"), df, model)
    _prs, slide, slot, ctx = make_ctx("vertical_bar", series, **spec_kw)

    captured = {}
    real_render_png = bars_mod.render_png

    def _spy(fig):
        captured["h_in"] = fig.get_size_inches()[1]
        return real_render_png(fig)

    monkeypatch.setattr(bars_mod, "render_png", _spy)
    IMAGE_BUILDERS["vertical_bar"](ctx)

    # Fixed slot height in make_slot() is 5in; a stacked (rows == 2) figure
    # must clear that by a wide margin (the fix uses 4.5in/row * 2 = 9.0in) to
    # prove the height actually scaled with `rows` rather than falling back to
    # the slot/default floor.
    assert captured["h_in"] >= 8.5, (
        f"stacked vertical panels rendered at {captured['h_in']}in tall — "
        "did not grow to fit a second row of x-tick labels + legend"
    )


@pytest.mark.parametrize("chart_type", ["stacked_horizontal_bar", "stacked_vertical_bar"])
def test_stacked_separate_panels_render_one_picture(chart_type):
    model, question, df = _setup()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec(chart_type), df, model)
    _prs, slide, slot, ctx = make_ctx(chart_type, series, **spec_kw)
    IMAGE_BUILDERS[chart_type](ctx)
    assert_single_picture(slide, slot)


def test_stacked_separate_panels_keep_their_row_summary_per_panel():
    model, question, df = _setup()
    spec = _spec("stacked_horizontal_bar", row_summary_fn="top2_sum")
    series = compute(question, spec, df, model)
    from reportbuilder.render.image.bars import _primary_groups, _row_summary_by_bar
    for _p, segs in _primary_groups(series):
        vals = _row_summary_by_bar(series, list(segs))
        assert len(vals) == len(segs)
        assert all(v is not None for v in vals), "every bar in the panel has its value"


@pytest.mark.parametrize("chart_type", ["stacked_horizontal_bar", "stacked_vertical_bar"])
def test_stacked_separate_panels_render_two_axes_titled_by_variable(chart_type, monkeypatch):
    """`assert_single_picture` alone would ALSO pass on a flat, un-panelled stacked
    chart (still one picture) — this is the only test that can fail if the SEPARATE
    dispatch is missing or wired to the wrong function. Spies on render_png (called
    once, right before the figure is handed to place_picture and cleared) to inspect
    the figure's axes/titles before they're discarded."""
    import reportbuilder.render.image.bars as bars_mod

    model, question, df = _setup()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec(chart_type), df, model)
    _prs, slide, slot, ctx = make_ctx(chart_type, series, **spec_kw)

    captured = {}
    real_render_png = bars_mod.render_png

    def _spy(fig):
        captured["n_axes"] = len(fig.axes)
        captured["titles"] = [ax.get_title() for ax in fig.axes]
        # Bar labels differ per panel (2 for Sukupuoli, 3 for Ikäryhmät) — this can
        # only be true if the axes are NOT sharey-linked (see `new_figure_grid`'s
        # sharey note): with sharey=True the second axes' set_ylim/set_yticks call
        # silently overwrites the first's too, so both would report 3 bars.
        captured["n_bars"] = [len(ax.get_yticks()) for ax in fig.axes]
        return real_render_png(fig)

    monkeypatch.setattr(bars_mod, "render_png", _spy)
    IMAGE_BUILDERS[chart_type](ctx)

    assert captured["n_axes"] == 2, "one panel per classifying variable, not per group"
    assert captured["titles"] == ["Sukupuoli", "Ikäryhmät"]
    # Sukupuoli: Nainen, Mies, + the reference "Total" bar the stacked engine adds
    # per group → 3. Ikäryhmät: Nuoret, Keski, Vanhat, + Total → 4.
    assert captured["n_bars"] == [3, 4], (
        "each panel must keep its OWN bar count — a shared/linked y-axis would "
        "make both panels report the same (last-drawn) count"
    )


def test_stacked_separate_panels_grow_figure_height_with_rows(monkeypatch):
    """Regression-shaped test for the stacked panel renderer's own height budget.

    Unlike the clustered `_setup()` fixture (5 digit answer categories, which never
    trips `_stack_panels`), the STACKED types trip `_stack_panels` on `_setup()`
    already: the engine appends a per-group reference "Total" bar for stacked
    chart types (see `_stacked_layout`'s docstring), so Sukupuoli's panel has 3
    bars (Nainen, Mies, Total) and Ikäryhmät's has 4 (Nuoret, Keski, Vanhat,
    Total) — 7 bars flattened across panels, > 6, so `rows == 2`. That makes this
    the stacked-rows path the earlier clustered-panel regression warns about, and
    it needs its OWN fixture-independent, machine-verifiable assertion (font-metric
    -dependent overlap checks are not) — the figure height computed from the fixed
    constants `_render_stacked_variable_panels` documents: max_bars(4) *
    `_HBAR_ROW_IN`(0.52) + 2.0, all * rows(2) = 8.16in.
    """
    import reportbuilder.render.image.bars as bars_mod

    model, question, df = _setup()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec("stacked_horizontal_bar"), df, model)
    _prs, slide, slot, ctx = make_ctx("stacked_horizontal_bar", series, **spec_kw)

    # Independently confirm the fixture really does trip rows == 2 and max_bars == 4
    # before trusting the height computed from them (a wrong premise would make the
    # height assertion pass for the wrong reason).
    groups = bars_mod._primary_groups(series)
    assert [len(segs) for _p, segs in groups] == [3, 4]
    flat = [bars_mod._secondary_tick(s) for _p, segs in groups for s in segs]
    assert bars_mod._stack_panels(flat) is True

    captured = {}
    real_render_png = bars_mod.render_png

    def _spy(fig):
        captured["h_in"] = fig.get_size_inches()[1]
        return real_render_png(fig)

    monkeypatch.setattr(bars_mod, "render_png", _spy)
    IMAGE_BUILDERS["stacked_horizontal_bar"](ctx)

    expected = (4 * bars_mod._HBAR_ROW_IN + 2.0) * 2
    assert captured["h_in"] == pytest.approx(expected), (
        f"expected {expected}in from the documented max_bars*_HBAR_ROW_IN+2.0 * "
        f"rows budget, got {captured['h_in']}in"
    )
