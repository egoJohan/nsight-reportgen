from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from nsight.render.fill_chart import (
    fill_chart,
    read_chart_categories,
    read_chart_series,
    replace_one_series,
)
from nsight.render.fill_table import fill_table
from nsight.render.fill_text import set_lines, set_text
from nsight.render.template import Template


@dataclass
class ChartFill:
    name: str
    categories: list[str] | None = None
    series: dict[str, list[float]] | None = None
    series_name: str | None = None
    values_by_category: dict[str, float] | None = None
    occurrence: int = 0


@dataclass
class TableFill:
    name: str
    cells: dict[tuple[int, int], str]
    occurrence: int = 0


@dataclass
class TextFill:
    name: str
    value: str | None = None
    occurrence: int = 0
    # When `lines` is set, write one paragraph per line starting at `start`,
    # preserving the paragraphs before `start` (e.g. a "TOP 10" header).
    lines: list[str] | None = None
    start: int = 0


@dataclass
class SlideFill:
    slide_idx: int
    charts: list[ChartFill] = field(default_factory=list)
    tables: list[TableFill] = field(default_factory=list)
    texts: list[TextFill] = field(default_factory=list)


def render(*, template_path: Path, out_path: Path, fills: list[SlideFill]) -> Path:
    tmpl = Template(template_path)
    for sf in fills:
        for cf in sf.charts:
            shape = tmpl.shape(slide_idx=sf.slide_idx, name=cf.name, occurrence=cf.occurrence)
            if cf.series_name is not None:
                cats = read_chart_categories(shape)
                existing = read_chart_series(shape)[cf.series_name]
                vbc = cf.values_by_category or {}
                aligned = [vbc.get(cat, existing[i]) for i, cat in enumerate(cats)]
                replace_one_series(shape, series_name=cf.series_name, values=aligned)
            else:
                fill_chart(shape, categories=cf.categories, series=cf.series)
        for tf in sf.tables:
            fill_table(tmpl.shape(slide_idx=sf.slide_idx, name=tf.name, occurrence=tf.occurrence), tf.cells)
        for xf in sf.texts:
            shape = tmpl.shape(slide_idx=sf.slide_idx, name=xf.name, occurrence=xf.occurrence)
            if xf.lines is not None:
                set_lines(shape, xf.lines, start=xf.start)
            else:
                set_text(shape, xf.value or "")
    tmpl.save(out_path)
    return out_path
