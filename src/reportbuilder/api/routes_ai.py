"""AI text routes — egoHive-backed descriptive slide titles + short category labels.

Both endpoints NEVER return 500: any egoHive/extract/compute failure is wrapped as
HTTPException(503). The LLM only writes prose/labels — the numbers shown elsewhere
stay deterministic from the stats engine. The caller stores the results into
``ChartSpec.slide_title`` and ``ChartSpec.category_label_overrides``.

- POST /materials/{material_id}/ai/slide-title  -> {"title": "..."}
- POST /materials/{material_id}/ai/short-labels  -> {"overrides": [["full","short"], ...]}
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nsight.agent.egohive_client import EgoHiveError, egohive_chat

from reportbuilder.ai.reference import ReferenceLabels
from reportbuilder.ai.text import generate_slide_title, shorten_labels
from reportbuilder.api.deps import get_client
from reportbuilder.api.routes_questions import _category_labels
from reportbuilder.ingest.multi_group import enrich_model
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    SortSpec,
)
from reportbuilder.stats.engine import compute
from reportbuilder.stats.series import SeriesResult
from reportbuilder.store.datahive_client import DataHiveClient

ai_router = APIRouter()

# Repo root: src/reportbuilder/api/routes_ai.py -> parents[3] == project root.
_REPO_ROOT = Path(__file__).resolve().parents[3]

_AI_UNAVAILABLE = "AI service (egoHive) is unavailable"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _reference_paths() -> list[Path]:
    """Originating reference decks used as the short-label corpus."""
    return sorted((_REPO_ROOT / "input").glob("*.pptx"))


def _reference_labels() -> ReferenceLabels:
    """Load (cached) the reference-label corpus. Indirection so tests can patch."""
    return ReferenceLabels.load(_reference_paths())


def _load_df_model(material_id: str, client: DataHiveClient):
    """Fetch the material's .sav bytes and return (df, model) with multi-groups applied."""
    raw = client.get_material(material_id)
    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        df, model = read_sav(tmp_path)
    finally:
        os.unlink(tmp_path)
    return df, enrich_model(model)


def _findings_from_series(
    series: SeriesResult, top_n: int
) -> list[tuple[str, float]]:
    """Top-N (category, value) pairs by the Total-segment value of the statistic."""
    stat = series.statistic
    pairs: list[tuple[str, float]] = []
    for cat in series.categories:
        cell = series.cells.get((cat, "Total"))
        if cell is None:
            continue
        val = cell.value(stat)
        if val is None:
            continue
        pairs.append((cat, float(val)))
    pairs.sort(key=lambda p: p[1], reverse=True)
    return pairs[: max(1, top_n)]


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #
class SlideTitleBody(BaseModel):
    """Enough to compute the series; everything but ``question_ref`` is optional."""

    question_ref: str
    statistic: str = "pct"
    classifying_var: str | None = None
    show_not_answered: bool = False
    not_answered_codes: list[float] | None = None
    show_empty_categories: bool = True
    top_n: int = 3


class ShortLabelsBody(BaseModel):
    """Resolve labels from explicit ``categories`` or from the question's labels."""

    question_ref: str | None = None
    categories: list[str] | None = None


def _spec_from_title_body(body: SlideTitleBody) -> ChartSpec:
    """Build a minimal ChartSpec sufficient for the stats engine to compute a series."""
    return ChartSpec(
        question_ref=body.question_ref,
        chart_type="horizontal_bar",  # irrelevant to compute()
        statistic=body.statistic,
        classifying_var=body.classifying_var,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="ai",
        elements=ElementToggles(),
        show_not_answered=body.show_not_answered,
        show_empty_categories=body.show_empty_categories,
        not_answered_codes=(
            tuple(float(c) for c in body.not_answered_codes)
            if body.not_answered_codes is not None
            else None
        ),
    )


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@ai_router.post("/materials/{material_id}/ai/slide-title")
def ai_slide_title(
    material_id: str,
    body: SlideTitleBody,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Generate a descriptive slide title for a chart. Returns {"title": "..."}.

    Computes the deterministic SeriesResult, takes the top-N categories as
    findings, and asks egoHive for a headline. egoHive failures -> 503.
    """
    try:
        df, model = _load_df_model(material_id, client)
    except HTTPException:
        raise
    except Exception as exc:  # data load is part of the AI flow — degrade to 503
        raise HTTPException(status_code=503, detail=f"Could not load material: {exc}") from exc

    try:
        question = model.question(body.question_ref)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Question '{body.question_ref}' not found"
        ) from exc

    try:
        spec = _spec_from_title_body(body)
        series = compute(question, spec, df, model)
        findings = _findings_from_series(series, body.top_n)
        # No computable findings (e.g. an empty/degenerate variable) → the LLM
        # would have nothing to summarise and tends to reply with a meta-question.
        # Fall back to the question text instead of generating a bogus headline.
        if not findings:
            return {"title": question.text}
        title = generate_slide_title(question.text, findings, chat=egohive_chat)
    except EgoHiveError as exc:
        raise HTTPException(status_code=503, detail=_AI_UNAVAILABLE) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not generate title: {exc}") from exc

    return {"title": title}


@ai_router.post("/materials/{material_id}/ai/short-labels")
def ai_short_labels(
    material_id: str,
    body: ShortLabelsBody,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Shorten category labels. Returns {"overrides": [["full","short"], ...]}.

    Labels come from the request ``categories`` or, failing that, the question's
    base category labels. Reference/extract failures -> 503; egoHive
    unreachability degrades gracefully (shorten_labels falls back to originals).
    """
    # 1. Resolve the labels to shorten.
    if body.categories:
        labels = [str(c) for c in body.categories]
    elif body.question_ref:
        try:
            _df, model = _load_df_model(material_id, client)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"Could not load material: {exc}"
            ) from exc
        try:
            question = model.question(body.question_ref)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail=f"Question '{body.question_ref}' not found"
            ) from exc
        try:
            labels = _category_labels(model, question)
        except Exception as exc:
            # Never 500: a malformed model surfaces as a clean 503.
            raise HTTPException(
                status_code=503, detail=f"Could not resolve category labels: {exc}"
            ) from exc
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'categories' or 'question_ref'.",
        )

    # 2. Build the reference corpus (tolerant load) and shorten.
    try:
        reference = _reference_labels()
        overrides = shorten_labels(labels, reference=reference, chat=egohive_chat)
    except EgoHiveError as exc:
        raise HTTPException(status_code=503, detail=_AI_UNAVAILABLE) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Could not shorten labels: {exc}"
        ) from exc

    return {"overrides": [[full, short] for full, short in overrides]}


__all__ = ["ai_router"]
