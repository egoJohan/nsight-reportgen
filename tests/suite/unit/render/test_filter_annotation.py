"""The methodology footer must not claim a separate-layout slide is split by only
the first variable."""
from __future__ import annotations

from reportbuilder.render.elements import add_filter_annotation
from reportbuilder.stats.series import Cell, SeriesResult

from suite._helpers import make_ctx


def _series():
    return SeriesResult(categories=("A",), segments=("Total",),
                        cells={("A", "Total"): Cell(pct=100.0, count=1.0, mean=None)},
                        base_n={"Total": 1}, statistic="pct")


def _texts(slide):
    return [sh.text_frame.text for sh in slide.shapes if sh.has_text_frame]


def test_one_classifier_names_it():
    _prs, slide, _slot, ctx = make_ctx("horizontal_bar", _series(), classifying_var="sex")
    add_filter_annotation(ctx)
    assert "sex" in " ".join(_texts(slide))


def test_separate_layout_names_both():
    _prs, slide, _slot, ctx = make_ctx(
        "horizontal_bar", _series(), classifying_var="sex", classifying_var_2="age",
        options={"xtab_layout": "separate"})
    add_filter_annotation(ctx)
    text = " ".join(_texts(slide))
    assert "sex" in text and "age" in text


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


def test_a_bar_chart_never_claims_it_omitted_groups():
    # Bars draw every group; only the panelled types cap at three. (ruling 2026-08-22)
    s = _split_series(("18-29", "30-44", "45-59", "60+", "Total"),
                      {"18-29": 50, "30-44": 90, "45-59": 70, "60+": 30,
                       "Total": 240})
    _prs, slide, _slot, ctx = make_ctx("horizontal_bar", s, classifying_var="age")
    add_filter_annotation(ctx)
    text = " ".join(_texts(slide))
    assert "Ei mahtunut sivulle" not in text and "Ei raportoitu" not in text


def test_degraded_split_says_grouping_could_not_be_drawn():
    # Every group is under the base floor -- the renderer falls back to the whole
    # sample, and that is the single most severe omission the feature can make:
    # the slide looks like an ordinary un-split pie unless the footer says
    # otherwise. The degraded clause REPLACES the per-group ones, not stacks with
    # them. (coordinator review 2026-08-22)
    s = _split_series(("Naiset", "Miehet", "Total"),
                      {"Naiset": 4, "Miehet": 6, "Total": 10})
    _prs, slide, _slot, ctx = make_ctx("pie", s, classifying_var="sex")
    add_filter_annotation(ctx)
    text = " ".join(_texts(slide))
    assert "Ryhmittelyä ei voitu piirtää" in text
    assert "Ei raportoitu:" not in text and "Ei mahtunut sivulle:" not in text
