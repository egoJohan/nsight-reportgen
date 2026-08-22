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


def test_one_surviving_group_draws_a_titled_single_panel():
    # Distinct from the degraded case: one group survived, so the reader must be
    # told WHICH group the single circle describes. (spec 2026-08-22)
    series = _series(("Naiset", "Miehet", "Total"),
                     {"Naiset": 512, "Miehet": 4, "Total": 516})
    _prs, _slide, _slot, ctx = make_ctx("pie", series, classifying_var="sex")
    fig = _build_pie_figure(ctx, donut=False)
    axes = list(fig.axes)
    assert len(axes) == 1
    assert axes[0].get_title() == "Naiset"
    assert axes[0].get_xlabel() == "n = 512"


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
