"""Integration: two classifiers rendered as SEPARATE panels, one per variable."""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.render.image.bars import _stack_panels, _measure_max_label_width_in
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


# Two deliberately pathological, unbroken 40-character tokens — never real
# survey text, chosen purely to force each character's full glyph width onto
# a single wrapped line (`_wrap_label`'s `force_break_token` caps any line at
# `_LABEL_WRAP_WIDTH`==30 chars, so this is close to the WIDEST a single
# label block can physically measure). See `_setup_wide_bar_labels`.
_PATHOLOGICAL_LABEL_1 = "M" * 40
_PATHOLOGICAL_LABEL_2 = "W" * 40


def _setup_wide_bar_labels():
    """Like `_setup`, but BOTH Sukupuoli's and Ikäryhmät's own value labels
    are pathologically wide unbroken tokens instead of "Nainen"/"Mies"/
    "Nuoret"/"Keski"/"Vanhat".

    For `test_stacked_separate_panels_grow_figure_height_with_rows`: the
    STACKED panel renderer measures each panel's OWN bar labels (the
    classifier's own group names — these), PER PANEL — panel 0's own label
    block only has to fit the figure's LEFT margin, and panel 1's only the
    GAP between panel 0 and 1 (see `_side_by_side_layout`). That per-panel
    costing turned out to be much more forgiving than a first-draft flat
    approximation assumed: realistic Finnish sentence-length labels (even a
    30-character single line, e.g. "Naiset ja muunsukupuoliset vastaajat")
    top out around 1.8-2.0in at fontsize 10.5 and do NOT force stacking,
    because only the panel that actually OWNS a wide label pays for it —
    a short second panel doesn't inflate the shared cost. Forcing `rows ==
    2` genuinely requires BOTH panels to carry a near-worst-case label (see
    the arithmetic in `_side_by_side_layout`'s docstring: with two 9in-floor
    panels, `_MIN_HGUTTER_PLOT_IN` is only undercut once both panels' widest
    label exceeds ~2.1in — unreachable by realistic wrapped Finnish text
    alone). Hence the two synthetic pathological tokens here, one for each
    variable, rather than natural wording — this test now exists to prove
    the ROWS==2 height-scaling *mechanism* still works, not to model a
    plausible customer shape (that's `test_customer_scale_stays_side_by_side`
    and `test_labels_that_genuinely_cannot_fit_still_stack`'s job).
    `age` keeps a normal-length "Keski" alongside its own pathological entry
    so the group SIZES driving `max_bars` (3 for Sukupuoli+Total, 4 for
    Ikäryhmät+Total) stay identical to `_setup`'s — only label WIDTH changes.
    (re-expressed 2026-08-06 for the measured rule; widened again 2026-08-06
    once panel margins were split from a flat approximation to genuine
    per-panel costing — see the coordinator finding in the task report)"""
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, _PATHOLOGICAL_LABEL_1),
                                 ValueLabel(2.0, _PATHOLOGICAL_LABEL_2)),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, _PATHOLOGICAL_LABEL_1), ValueLabel(2.0, "Keski"),
                                 ValueLabel(3.0, _PATHOLOGICAL_LABEL_2)),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex, "age": age}, questions=[])
    question = Question(qid="q", kind="single", variables=("q",), text="Suhtautuminen")
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0, 5.0] * 24,
        "sex": ([1.0] * 60) + ([2.0] * 60),
        "age": [1.0, 2.0, 3.0] * 40,
    })
    return model, question, df


def _setup_realistic_classifier_labels():
    """Mirrors the actual customer render that surfaced the overlap bug:
    `var4`-style gender labels ("Naiseksi"/"Mieheksi", 8 chars) and
    `var5`-style age-band labels ("18-24-vuotias" etc., ~13 chars, SIX
    groups) — genuinely realistic survey text, not pathological, and (per
    `_setup_wide_bar_labels`'s finding) comfortably narrow enough that
    `_stack_panels`/`_side_by_side_layout` choose SIDE BY SIDE. That is
    exactly the shape that exposed the bug: a fixed `subplots_adjust(left=,
    wspace=)` doesn't care whether the decision was "fits" — it overflows
    regardless of what the fit test concluded, unless the space allocation is
    ALSO driven by the same measurement. Six age groups (not three) also
    matches the real render's taller per-panel bar count."""
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Naiseksi"), ValueLabel(2.0, "Mieheksi")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikä", measurement="categorical",
                   value_labels=(
                       ValueLabel(1.0, "18–24-vuotias"),
                       ValueLabel(2.0, "25–34-vuotias"),
                       ValueLabel(3.0, "35–44-vuotias"),
                       ValueLabel(4.0, "45–54-vuotias"),
                       ValueLabel(5.0, "55–64-vuotias"),
                       ValueLabel(6.0, "65–69-vuotias"),
                   ),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex, "age": age}, questions=[])
    question = Question(qid="q", kind="single", variables=("q",), text="Suhtautuminen")
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0, 5.0] * 60,
        "sex": ([1.0] * 150) + ([2.0] * 150),
        "age": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0] * 50,
    })
    return model, question, df


