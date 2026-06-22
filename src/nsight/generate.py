"""End-to-end deck generation: brief -> deterministic build -> agent -> render."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from nsight.agent.workflow import generate_fills
from nsight.brief import SlideJob, parse_brief
from nsight.build import preflight
from nsight.config import CODEBOOK_JSON, SURVEY_DB
from nsight.render.renderer import render
from nsight.render.template import Template
from nsight.store.survey_store import SurveyStore

# Sentinel: caller did not supply weight, so we fall back to the Attendo binding.
_WEIGHT_DEFAULT = "__default__"


def generate_deck(
    *,
    sav: Path,
    brief_path: Path,
    template: Path,
    out: Path,
    narrator: Callable[[SlideJob, dict], str] | None = None,
    brand_vars: dict[str, str] | None = None,
    weight: str | None | str = _WEIGHT_DEFAULT,
) -> Path:
    store = SurveyStore(db_path=SURVEY_DB, codebook_path=CODEBOOK_JSON)
    if store.frame().empty:
        store.ingest(sav)
    frame = store.frame()

    brief = parse_brief(brief_path)
    errors = preflight(brief.jobs, Template(template))
    if errors:
        raise ValueError("brief→template binding errors:\n" + "\n".join(errors))

    if brand_vars is None:
        from nsight.attendo_bindings import AIDED_AWARENESS_VARS
        brand_vars = AIDED_AWARENESS_VARS

    if weight is _WEIGHT_DEFAULT:
        from nsight.attendo_bindings import WEIGHT_VAR
        weight = WEIGHT_VAR

    if narrator is None:
        narrator = lambda job, numbers: (job.title or job.id)

    fills = generate_fills(
        brief,
        frame,
        brand_vars=brand_vars,
        weight=weight,
        narrator=narrator,
    )
    return render(template_path=template, out_path=out, fills=fills)
