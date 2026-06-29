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
from reportbuilder.ai.text import (
    generate_conclusion_bullets,
    generate_demographics_bullets,
    generate_open_themes,
    generate_overview_bullets,
    generate_slide_title,
    pick_demographic_questions,
    shorten_labels,
)
from reportbuilder.api.deps import get_client
from reportbuilder.api.routes_questions import _category_labels
from reportbuilder.ingest.multi_group import enrich_model
from reportbuilder.ingest.sav_reader import read_sav, sav_file_label
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


def _load_df_model_labeled(material_id: str, client: DataHiveClient):
    """Like _load_df_model but also return the SAV's study label (file label).

    Falls back to the material id when the .sav carries no embedded label.
    """
    raw = client.get_material(material_id)
    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        df, model = read_sav(tmp_path)
        # Empty when the .sav carries no embedded study label — the prompts then
        # omit the name line rather than printing an internal material id.
        label = sav_file_label(tmp_path) or ""
    finally:
        os.unlink(tmp_path)
    return df, enrich_model(model), label


def _kind_spec(question, model) -> ChartSpec:
    """A minimal ChartSpec that compute() accepts for this question.

    compute() raises for text questions unless chart_type="wordcloud", and a
    battery yields findings only with statistic="mean" — so pick per kind. Text
    is detected by variable *measurement* (kind is usually "single").
    """
    qvars = [model.variables[v] for v in question.variables if v in model.variables]
    is_text = bool(qvars) and all(v.measurement == "text" for v in qvars)
    if is_text:
        statistic, chart_type = "count", "wordcloud"
    elif question.kind == "battery":
        statistic, chart_type = "mean", "horizontal_bar"
    else:  # single | multi
        statistic, chart_type = "pct", "horizontal_bar"
    return ChartSpec(
        question_ref=question.qid,
        chart_type=chart_type,
        statistic=statistic,
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="ai",
        elements=ElementToggles(),
    )


def _findings_for_refs(
    refs: list[str], df, model, *, top_n: int = 3, cap: int = 25
) -> list[tuple[str, list[tuple[str, float]]]]:
    """Per-question top findings for the given refs, guarded against compute()
    raising on incompatible kinds and skipping questions that yield nothing.
    Capped to bound egoHive latency.
    """
    out: list[tuple[str, list[tuple[str, float]]]] = []
    for ref in refs[:cap]:
        try:
            q = model.question(ref)
            series = compute(q, _kind_spec(q, model), df, model)
            findings = _findings_from_series(series, top_n)
        except Exception:
            continue  # skip incompatible/empty questions
        if findings:
            out.append((q.text, findings))
    return out


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


# --------------------------------------------------------------------------- #
# Special slides — Overview / Conclusion / Demographics (bullet lists)
# --------------------------------------------------------------------------- #
class SpecialSlideBody(BaseModel):
    """Optional report context. ``question_refs`` are the report's current chart
    questions (used for Overview topics / Conclusion findings)."""

    question_refs: list[str] = []


class ThemesBody(BaseModel):
    question_ref: str


@ai_router.post("/materials/{material_id}/ai/themes")
def ai_themes(
    material_id: str,
    body: ThemesBody,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Summarise an open-ended question's answers into key themes (bullets)."""
    try:
        df, model = _load_df_model(material_id, client)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not load material: {exc}") from exc
    try:
        question = model.question(body.question_ref)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Question '{body.question_ref}' not found"
        ) from exc
    try:
        series = compute(question, _kind_spec(question, model), df, model)
        word_freqs = _findings_from_series(series, 25)
        var = question.variables[0]
        answers = [
            str(x) for x in df[var].dropna().tolist() if str(x).strip()
        ][:40]
        if not word_freqs and not answers:
            return {"bullets": []}
        bullets = generate_open_themes(
            question.text, word_freqs, answers, chat=egohive_chat
        )
    except EgoHiveError as exc:
        raise HTTPException(status_code=503, detail=_AI_UNAVAILABLE) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not generate themes: {exc}") from exc
    return {"bullets": bullets}


def _question_texts(refs: list[str], model) -> list[str]:
    texts: list[str] = []
    for ref in refs:
        try:
            texts.append(model.question(ref).text)
        except KeyError:
            continue
    return texts


@ai_router.post("/materials/{material_id}/ai/overview")
def ai_overview(
    material_id: str,
    body: SpecialSlideBody,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Background/overview bullets about the research. Returns {"bullets": [...]}."""
    try:
        df, model, label = _load_df_model_labeled(material_id, client)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not load material: {exc}") from exc

    texts = _question_texts(body.question_refs, model) or [q.text for q in model.questions]
    try:
        bullets = generate_overview_bullets(label, texts, len(df), chat=egohive_chat)
    except EgoHiveError as exc:
        raise HTTPException(status_code=503, detail=_AI_UNAVAILABLE) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not generate overview: {exc}") from exc
    return {"bullets": bullets}


@ai_router.post("/materials/{material_id}/ai/conclusion")
def ai_conclusion(
    material_id: str,
    body: SpecialSlideBody,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Conclusion bullets summarising findings across the report's questions."""
    try:
        df, model, label = _load_df_model_labeled(material_id, client)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not load material: {exc}") from exc

    refs = body.question_refs or [q.qid for q in model.questions]
    findings = _findings_for_refs(refs, df, model)
    if not findings:
        return {"bullets": []}  # nothing computable to conclude from
    try:
        bullets = generate_conclusion_bullets(label, findings, chat=egohive_chat)
    except EgoHiveError as exc:
        raise HTTPException(status_code=503, detail=_AI_UNAVAILABLE) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not generate conclusion: {exc}") from exc
    return {"bullets": bullets}


@ai_router.post("/materials/{material_id}/ai/demographics")
def ai_demographics(
    material_id: str,
    body: SpecialSlideBody,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Pick demographic questions and write 'about the respondents' bullets.

    Returns {"bullets": [...], "question_refs": [...]} where question_refs are the
    LLM-selected demographic questions (validated against the model).
    """
    try:
        df, model, label = _load_df_model_labeled(material_id, client)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not load material: {exc}") from exc

    try:
        candidates = [(q.qid, q.text) for q in model.questions]
        picked = pick_demographic_questions(candidates, chat=egohive_chat)
        findings = _findings_for_refs(picked, df, model)
        bullets = generate_demographics_bullets(label, findings, chat=egohive_chat) if findings else []
    except EgoHiveError as exc:
        raise HTTPException(status_code=503, detail=_AI_UNAVAILABLE) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not generate demographics: {exc}") from exc

    # A suggested chart type per picked demographic question (for the grid cells).
    from reportbuilder.render.plugins import suggest_chart_type

    charts = []
    for ref in picked:
        try:
            q = model.question(ref)
            series = compute(q, _kind_spec(q, model), df, model)
            ct = suggest_chart_type(q, series)
            if ct == "wordcloud":  # demographics aren't text, but guard
                ct = "vertical_bar"
            charts.append({"question_ref": ref, "chart_type": ct})
        except Exception:
            charts.append({"question_ref": ref, "chart_type": "vertical_bar"})
    return {"bullets": bullets, "question_refs": picked, "charts": charts}


__all__ = ["ai_router"]
