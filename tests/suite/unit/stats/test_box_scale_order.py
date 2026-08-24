"""Top box means the top of the SCALE — not the top of the SAV file.

Both defects here printed a confident, precisely-formatted, wrong number on a
client slide, which is the worst failure this codebase has: nothing looks broken.

1. A word-labelled scale ("Erittäin tyytymätön" … "Erittäin tyytyväinen") has no
   leading digit to parse, so the ordering fell back to the order the labels
   happen to sit in the SAV. Half the survey tools export those descending, and
   on those files "top 2" reported the two most NEGATIVE levels. Reproduced:
   50 % at "Erittäin tyytymätön" was reported as top-2 = 70 %.

2. "En osaa sanoa" is a real answer, not a scale point. It was sorted to the end
   of the scale — past 5 — and so was counted INTO the top box, and given the
   sentinel value 1000 in the mean.
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _spec(**kw):
    base = dict(question_ref="q", chart_type="stacked_horizontal_bar", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def _run(var, codes, **kw):
    model = QuestionModel(variables={"q": var}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text=var.label)
    df = pd.DataFrame({"q": codes})
    return engine.compute(q, _spec(**kw), df, model)


# ── 1. A word-labelled scale the file stores high→low ──────────────────────
WORDS = ["Erittäin tyytymätön", "Tyytymätön", "Ei kumpaakaan",
         "Tyytyväinen", "Erittäin tyytyväinen"]


def _descending_word_scale():
    """As a real export writes it: the most positive label FIRST."""
    return Variable(
        name="q", label="Kuinka tyytyväinen olet?", measurement="categorical",
        value_labels=tuple(ValueLabel(float(5 - i), lbl)
                           for i, lbl in enumerate(reversed(WORDS))),
        missing_values=frozenset())


# 50 % dissatisfied, 20 % satisfied — an unambiguous verdict either way round.
_LOPSIDED = [1.0] * 50 + [2.0] * 20 + [3.0] * 10 + [4.0] * 10 + [5.0] * 10


def test_top_box_on_a_word_scale_counts_the_satisfied_ones():
    r = _run(_descending_word_scale(), _LOPSIDED, row_summary_fn="top2_sum")
    assert r.row_summaries == (20.0,)


def test_bottom_box_on_a_word_scale_counts_the_dissatisfied_ones():
    r = _run(_descending_word_scale(), _LOPSIDED, row_summary_fn="bottom2_sum")
    assert r.row_summaries == (70.0,)


def test_the_mean_of_a_word_scale_uses_the_scale_points():
    r = _run(_descending_word_scale(), _LOPSIDED, row_summary_fn="mean")
    # 1×.5 + 2×.2 + 3×.1 + 4×.1 + 5×.1 = 2.1
    assert r.row_summaries == (2.1,)


def test_the_stored_order_still_decides_how_the_bars_are_drawn():
    """Deliberately unchanged: this fixes the ARITHMETIC, not the layout.

    Existing decks are drawn in file order and changing that silently would
    re-order every word-scale chart already approved by a client.
    """
    r = _run(_descending_word_scale(), _LOPSIDED, row_summary_fn="top2_sum")
    assert list(r.categories) == list(reversed(WORDS))


# ── 2. "En osaa sanoa" is not the top of the scale ─────────────────────────
def _scale_with_dont_know():
    labels = [(1.0, "1 Erittäin tyytymätön"), (2.0, "2"), (3.0, "3"),
              (4.0, "4"), (5.0, "5 Erittäin tyytyväinen"),
              (9.0, "En osaa sanoa")]
    return Variable(name="q", label="Tyytyväisyys", measurement="categorical",
                    value_labels=tuple(ValueLabel(v, t) for v, t in labels),
                    missing_values=frozenset())


# Counts chosen so 4+5 (30) and 5+"En osaa sanoa" (50) cannot be confused: an
# earlier draft of this test used counts where the two happened to be equal, and
# it passed against the defect.
_WITH_EOS = [1.0] * 10 + [2.0] * 10 + [3.0] * 20 + [4.0] * 10 + [5.0] * 20 + [9.0] * 30


def test_dont_know_is_not_counted_into_the_top_box():
    r = _run(_scale_with_dont_know(), _WITH_EOS, row_summary_fn="top2_sum")
    assert r.row_summaries == (30.0,)   # 4 and 5, not 5 and "En osaa sanoa"


def test_dont_know_does_not_enter_the_mean():
    r = _run(_scale_with_dont_know(), _WITH_EOS, row_summary_fn="mean")
    # Over the 70 % who gave a scale answer:
    # (1×10 + 2×10 + 3×20 + 4×10 + 5×20) / 70 = 3.2857
    assert r.row_summaries == (3.3,)


# ── The same thing, on the drawn slide ─────────────────────────────────────
def test_the_printed_top_box_does_not_depend_on_the_file_order():
    """The property, at the pixel level: the same answers reported the same way.

    Two SAV files, identical data, differing only in the order the value labels
    are written. The summary column is one number about the respondents — it
    cannot come out different because an export tool wrote its labels backwards.
    """
    import io

    from PIL import Image

    _CROP_SIZE: list[int] = [0, 0]

    from reportbuilder.render.image import IMAGE_BUILDERS
    from suite._helpers import assert_single_picture, make_ctx, make_spec

    def strip(ascending: bool) -> bytes:
        order = WORDS if ascending else list(reversed(WORDS))
        var = Variable(
            name="q", label="Kuinka tyytyväinen olet?", measurement="categorical",
            value_labels=tuple(ValueLabel(float(WORDS.index(lbl) + 1), lbl)
                               for lbl in order),
            missing_values=frozenset())
        model = QuestionModel(variables={"q": var}, questions=[])
        q = Question(qid="q", kind="single", variables=("q",), text=var.label)
        kw = dict(classifying_var=None, row_summary_fn="top2_sum",
                  row_summary_label="Top 2", sort=SortSpec(basis="data_order"))
        series = engine.compute(q, make_spec("stacked_horizontal_bar", **kw),
                                pd.DataFrame({"q": _LOPSIDED}), model)
        _prs, slide, slot, ctx = make_ctx("stacked_horizontal_bar", series, **kw)
        IMAGE_BUILDERS["stacked_horizontal_bar"](ctx)
        blob = assert_single_picture(slide, slot).image.blob
        img = Image.open(io.BytesIO(blob)).convert("RGB")
        w, h = img.size
        # Right of where a 100 % bar ends, above the legend — the legend lists the
        # levels in the file's own order, so it differs between the two by design.
        crop = img.crop((int(w * 0.9), 0, w, int(h * 0.85)))
        _CROP_SIZE[:] = crop.size
        return crop.tobytes()

    a, b = strip(ascending=True), strip(ascending=False)
    assert a == b
    # Two blank crops would also be equal. Check there is something drawn in
    # there before believing the comparison means anything.
    from PIL import Image as _I
    assert len(set(_I.frombytes("RGB", _CROP_SIZE, a).getdata())) > 1, (
        "the summary column is blank — this comparison proves nothing")


# ── What the label SAYS decides, not whether it parsed a digit ─────────────
def test_a_real_endpoint_typed_without_its_number_still_counts():
    """The regression this file's own fix introduced.

    `is_rating` tolerates one label the digit parse cannot read, and that label
    is as often a genuine endpoint typed without its number as it is "En osaa
    sanoa". Treating every unparsed label as a non-answer dropped a real scale
    point from the box AND from both halves of the mean — on a chart that still
    drew in the right order, so nothing looked wrong.
    """
    labels = ["1 - Täysin eri mieltä", "2", "3", "4", "Täysin samaa mieltä"]
    var = Variable(name="q", label="Väite", measurement="categorical",
                   value_labels=tuple(ValueLabel(float(i + 1), t)
                                      for i, t in enumerate(labels)),
                   missing_values=frozenset())
    data = [1.0] * 10 + [2.0] * 10 + [3.0] * 20 + [4.0] * 30 + [5.0] * 30
    assert _run(var, data, row_summary_fn="top2_sum").row_summaries == (60.0,)
    assert _run(var, data, row_summary_fn="mean").row_summaries == (3.6,)


def test_the_mean_weights_by_the_scale_point_not_the_sav_code():
    """A reverse-coded file: the label says 5, the code says 1.

    Weighting by code printed 1.0 where everyone had answered "Täysin samaa
    mieltä" — and the same data charted as a battery printed 5.0, so the two
    paths disagreed about the same respondents.
    """
    labels = [(1.0, "5 - Täysin samaa mieltä"), (2.0, "4"), (3.0, "3"),
              (4.0, "2"), (5.0, "1 - Täysin eri mieltä")]
    var = Variable(name="q", label="Väite", measurement="categorical",
                   value_labels=tuple(ValueLabel(v, t) for v, t in labels),
                   missing_values=frozenset())
    assert _run(var, [1.0] * 50, row_summary_fn="mean").row_summaries == (5.0,)


def test_a_dont_know_coded_inside_the_run_is_still_not_a_scale_point():
    """Word-only 1..5 with "En osaa sanoa" coded 6 — contiguous, so the codes
    looked like a six-point scale and EOS became the top of it."""
    words = ["Erittäin tyytymätön", "Tyytymätön", "Ei kumpaakaan",
             "Tyytyväinen", "Erittäin tyytyväinen", "En osaa sanoa"]
    var = Variable(name="q", label="Tyytyväisyys", measurement="categorical",
                   value_labels=tuple(ValueLabel(float(i + 1), t)
                                      for i, t in enumerate(words)),
                   missing_values=frozenset())
    # 25 % at the top level, 15 % at the one below, 10 % "En osaa sanoa".
    data = ([1.0] * 20 + [2.0] * 20 + [3.0] * 10 + [4.0] * 15 + [5.0] * 25
            + [6.0] * 10)
    assert _run(var, data, row_summary_fn="top2_sum").row_summaries == (40.0,)


def test_two_levels_shortened_to_one_label_do_not_pull_in_the_level_below():
    """"Top 2" became top level + neutral once the author shortened both agree
    levels to the same words."""
    from reportbuilder.stats.engine import _top_scale_categories

    labels = ["1 - Täysin eri mieltä", "2", "3 - Ei kumpaakaan",
              "4 - Melko samaa mieltä", "5 - Täysin samaa mieltä"]
    var = Variable(name="q", label="Väite", measurement="categorical",
                   value_labels=tuple(ValueLabel(float(i + 1), t)
                                      for i, t in enumerate(labels)),
                   missing_values=frozenset())
    overrides = {"4 - Melko samaa mieltä": "Samaa mieltä",
                 "5 - Täysin samaa mieltä": "Samaa mieltä"}
    shown = ["1 - Täysin eri mieltä", "2", "3 - Ei kumpaakaan", "Samaa mieltä"]

    top = _top_scale_categories(var, shown, 2, overrides=overrides)
    assert "3 - Ei kumpaakaan" not in top, "the neutral level is not agreement"
    assert top == ["Samaa mieltä"]


def test_a_picked_code_means_the_same_in_a_battery_as_in_a_single_bar():
    """"Sum these codes" has to select the same answers either way.

    The editor's code picker offers SAV codes (question.values). A single
    stacked bar looked them up by code; a battery looked them up by scale
    POINT. On a reverse-coded file — the label reading "5" stored on code 1 —
    ticking that code summed 100 % in one and 0 % in the other, from identical
    data.
    """
    import pandas as pd

    from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec

    labels = [(1.0, "5 - Täysin samaa mieltä"), (2.0, "4"), (3.0, "3"),
              (4.0, "2"), (5.0, "1 - Täysin eri mieltä")]

    def _var(name):
        return Variable(name=name, label=f"Väite {name}", measurement="categorical",
                        value_labels=tuple(ValueLabel(v, t) for v, t in labels),
                        missing_values=frozenset())

    def _spec():
        return ChartSpec(question_ref="q", chart_type="stacked_horizontal_bar",
                         statistic="pct", classifying_var=None,
                         number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                         template_slot="s", elements=ElementToggles(),
                         row_summary_fn="sum", row_summary_codes=(1.0,))

    single = engine.compute(
        Question(qid="q", kind="single", variables=("a",), text="Väite"), _spec(),
        pd.DataFrame({"a": [1.0] * 50}),
        QuestionModel(variables={"a": _var("a")}, questions=[]))
    battery = engine.compute(
        Question(qid="q", kind="battery", variables=("a", "b"), text="Väite"), _spec(),
        pd.DataFrame({"a": [1.0] * 50, "b": [1.0] * 50}),
        QuestionModel(variables={"a": _var("a"), "b": _var("b")}, questions=[]))

    assert single.row_summaries == (100.0,)
    assert battery.row_summaries == (100.0, 100.0)
