"""Vertical bar (column) chart plugin — the baseline default for few short labels."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import clustered_bar_schema
from reportbuilder.render.shape import SeriesShape
from reportbuilder.render.image.bars import build_image_column
from reportbuilder.render.native.column import build_vertical_bar


def suitability(question, series) -> float | None:
    """High for few (<=6) short labels; lower for many/long categories."""
    s = SeriesShape.of(question, series)
    if s.n_categories <= 6 and s.max_label_len <= 14:
        return 0.80
    return 0.35


def suggest(question, series) -> float | None:
    """Baseline fallback — always eligible at a low score so there is always a
    default when nothing more specific fits."""
    return 0.40


register(ChartPlugin(
    id="vertical_bar",
    label="Vertical Bar",
    image_build=build_image_column,
    native_build=build_vertical_bar,
    suitability=suitability,
    suggest=suggest,
    config_schema=clustered_bar_schema(),
))
