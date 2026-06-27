"""ChartPlugin registry — graph styles as self-contained plugins (REQ-C-13, R2).

This module is GENERIC: it defines the plugin contract, the registry, and a
registry-driven default-picker.  It contains **no graph-specific logic** — every
chart type lives in its own module under ``render/charts/`` and self-registers,
so adding a new graph style touches no generic code.

Each :class:`ChartPlugin` carries:
- ``id`` / ``label``        — canonical chart_type key + human label
- ``image_build`` / ``native_build`` — the renderers (ctx -> …)
- ``suitability(question, series) -> float | None`` — feasibility for THIS data
  shape; ``None`` means the type cannot faithfully represent the data and is
  hidden from the picker (drives ``compatible_chart_types``).
- ``suggest(question, series) -> float | None`` — how strongly this type should
  be the *default* pick; ``None`` = never auto-suggested.  ``suggest_chart_type``
  returns the highest-scoring plugin.
- ``requires`` — optional prerequisites (e.g. ``("scatter_xy",)``).

Usage::

    from reportbuilder.render.plugins import plugin, suggest_chart_type
    builder = plugin("horizontal_bar").image_build
    default = suggest_chart_type(question, series)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from reportbuilder.render.config_schema import ConfigField
from reportbuilder.stats.series import SeriesResult

# ---------------------------------------------------------------------------
# Plugin dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChartPlugin:
    id: str                          # canonical chart_type key
    label: str                       # human label for UI
    image_build: Callable | None     # ctx -> None (matplotlib, house style)
    native_build: Callable | None    # ctx -> graphic frame (OOXML)
    suitability: Callable            # (question, series) -> float | None
    suggest: Callable | None = None  # (question, series) -> float | None
    requires: tuple[str, ...] = ()   # e.g. ("scatter_xy",) — prerequisites
    config_schema: tuple[ConfigField, ...] = ()  # ordered config fields (declarative UI)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CHART_PLUGINS: dict[str, ChartPlugin] = {}


def register(p: ChartPlugin) -> None:
    """Register a ChartPlugin in the global registry (idempotent per id)."""
    CHART_PLUGINS[p.id] = p


def plugin(chart_type: str) -> ChartPlugin:
    """Return the ChartPlugin for *chart_type*. Raises KeyError if unknown."""
    try:
        return CHART_PLUGINS[chart_type]
    except KeyError:
        raise KeyError(
            f"No ChartPlugin registered for chart_type={chart_type!r}. "
            f"Known types: {sorted(CHART_PLUGINS)}"
        )


# ---------------------------------------------------------------------------
# Registry-driven default picker (no hardcoded type names)
# ---------------------------------------------------------------------------

def suggest_chart_type(question, series: SeriesResult) -> str:
    """Return the smartest default chart_type for *question*/*series*.

    Purely registry-driven: each plugin scores how strongly it should be the
    default via its ``suggest`` hook; the highest score wins.  Ties resolve by
    registration order.  Always returns a registered type (``vertical_bar`` is
    the baseline fallback every plugin set provides).
    """
    best_id: str | None = None
    best_score = float("-inf")
    for cid, p in CHART_PLUGINS.items():
        if p.suggest is None:
            continue
        try:
            score = p.suggest(question, series)
        except Exception:
            continue
        if score is None:
            continue
        if score > best_score:
            best_score = score
            best_id = cid
    return best_id or "vertical_bar"


# ---------------------------------------------------------------------------
# Populate the registry: importing the chart modules self-registers each plugin.
# Done at the bottom so the registry primitives above are fully defined before
# the chart modules import them (avoids a circular-import race).
# ---------------------------------------------------------------------------
from reportbuilder.render import charts as _charts  # noqa: E402,F401
