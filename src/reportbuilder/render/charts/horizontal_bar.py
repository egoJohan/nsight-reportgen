"""Horizontal bar chart plugin — preferred for many/long categories and for
multi-response sets (one bar per tick-box option)."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import clustered_bar_schema
from reportbuilder.render.shape import SeriesShape
from reportbuilder.render.image.bars import build_image_bar
from reportbuilder.render.native.bar import build_horizontal_bar


def _many_or_long(s: SeriesShape) -> bool:
    return s.n_categories > 6 or s.max_label_len > 14


def suitability(question, series) -> float | None:
    """High when many (>6) categories or any long label (>14 chars)."""
    s = SeriesShape.of(question, series)
    return 0.85 if _many_or_long(s) else 0.55


def suggest(question, series) -> float | None:
    """Default for multi-response (one bar per option, often many/long labels)
    and for any single series with many/long categories."""
    s = SeriesShape.of(question, series)
    if s.is_multi:
        return 1.10  # multi-response always defaults to bars
    if _many_or_long(s):
        return 0.90
    return None


register(ChartPlugin(
    id="horizontal_bar",
    label="Horizontal Bar",
    image_build=build_image_bar,
    native_build=build_horizontal_bar,
    suitability=suitability,
    suggest=suggest,
    config_schema=clustered_bar_schema(),
))
