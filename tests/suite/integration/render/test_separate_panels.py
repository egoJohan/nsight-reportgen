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