def _setup_stacked():
    """Like `_setup`, but with 7 worded answer categories (a realistic 7-point
    Likert scale) instead of 5 bare digits.

    Under the runtime-measured fit test (`_stack_panels`), bare digit labels
    ("1".."7") are trivially narrow at any rotation and never trip stacking —
    a category COUNT alone no longer forces it. Real Likert wording, rotated
    30° on a vertical panel's shared x-axis, DOES: each of the 7 rotated
    labels only gets ~0.56in of the panel's width, and the widest of them
    measures wider than that — see test_vertical_stacked_panels_grow_figure_height,
    which is this fixture's actual assertion of the `rows == 2` (panels stacked
    one above the other) path. (The HORIZONTAL orientation of this same fixture
    stays side by side — these particular labels fit a left-gutter comfortably;
    only the vertical, rotated, per-category-width test is tight enough to trip
    on them.) (spec 2026-08-04; re-expressed 2026-08-06 for the measured rule)"""
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=(
                     ValueLabel(1.0, "1 Täysin eri mieltä"),
                     ValueLabel(2.0, "2 Osittain eri mieltä"),
                     ValueLabel(3.0, "3 Ei samaa eikä eri mieltä"),
                     ValueLabel(4.0, "4 Osittain samaa mieltä"),
                     ValueLabel(5.0, "5 Täysin samaa mieltä"),
                     ValueLabel(6.0, "6 En osaa sanoa"),
                     ValueLabel(7.0, "7 Ei koske minua"),
                 ),
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
    survives — while the labels still ask for stacked panels (`rows == 2`) for
    at least the STACKED chart types.

    Deliberately breaks the intersection every other separate-mode fixture in
    this file shares (two healthy variables, short labels): the sex value
    labels ("Naiset ja muunsukupuoliset" / "Miehet ja muut vastaajat") measure
    too wide for a side-by-side horizontal gutter, which trips `_stack_panels`
    for the STACKED renderer (it measures the BAR labels — these — regardless
    of chart orientation). That gives `new_figure_grid(n=1, rows=2)` for
    `stacked_horizontal_bar`/`stacked_vertical_bar`. The bare digit `q`
    categories ("1".."7") measure narrow at any rotation, so the CLUSTERED
    renderers (`horizontal_bar`/`vertical_bar`, which measure the ANSWER
    categories, not the sex labels) stay at `rows == 1` under the measured
    rule — this test still covers `n=1` for those two, just not `rows=2`.
    Either way this must not crash. (2026-08-04 final review, C1; re-expressed
    2026-08-06 for the measured rule)"""
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


def test_measure_max_label_width_in_grows_with_label_length():
    """Direct unit test of the measurement helper: a short label measures
    narrower than a long one, and the result is a plausible number of INCHES —
    not the hundreds-of-pixels `get_window_extent` returns raw, and not a bare
    character count either."""
    short_in = _measure_max_label_width_in(["Kyllä"], 9.0)
    long_in = _measure_max_label_width_in(
        ["Erittäin paljon samaa mieltä väitteestä"], 9.0)
    assert short_in < long_in
    assert 0.05 < short_in < 1.0, f"implausible for a 5-char word: {short_in}in"
    assert 1.0 < long_in < 6.0, f"implausible for a 40-char phrase: {long_in}in"


def test_stack_panels_rule():
    """Short labels fit side by side in either orientation; labels that
    measurably cannot fit stack.

    Re-expressed against the runtime-measured fit test: the old rule was a
    bare character count (`len(cats) > 6 or any(len(c) > 14 ...)`), so this
    test used to assert on category count/length directly. The measured rule
    takes `fig_w_in`/`fontsize`/`vertical` as real inputs instead, so the
    cases below are chosen to still land on the same two outcomes (fits /
    doesn't fit) but via genuine measurement — 7 short digit categories no
    longer trip stacking (proving the count alone is no longer sufficient),
    while a long compound word / many realistically-worded categories still
    do (see test_customer_scale_stays_side_by_side and
    test_labels_that_genuinely_cannot_fit_still_stack for the two boundary
    shapes that motivated the rewrite). Not a bare "count no longer matters"
    claim either — the digit case above is the count/length trigger falling
    silent when it shouldn't have fired in the first place, not proof count
    never matters (the guard test still trips it, via width)."""
    # Three short digit categories: comfortably fits either orientation.
    assert _stack_panels(["1", "2", "3"], fig_w_in=9.0, fontsize=9.0,
                          vertical=False) is False
    assert _stack_panels(["1", "2", "3"], fig_w_in=9.0, fontsize=8.5,
                          vertical=True) is False
    # 7 short digit categories: the OLD rule's ">6 categories" branch tripped
    # on this alone; the measured rule does not — count alone isn't enough
    # when every label is a single narrow character.
    seven_short = [str(i) for i in range(1, 8)]
    assert _stack_panels(seven_short, fig_w_in=9.0, fontsize=9.0,
                          vertical=False) is False
    assert _stack_panels(seven_short, fig_w_in=9.0, fontsize=8.5,
                          vertical=True) is False


def test_customer_scale_stays_side_by_side():
    """Regression for the reported complaint: a 1-5 rating scale whose end
    labels are Finnish sentences ('1 En lainkaan positiivisesti' / '5 Erittäin
    positiivisesti', 25-27 characters) must choose SIDE BY SIDE at the normal
    (9in floor) slot width.

    These are the ANSWER categories, so this is `_render_variable_panels`'s
    (the CLUSTERED renderer's) fit test — its `horizontal_bar` gutter draws
    category labels at fontsize=9.0. (The stacked-type panel renderer's
    fontsize=10.5 call measures the CLASSIFIER's own group labels — e.g.
    gender/age names — never this question's answer scale, so it isn't the
    right comparison for this specific shape; see
    test_stacked_separate_panels_grow_figure_height_with_rows for that call
    site's own genuinely-too-wide case.)

    This must FAIL against the old character rule and PASS against the
    measured one: both end labels are well over the old `> 14` character
    threshold, so the old rule stacked on this shape even though the labels,
    measured, leave comfortable room in a half-width panel's gutter."""
    cats = ["1 En lainkaan positiivisesti", "2", "3", "4",
            "5 Erittäin positiivisesti"]
    assert any(len(c) > 14 for c in cats), (
        "premise: the OLD character rule DID trip on this shape"
    )
    assert _stack_panels(cats, fig_w_in=9.0, fontsize=9.0, vertical=False) is False, (
        "horizontal_bar's clustered gutter (fontsize 9.0) must stay side by side"
    )


def test_labels_that_genuinely_cannot_fit_still_stack():
    """Guard against over-correcting to 'always side by side': labels that
    demonstrably cannot fit a half-width panel must still choose STACKED.

    Vertical: a dozen ordinarily-worded categories (not pathologically long,
    just numerous) crowd out the per-category width a rotated panel can
    spare — realistic text, no exaggeration needed.

    Horizontal (`shared_labels=False` — the STACKED panel renderer's real
    per-panel geometry, where EVERY panel draws its OWN labels, unlike the
    shared-axis clustered renderer default): two pathologically wide,
    unbroken 40-character tokens, one per (synthetic) panel. This had to get
    more extreme than a first draft of this test used (a single long, real
    Finnish compound word) once the layout moved from a flat per-panel
    approximation to genuine per-panel costing — seeing `_side_by_side_layout`'s
    docstring, forcing `rows == 2` at the 9in figure-width floor requires
    BOTH panels' own widest label to individually exceed ~2.1in, and
    `_wrap_label`'s 30-character line cap keeps even long real Finnish
    sentences under ~2.0in. So a real single long word is NOT actually a
    case that fails to fit any more (see the shared-axis assertion below,
    which is the shape `_render_variable_panels`'s clustered renderer
    actually uses) — only a synthetic worst-case token pair demonstrates the
    per-panel branch can still stack at all."""
    many_cats = [f"Kategoria {i}" for i in range(1, 13)]
    assert _stack_panels(many_cats, fig_w_in=9.0, fontsize=8.5,
                          vertical=True) is True

    wide1, wide2 = "M" * 40, "W" * 40
    assert _stack_panels([wide1, wide2], fig_w_in=9.0, fontsize=10.5,
                          vertical=False, shared_labels=False) is True

    # By contrast: a single long real Finnish compound word, measured against
    # the SHARED-axis geometry `_render_variable_panels`'s horizontal branch
    # actually uses (only one panel ever draws a label at all), does NOT
    # stack — proving this isn't a case that quietly "always stacks now
    # anyway" but a genuine, geometry-dependent difference.
    long_word = "Yhteiskuntavastuullisuusasenneindeksimittaristo"
    assert _stack_panels(["a", long_word], fig_w_in=9.0, fontsize=9.0,
                          vertical=False, shared_labels=True) is False


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
    """`_setup_stacked`'s 7 worded Likert categories trip the `rows == 2` path
    for the VERTICAL orientation (see test_vertical_stacked_panels_grow_figure_height
    for the direct assertion); the HORIZONTAL orientation of the same fixture
    stays side by side under the measured fit test. Either way this must
    render without crashing — that's all this test checks."""
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
    `rows` — well under the 8.5in floor asserted below.

    Depends on `_setup_stacked`'s 7 REAL Likert-worded categories genuinely
    tripping `rows == 2` under the runtime-measured fit test (each rotated
    label only gets ~0.56in of a half-width panel's x-axis, and the widest of
    these measures wider than that) — bare digit categories no longer would,
    see `_setup_stacked`'s docstring. (re-expressed 2026-08-06)"""
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

    Uses `_setup_wide_bar_labels` (see its docstring for why BOTH panels now
    need a pathologically wide label, not just one, to force `rows == 2`
    under the per-panel-costed layout). The engine still appends a per-group
    reference "Total" bar for stacked chart types (see `_stacked_layout`'s
    docstring) regardless of label text, so Sukupuoli's panel still has 3
    bars (2 groups + Total) and Ikäryhmät's still has 4 (3 groups + Total) —
    the SAME group sizes `_setup` produces, so the max_bars(4)-derived height
    formula below is unaffected by the fixture's label content. That makes
    this the stacked-rows path the earlier clustered-panel regression warns
    about, and it needs its OWN fixture-independent, machine-verifiable
    assertion (font-metric-dependent overlap checks are not) — the figure
    height computed from the fixed constants `_render_stacked_variable_panels`
    documents: max_bars(4) * `_HBAR_ROW_IN`(0.52) + 2.0, all * rows(2) = 8.16in.
    """
    import reportbuilder.render.image.bars as bars_mod

    model, question, df = _setup_wide_bar_labels()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec("stacked_horizontal_bar"), df, model)
    _prs, slide, slot, ctx = make_ctx("stacked_horizontal_bar", series, **spec_kw)

    # Independently confirm the fixture really does trip rows == 2 and max_bars == 4
    # before trusting the height computed from them (a wrong premise would make the
    # height assertion pass for the wrong reason). Mirrors the PER-PANEL costing
    # `_render_stacked_variable_panels` itself now uses (see
    # `_side_by_side_layout`) rather than the single-flattened-list `_stack_panels`
    # convenience wrapper, which no longer represents this call site's real
    # (per-panel, not shared) label geometry.
    groups = bars_mod._primary_groups(series)
    assert [len(segs) for _p, segs in groups] == [3, 4]
    bars_all, _stack, _data = bars_mod._stacked_layout(series)
    drawable = bars_mod._drawable_panels(groups, bars_all)
    panel_label_w_in = [
        bars_mod._measure_max_label_width_in(
            [bars_mod._wrap_label(bars_mod._secondary_tick(b)) for b in bars], 10.5)
        for _p, bars in drawable
    ]
    fig_w_in = max(9.0, slot.width / bars_mod._EMU_PER_IN)
    _left, _right, _wspace, plot_w_in = bars_mod._side_by_side_layout(
        fig_w_in, len(drawable), panel_label_w_in[0], panel_label_w_in[1])
    assert plot_w_in < bars_mod._MIN_HGUTTER_PLOT_IN, (
        f"premise: side-by-side plot width {plot_w_in}in should be below the "
        f"{bars_mod._MIN_HGUTTER_PLOT_IN}in floor for this fixture"
    )

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


# ---------------------------------------------------------------------------
# Overlap regression: a fit DECISION alone proves nothing about the actual
# picture — the arrangement can be measured as "fits side by side" and still
# render with a label from one panel drawn on top of ANOTHER panel's bars if
# the space allocation (`subplots_adjust`) isn't driven by the same
# measurement. Caught by inspection of a real render (a fixed `left`/`wspace`
# regardless of label width): `_render_stacked_variable_panels` used to end
# with `subplots_adjust(..., wspace=0.18, left=0.2)` no matter what the fit
# test had just decided. Checked here with matplotlib's OWN rendered
# geometry (`get_window_extent`) against the actual figure that gets saved —
# not source-level assertions about the formula, which cannot catch a
# call site that computed the right numbers but forgot to use them.
# ---------------------------------------------------------------------------

def _assert_no_tick_label_overlaps_other_axes(fig) -> None:
    """No axis's own tick label may overlap a DIFFERENT axis's plot area.

    Matplotlib draws tick labels OUTSIDE their own axes' bounding box, so a
    label legitimately extends past its own axes' edge into the figure
    margin or inter-panel gap — that's expected and fine. What must never
    happen is that extension reaching far enough to land inside a *different*
    axes' own bounding box, which visually reads as text drawn over that
    other panel's bars. `get_window_extent` gives both the label's and the
    axes' TRUE rendered pixel geometry (post-layout, post-rotation), so this
    checks the actual picture, not the subplots_adjust numbers that produced
    it.
    """
    renderer = fig.canvas.get_renderer()
    axes = list(fig.axes)
    axes_bboxes = [(ax, ax.get_window_extent(renderer)) for ax in axes]
    for ax in axes:
        labels = list(ax.get_yticklabels()) + list(ax.get_xticklabels())
        for label in labels:
            if not label.get_visible() or not label.get_text():
                continue
            lbox = label.get_window_extent(renderer)
            for other_ax, obox in axes_bboxes:
                if other_ax is ax:
                    continue
                assert not lbox.overlaps(obox), (
                    f"tick label {label.get_text()!r} (belonging to one panel) "
                    "overlaps a DIFFERENT panel's plot area"
                )


@pytest.mark.parametrize("chart_type", ["stacked_horizontal_bar", "stacked_vertical_bar"])
def test_stacked_panel_labels_never_overlap_a_neighbouring_panel(chart_type, monkeypatch):
    """Direct regression for the reviewer-caught bug: with realistic (not
    pathological) classifier labels that measure as fitting SIDE BY SIDE,
    the right panel's own row labels must not be drawn on top of the left
    panel's bars — and vice versa. Pre-fix, `_render_stacked_variable_panels`
    ended with a FIXED `subplots_adjust(left=0.2, wspace=0.18)` regardless of
    what `_stack_panels` had just measured, so a label wider than that fixed
    budget silently overflowed into the neighbouring axes; this is exactly
    what happened on the customer's real slide."""
    import reportbuilder.render.image.bars as bars_mod

    model, question, df = _setup_realistic_classifier_labels()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec(chart_type), df, model)
    _prs, slide, slot, ctx = make_ctx(chart_type, series, **spec_kw)

    captured = {}
    real_render_png = bars_mod.render_png

    def _spy(fig):
        captured["fig"] = fig
        _assert_no_tick_label_overlaps_other_axes(fig)
        return real_render_png(fig)

    monkeypatch.setattr(bars_mod, "render_png", _spy)
    IMAGE_BUILDERS[chart_type](ctx)
    assert "fig" in captured, "render_png was never called"


@pytest.mark.parametrize("chart_type", ["horizontal_bar", "vertical_bar"])
def test_clustered_panel_labels_never_overlap_a_neighbouring_panel(chart_type, monkeypatch):
    """Same check for `_render_variable_panels` (the clustered renderer):
    even though its shared y-axis (sharey=True) meant it was never observed
    to exhibit the reviewer-caught bug in practice (only the leftmost panel
    of a row ever draws a label at all), it went through the same
    `subplots_adjust` rewrite in this fix, so it gets the same direct,
    pixel-level regression coverage rather than relying on that structural
    argument alone."""
    import reportbuilder.render.image.bars as bars_mod

    model, question, df = _setup_realistic_classifier_labels()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec(chart_type), df, model)
    _prs, slide, slot, ctx = make_ctx(chart_type, series, **spec_kw)

    captured = {}
    real_render_png = bars_mod.render_png

    def _spy(fig):
        captured["fig"] = fig
        _assert_no_tick_label_overlaps_other_axes(fig)
        return real_render_png(fig)

    monkeypatch.setattr(bars_mod, "render_png", _spy)
    IMAGE_BUILDERS[chart_type](ctx)
    assert "fig" in captured, "render_png was never called"
