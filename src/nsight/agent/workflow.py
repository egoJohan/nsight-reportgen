"""Agent workflow: deterministic numbers first, LLM prose second."""

from __future__ import annotations

from typing import Callable

import pandas as pd

from nsight.brief import Brief, SlideJob
from nsight.build import build_slidefill
from nsight.render.renderer import SlideFill

Narrator = Callable[[SlideJob, dict], str]


def _numbers_from(base: SlideFill) -> dict:
    """Whole-percent numbers per chart for the narrator's benefit (never written)."""
    numbers: dict[str, dict[str, float]] = {}
    for cf in base.charts:
        vbc = cf.values_by_category or {}
        numbers[cf.name] = {k: round(v * 100.0) for k, v in vbc.items()}
    return numbers


def generate_fills(
    brief: Brief,
    frame: pd.DataFrame,
    *,
    brand_vars: dict[str, str],
    weight: str | None,
    narrator: Narrator,
) -> list[SlideFill]:
    fills: list[SlideFill] = []
    for job in brief.jobs:
        base = build_slidefill(job, frame, brand_vars=brand_vars, weight=weight)
        message = None
        if job.key_message:
            message = narrator(job, _numbers_from(base))
        final = build_slidefill(
            job, frame, brand_vars=brand_vars, weight=weight, key_message=message
        )
        fills.append(final)
    return fills
