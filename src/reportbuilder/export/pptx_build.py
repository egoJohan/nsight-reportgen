from __future__ import annotations
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
    is_demographics_grid,
    renders_as_bullets,
)
from reportbuilder.model.question import QuestionModel
from reportbuilder.render.base import StyleSpec
from reportbuilder.render.deck import series_key, render_report, render_to_file, RenderCancelled
from reportbuilder.render.image._mpl import series_is_empty
from reportbuilder.stats.engine import compute
from reportbuilder.stats.series import SeriesResult


def _empty_series(statistic: str) -> SeriesResult:
    return SeriesResult(categories=(), segments=("Total",), cells={},
                        base_n={"Total": 0}, statistic=statistic or "pct")


def _cell_spec(ref: str, chart_type: str) -> ChartSpec:
    """A minimal spec for one demographics-grid cell chart."""
    return ChartSpec(
        question_ref=ref, chart_type=chart_type, statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="pct"), template_slot="cell", elements=ElementToggles(),
    )


def build_pptx(report: Report, model: QuestionModel, data, out_path: str,
               style: StyleSpec | None = None, cancel_check=None,
               empty_out: list[str] | None = None,
               notes: list | None = None) -> str:
    """Compute each chart's SeriesResult, then render the Report to a .pptx (REQ-C-22/18).
    `cancel_check` (optional) is polled between charts so a long build aborts promptly.
    `empty_out` (optional) collects the key of every chart with nothing to plot.
    `notes` (optional) collects the `RenderNote`s the builders raise for the author."""
    return _build(report, model, data, style, cancel_check, out_path=out_path,
                  empty_out=empty_out, notes=notes)


def build_presentation(report: Report, model: QuestionModel, data,
                       style: StyleSpec | None = None, cancel_check=None,
                       empty_out: list[str] | None = None,
                       notes: list | None = None):
    """The same deck, handed back as a Presentation instead of a file.

    The chart preview needs the SHAPES — where the picture landed, what the
    footer says and in which font — so it can draw them itself instead of paying
    LibreOffice per chart. Nothing about the rendering differs; only the ending.
    """
    return _build(report, model, data, style, cancel_check, out_path=None,
                  empty_out=empty_out, notes=notes)


def _build(report: Report, model: QuestionModel, data, style, cancel_check,
           *, out_path: str | None, empty_out: list[str] | None = None,
           notes: list | None = None):
    if style is None:
        style = StyleSpec()   # generic base style (no template); deck synthesizes slides
    series_by_ref: dict = {}
    titles: dict = {}
    for spec in report.charts:
        if getattr(spec, "excluded", False):
            continue          # unticked in Select — kept in the report, off the deck
        if cancel_check is not None and cancel_check():
            raise RenderCancelled()
        # Demographics grid: compute a series per cell chart (by question_ref).
        if is_demographics_grid(spec):
            for c in (spec.options.get("charts") or []):
                ref = c.get("question_ref")
                ctype = c.get("chart_type") or "vertical_bar"
                try:
                    q = model.question(ref)
                    series_by_ref[ref] = compute(q, _cell_spec(ref, ctype), data, model)
                    titles[ref] = q.text
                except Exception:
                    pass
            continue
        # Bullet slides (special slides + themes) carry no series — they render
        # as text in render_report. Skip stats, but record the question text so a
        # themes slide can use it as its heading.
        if renders_as_bullets(spec):
            try:
                titles[spec.question_ref] = model.question(spec.question_ref).text
            except Exception:
                pass
            continue
        q = model.question(spec.question_ref)
        # A single chart that can't compute (e.g. a wordcloud with no words)
        # must not crash the whole deck — fall back to an empty series, which
        # render_report draws as a "no data" placeholder.
        try:
            series_by_ref[series_key(spec)] = compute(q, spec, data, model)
        except Exception:
            series_by_ref[series_key(spec)] = _empty_series(spec.statistic)
        titles[spec.question_ref] = q.text
        # A chart with nothing to plot draws a BLANK placeholder — the slide
        # says nothing about it any more, so the only person who can notice is
        # the author, and only if we tell them. Asked here, where the series is
        # computed, with the predicate render_report itself branches on: two
        # copies of "is this blank?" would eventually disagree, and the one that
        # was wrong would be this one, silently. (Johan, 2026-09-16)
        if empty_out is not None and series_is_empty(series_by_ref[series_key(spec)]):
            empty_out.append(series_key(spec))
    if out_path is None:
        return render_report(report, series_by_ref, style, titles=titles,
                             cancel_check=cancel_check, notes=notes)
    return render_to_file(report, series_by_ref, style, out_path, titles=titles,
                          cancel_check=cancel_check, notes=notes)
