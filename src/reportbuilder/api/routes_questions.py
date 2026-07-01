"""Questions routes: GET /materials/{material_id}/questions (browse),
GET /materials/{material_id}/variables (variable labels for classifying-var pickers),
PUT /materials/{material_id}/grouping (stateless preview),
POST /materials/{material_id}/preview-chart (single-chart PNG thumbnail).
(REQ-C-05, REQ-C-06, REQ-C-13, REQ-C-19, REQ-D-06, M-02, RX-be.1, RX-be.2, RX-be.3)"""
from __future__ import annotations

import hashlib
import os
import pathlib
import re
import shutil
import tempfile
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from reportbuilder.api.deps import get_client
from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.preview import rasterize_pages
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.ingest.grouping_override import apply_grouping_override
from reportbuilder.api.model_loader import (
    model_for_material,
    df_model_for_material,
)
from reportbuilder.ingest.sav_reader import read_sav, _is_metadata
from reportbuilder.model.question import QuestionModel
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
)
from reportbuilder.render.plugins import CHART_PLUGINS, suggest_chart_type
from reportbuilder.stats.engine import compute
from reportbuilder.stats.series import Cell, SeriesResult
from reportbuilder.store.datahive_client import DataHiveClient


questions_router = APIRouter()


@questions_router.get("/chart-types")
def list_chart_types() -> dict:
    """Chart-type catalog with each type's declarative config schema.

    The frontend renders the per-chart configuration form purely from this
    schema (via a widget registry), so a new chart type — even one with a new
    config option — adds its plugin + schema field and needs no frontend change.
    Material-independent; safe to fetch once. (REQ-C-13, REQ-C-30)
    """
    return {
        "chart_types": [
            {
                "id": p.id,
                "label": p.label,
                "requires": list(p.requires),
                "config": [f.to_dict() for f in p.config_schema],
            }
            for p in CHART_PLUGINS.values()
        ]
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _quick_series(question, model: QuestionModel) -> SeriesResult:
    """Build a minimal SeriesResult from the question's value-label shape.

    Used exclusively by suggest_chart_type so no real survey data is needed.
    For single questions: categories come from non-missing value labels.
    For multi questions: categories are the member-variable labels.
    (REQ-C-13)
    """
    # multi + battery: one category per member variable (its rewritten label).
    if question.kind in ("multi", "battery"):
        cats = tuple(model.variables[v].label for v in question.variables)
    else:
        var = model.variables[question.variables[0]]
        cats = tuple(
            vl.label
            for vl in var.value_labels
            if vl.value not in var.missing_values
        )
        if not cats:
            cats = ("A", "B", "C")  # fallback: no value labels defined

    # A battery reports a mean per member (not a part-of-whole %), so its
    # synthetic shape uses the mean statistic — keeps pie/doughnut out and
    # picks a bar default.
    is_battery = question.kind == "battery"
    segments = ("Total",)
    cells: dict[tuple[str, str], Cell] = {
        (cat, "Total"): Cell(pct=None if is_battery else 50.0, count=10.0,
                             mean=3.0 if is_battery else None)
        for cat in cats
    }
    return SeriesResult(
        categories=cats,
        segments=segments,
        cells=cells,
        base_n={"Total": len(cats) * 10},
        statistic="mean" if is_battery else "pct",
    )


def _is_text_question(model: QuestionModel, q) -> bool:
    """True when all of the question's variables are open-ended free text (Task J.3)."""
    qvars = [model.variables[v] for v in q.variables]
    return bool(qvars) and all(v.measurement == "text" for v in qvars)


def _text_is_short(df, q, *, max_words: float = 2.0) -> bool:
    """True when an open-ended question's answers are SHORT (association lists like
    brand names or "describe in three words") → best shown as a word cloud rather
    than AI-summarised themes. Measured by the median word count of non-empty
    answers, which is robust to a few long outliers."""
    try:
        import statistics
        col = q.variables[0]
        if col not in df.columns:
            return False
        counts = []
        for x in df[col].dropna().tolist():
            s = str(x).strip()
            if s and s.lower() not in ("nan", "none"):
                counts.append(len(s.split()))
        if len(counts) < 5:
            return False
        return statistics.median(counts) <= max_words
    except Exception:
        return False


def _aggregatable(var) -> bool:
    """True when a per-category MEAN of this variable is meaningful — a numeric
    scale, or a rating whose value labels start with a digit (1..N). Used to
    offer valid secondary variables for a combo line."""
    import re as _re
    if var.measurement == "text":
        return False
    if var.measurement == "scale" and not var.value_labels:
        return True
    vls = var.value_labels
    if not vls:
        return var.measurement == "scale"
    digit = sum(1 for vl in vls if _re.match(r"^\s*\d", vl.label or ""))
    return digit >= max(1, int(len(vls) * 0.6))


def _is_likert_scale(var) -> bool:
    """A 1..N Likert rating item (labels are mostly sequential digits starting at
    1, e.g. '1=Täysin eri mieltä' … '7=Täysin samaa mieltä').

    Such items are what a survey MEASURES, not how respondents are segmented — so
    they must be excluded from the classifying-variable picker. This is distinct
    from bracket categoricals (age '18–24', spend '500–999 €') whose leading
    numbers are NOT a 1..N sequence and which ARE valid segmenters."""
    import re as _re
    pts: list[int] = []
    for vl in var.value_labels:
        m = _re.match(r"^\s*(\d+)", vl.label or "")
        if m:
            pts.append(int(m.group(1)))
    if len(pts) < max(3, len(var.value_labels) - 1):
        return False  # not mostly-numeric → not a Likert scale
    uniq = sorted(set(pts))
    return uniq[0] == 1 and uniq == list(range(1, len(uniq) + 1)) and uniq[-1] <= 11


def _segmentable(var) -> bool:
    """True when a variable is a MEANINGFUL classifying/segmentation variable.

    A low-cardinality categorical that is background/demographic (age, region,
    ownership tier, branch, …) — NOT a Likert rating item (measured, not used to
    segment) and not a high-cardinality single-choice question. This keeps the
    'Classifying variable' picker to the handful of variables an analyst would
    actually cross-tabulate by, instead of every categorical in the file."""
    if var.measurement != "categorical":
        return False
    nv = len(var.value_labels)
    if not (2 <= nv <= 10):
        return False
    return not _is_likert_scale(var)


def _has_real_category_labels(var) -> bool:
    """True when a variable's value labels are substantive category names (e.g.
    'enemmistöomistajat', 'Branch A') rather than generic flags (TRUE/FALSE/EMPTY)
    — used to keep analyst segment recodes (whose NAME looks like paradata) in the
    classifying-variable picker while still dropping bare binary URL flags."""
    generic = {"true", "false", "empty", "yes", "no", "kyllä", "ei", "-", "—", ""}
    named = [
        lbl for vl in var.value_labels
        if (lbl := (vl.label or "").strip())
        and any(ch.isalpha() for ch in lbl)
        and lbl.lower() not in generic
    ]
    return len(named) >= 2


def _is_binary_flag(var, df) -> bool:
    """True for a derived BINARY SEGMENT FLAG: an unlabeled categorical column
    (label == name, no value labels) whose data is 0/1 membership — e.g. Attendo's
    "Suosittelijat", "Kokemusta", "Ammattilainen". These are the overlapping
    respondent segments an analyst cross-tabs by; offered as classifiers and
    labelled (flag name vs "Muut") by the engine's segment relabeller."""
    if df is None or var.measurement != "categorical" or var.value_labels:
        return False
    if (var.label or "").strip() != var.name or var.name not in getattr(df, "columns", []):
        return False
    try:
        import pandas as pd
        vals = set(pd.to_numeric(df[var.name], errors="coerce").dropna().unique().tolist())
    except Exception:
        return False
    return bool(vals) and vals <= {0.0, 1.0} and 1.0 in vals and 0.0 in vals


# Respondent-background concepts a demographic question asks about. Matched on the
# question label so demographics (who the respondent IS) can be floated to the
# front of a deck — distinct from opinion/brand questions (what they THINK), which
# can look structurally identical (a low-cardinality single-choice). Finnish + EN.
_DEMOGRAPHIC_RE = re.compile(
    r"\b("
    r"ik[äa]|ik[äa]inen|vuotias|syntym|age|"                      # age
    r"sukupuoli|identifioit|mies\b|nais|gender|"                  # gender
    r"asu[ity]|asuinpaikk|asuinalue|maakun|kaupungi|postinumero|" # region/location
    r"miss[äa]\s+p[äa]in|alue|seutu|region|location|area|"
    r"tulot|tulota|ansio|bruttotul|income|"                       # income
    r"koulutus|education|"                                        # education
    r"kotitalou|asuntokun|household|"                             # household (specific:
    r"montako\s+.*taloud|taloutee?si\s+kuulu|"                    #   avoid generic perhe/lapsi
    r"ty[öo]tilan|occupation|employment|siviilis[äa]"             # occupation / marital
    r")", re.IGNORECASE,
)


def _is_demographic(model: QuestionModel, q) -> bool:
    """True for a respondent-BACKGROUND question (age/gender/region/income/…): a
    single-choice low-cardinality categorical whose label names a demographic
    concept. Used to float demographics to the front of a report."""
    if q.kind != "single":
        return False
    try:
        var = model.variable(q.variables[0])
    except Exception:
        return False
    if var.measurement != "categorical" or not (2 <= len(var.value_labels) <= 15):
        return False
    return bool(_DEMOGRAPHIC_RE.search(q.text or "")) or bool(_DEMOGRAPHIC_RE.search(var.label or ""))


def _question_chartable(model: QuestionModel, q) -> tuple[bool, str | None]:
    """Whether a question can be charted, plus a reason when it cannot (Task J.3).

    Open-ended free-text questions are now chartable — as a *word cloud only*
    (see the questions route, which wires their suggested/compatible types). A
    question is only non-chartable when it has no variables at all.
    """
    if not q.variables:
        return False, "No variables"
    return True, None


def _compatible_chart_types(question, series: SeriesResult) -> list[str]:
    """Chart-type ids whose plugin suitability is not None for this shape (Task G.2).

    Reuses the same plugin suitability scorers that drive suggested_chart_type, so
    the UI can gray out incompatible types (e.g. pie/doughnut for multi-response,
    scatter which is opt-in). Order follows plugin registration order.
    """
    out: list[str] = []
    for cid, p in CHART_PLUGINS.items():
        try:
            if p.suitability(question, series) is not None:
                out.append(cid)
        except Exception:
            # A scorer that errors on this shape is simply not offered.
            continue
    return out


def _missing_value_list(model: QuestionModel, qid: str) -> list[dict]:
    """Return the missing-value mapping for a question as a list of dicts.

    Each entry has ``{"code": float, "label": str}``.  Empty list when none.
    (REQ-D-06)
    """
    try:
        pairs = model.missing_value_labels(qid)
    except (KeyError, IndexError):
        return []
    return [{"code": code, "label": label} for code, label in pairs]


def _value_list(model: QuestionModel, q) -> list[dict]:
    """All defined value labels (incl. missing) of the question's representative variable.

    Single questions: every value label of the primary variable as {code, label} so the
    not-answered picker can show and uncheck them. Multi questions: empty list (the member
    dichotomies are 0/1 tick boxes — no meaningful value codes to fold). (REQ-D-06)
    """
    if q.kind in ("multi", "battery"):
        return []
    var = model.variables[q.variables[0]]
    return [{"code": vl.value, "label": vl.label} for vl in var.value_labels]


def _category_labels(model: QuestionModel, q) -> list[str]:
    """Base category label strings in render order (the label-override editor's list).

    Single: non-missing value labels of the primary variable. Multi: member-variable labels.
    """
    if q.kind in ("multi", "battery"):
        return [model.variables[v].label for v in q.variables]
    var = model.variables[q.variables[0]]
    return [vl.label for vl in var.value_labels if vl.value not in var.missing_values]


def _load_singles(material_id: str, client: DataHiveClient) -> QuestionModel:
    """Fetch the material's raw bytes from the store and return the QuestionModel as produced
    directly by read_sav (all single questions, no auto-grouping). Used by the stateless grouping
    endpoint so it can apply user-requested grouping from a clean slate."""
    raw = client.get_material(material_id)
    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        _df, model = read_sav(tmp_path)
    finally:
        os.unlink(tmp_path)
    return model


def load_model_for_material(material_id: str, client: DataHiveClient) -> QuestionModel:
    """Build the material's QuestionModel with auto-detection AND any manual
    grouping override applied (the single seam — see api.model_loader). (REQ-C-05)"""
    return model_for_material(material_id, client)


def _load_df_model(material_id: str, client: DataHiveClient):
    """Like load_model_for_material but also returns the DataFrame (for stats)."""
    return df_model_for_material(material_id, client)


def _question_measurement(model: QuestionModel, q) -> str:
    """Overall measurement label for a question: 'multi', 'text', or the primary
    variable's measurement (categorical/scale)."""
    if q.kind == "multi":
        return "multi"
    if q.kind == "battery":
        return "rating battery"
    var = model.variables[q.variables[0]]
    return var.measurement or "categorical"


def _summary_spec(qid: str) -> ChartSpec:
    """Minimal spec to compute a question's overall distribution."""
    return ChartSpec(
        question_ref=qid, chart_type="horizontal_bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="summary",
        elements=ElementToggles(), show_not_answered=False,
        show_empty_categories=True,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@questions_router.get("/materials/{material_id}/questions")
def list_questions(
    material_id: str,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Browse all questions for a material. Auto-detected multi groups are pre-applied so qids are
    render-resolvable. Each question includes a suggested chart type (REQ-C-13) and the
    missing-value mapping (REQ-D-06). (REQ-C-05)"""
    model = load_model_for_material(material_id, client)
    return {"questions": _questions_payload(model, material_id, client)}


def _questions_payload(model: QuestionModel, material_id: str, client) -> list[dict]:
    """Build the browse-questions payload for a (possibly regrouped) model."""
    # The short-answer word-cloud heuristic needs the data; load it lazily and
    # only once, and tolerate failure (e.g. a model-only mock in tests) by
    # degrading to themes. (Grouping doesn't change the raw DataFrame columns.)
    _df_box: dict = {}

    def _df_or_none():
        if "df" not in _df_box:
            try:
                _df_box["df"], _ = _load_df_model(material_id, client)
            except Exception:
                _df_box["df"] = None
        return _df_box["df"]

    questions = []
    for q in model.questions:
        chartable, reason = _question_chartable(model, q)
        if not chartable:
            suggested = None
            compatible = []
        elif _is_text_question(model, q):
            # Open-ended text: SHORT answers (brand names, "describe in 3 words")
            # are association lists → a WORD CLOUD (as the source decks do); longer
            # answers (opinions / suggestions) → AI-summarised themes. Both remain
            # available, ordered with the suggested one first.
            df = _df_or_none()
            if df is not None and _text_is_short(df, q):
                suggested = "wordcloud"
                compatible = ["wordcloud", "themes"]
            else:
                suggested = "themes"
                compatible = ["themes", "wordcloud"]
        else:
            series = _quick_series(q, model)
            suggested = suggest_chart_type(q, series)
            # Non-text questions never offer wordcloud (its suitability is None).
            compatible = _compatible_chart_types(q, series)
        questions.append({
            "qid": q.qid,
            "kind": q.kind,
            "variables": list(q.variables),
            "text": q.text,
            "chartable": chartable,
            "non_chartable_reason": reason,
            "suggested_chart_type": suggested,
            "compatible_chart_types": compatible,
            "missing_values": _missing_value_list(model, q.qid),
            "values": _value_list(model, q),
            "category_labels": _category_labels(model, q),
            # Respondent-background question (age/gender/region/…) → floated to
            # the front of a new report (demographics-first convention).
            "is_demographic": _is_demographic(model, q),
        })
    return questions


@questions_router.get("/materials/{material_id}/questions/{qid}/summary")
def question_summary(
    material_id: str,
    qid: str,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Rich detail for one question: full metadata + the computed response
    distribution (counts, %, base N) and mean for scale questions. Stats failures
    degrade to nulls (never a 500); a genuinely unknown qid is a 404."""
    df, model = _load_df_model(material_id, client)
    try:
        q = model.question(qid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Question '{qid}' not found") from exc

    chartable, reason = _question_chartable(model, q)
    is_text = _is_text_question(model, q)
    out: dict = {
        "qid": q.qid,
        "kind": q.kind,
        "text": q.text,
        "measurement": "text" if is_text else _question_measurement(model, q),
        "variables": [
            {
                "name": v,
                "label": model.variables[v].label,
                "measurement": model.variables[v].measurement,
            }
            for v in q.variables
        ],
        "value_labels": _value_list(model, q),
        "missing_values": _missing_value_list(model, q.qid),
        "category_labels": _category_labels(model, q),
        "chartable": chartable,
        "non_chartable_reason": reason,
        "respondent_total": int(len(df)),
        "base_n": None,
        "statistic": "pct",
        "distribution": None,
        "mean": None,
    }

    if not chartable or is_text:
        return out

    # Computed distribution (count + pct per category) + base N.
    try:
        series = compute(q, _summary_spec(q.qid), df, model)
        seg = series.segments[0] if series.segments else "Total"
        out["base_n"] = series.base_n.get(seg)
        out["statistic"] = series.statistic  # "pct" | "mean" (battery)
        dist = []
        for cat in series.categories:
            cell = series.cells.get((cat, seg))
            if cell is None:
                continue
            dist.append({
                "category": cat,
                "count": cell.count,
                "pct": cell.pct,
                "mean": cell.mean,
            })
        out["distribution"] = dist
        out["suggested_chart_type"] = suggest_chart_type(q, series)
        out["compatible_chart_types"] = _compatible_chart_types(q, series)
    except Exception:
        # Stats are best-effort; metadata above is always returned.
        pass

    # Mean for a single scale variable (excluding user-missing + sysmis).
    if q.kind == "single" and _question_measurement(model, q) == "scale":
        try:
            import pandas as pd  # local import; pandas already loaded via ingest
            var = model.variables[q.variables[0]]
            s = pd.to_numeric(df[var.name], errors="coerce")
            s = s[~s.isin(list(var.missing_values))]
            if s.notna().any():
                out["mean"] = float(s.mean())
        except Exception:
            pass

    return out


@questions_router.get("/materials/{material_id}/variables")
def list_variables(
    material_id: str,
    include_all: bool = False,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """List all variables for a material with display labels and measurement.

    Returns name, a display label (the variable's SPSS label if set, else the raw name),
    and measurement (categorical/scale). Sorted categorical-first so the classifying-variable
    picker groups them sensibly. (RX-be.1)
    """
    model = load_model_for_material(material_id, client)
    # The binary-segment-flag detector needs the data; load it lazily and tolerate
    # absence (model-only mocks) by skipping flag detection.
    _df_box: dict = {}

    def _df_or_none():
        if "df" not in _df_box:
            try:
                _df_box["df"], _ = _load_df_model(material_id, client)
            except Exception:
                _df_box["df"] = None
        return _df_box["df"]

    # Exclude variables that are members of a grouped question (multi/battery) —
    # those are sub-options/rating cells, not standalone segmentation variables.
    grouped = {
        v for q in model.questions if q.kind in ("multi", "battery") for v in q.variables
    }
    # Survey-platform paradata (IP address, Survey timer, URL captures, …) is kept
    # in the variables dict but must not be offered as a segmentation variable —
    # EXCEPT analyst-derived segment recodes (e.g. URLprofiilinew =
    # enemmistöomistajat/prosenttiomistajat/vierailijat, LinkName, Branch) which
    # carry a cryptic platform NAME but real category labels. Those are exactly
    # the classifiers an analyst cross-tabulates by, so keep them when they are a
    # genuine segment (substantive labels, not TRUE/FALSE flags).
    def _keep(v) -> bool:
        if v.name in grouped:
            return False
        if include_all:
            # Grouping's "show all": reveal otherwise-hidden paradata/helper vars
            # (still excluding current group members).
            return True
        if not _is_metadata(v.name, v.label or v.name):
            return True
        return _segmentable(v) and _has_real_category_labels(v)

    all_vars = [v for v in model.variables.values() if _keep(v)]
    # Stable sort: categorical before scale; original file order within each tier.
    all_vars.sort(key=lambda v: (0 if v.measurement == "categorical" else 1))
    return {
        "variables": [
            {
                "name": var.name,
                # label is already the human-readable label (falls back to name in read_sav
                # when no SPSS label is set), so we expose it directly.
                "label": var.label,
                "measurement": var.measurement,
                # Number of value labels — lets the UI offer only low-cardinality
                # categoricals as classifying (segmentation) variables.
                "n_values": len(var.value_labels),
                # Can a per-category MEAN be taken (numeric scale, or a rating whose
                # value labels start with a digit) — i.e. a valid combo secondary.
                "aggregatable": _aggregatable(var),
                # Is this a MEANINGFUL classifying/segmentation variable — a
                # background/demographic categorical (not a Likert item), OR a
                # derived binary SEGMENT FLAG (e.g. "Suosittelijat", "Kokemusta":
                # 0/1 membership the analyst cross-tabs by). Drives the
                # classifying-variable picker.
                "segmentable": _segmentable(var) or _is_binary_flag(var, _df_or_none()),
            }
            for var in all_vars
        ]
    }


class GroupSpec(BaseModel):
    """One manual group in the override. `battery` is reserved for Phase 2."""
    kind: Literal["multi", "battery"] = "multi"
    variables: list[str]
    label: str | None = None


class GroupingOverride(BaseModel):
    """PUT /materials/{material_id}/grouping body — the persisted grouping override."""
    groups: list[GroupSpec] = []
    singles: list[str] = []


def _validate_override(base: QuestionModel, body: GroupingOverride) -> dict:
    """Validate + normalise a grouping override → a plain dict for persistence.

    Each `multi` group needs ≥2 known, non-scale variables; a variable may belong
    to at most one group; a group member is dropped from `singles` (a group wins
    over a forced-single). `battery` groups are accepted but not validated here
    (Phase 2). Raises HTTP 422 on violations. (REQ-C-06, M-02)
    """
    seen: set[str] = set()
    for g in body.groups:
        if g.kind != "multi":
            continue
        vs = g.variables
        if len(vs) < 2:
            raise HTTPException(422, f"A multi group needs at least 2 variables; got {vs}.")
        unknown = [v for v in vs if v not in base.variables]
        if unknown:
            raise HTTPException(422, f"Unknown variable(s) {unknown} — not in the material.")
        scale = [v for v in vs if base.variables[v].measurement == "scale"]
        if scale:
            raise HTTPException(
                422,
                f"Scale variable(s) {scale} cannot be in a multi group — members must "
                "be binary/categorical tick-box variables.",
            )
        dup = [v for v in vs if v in seen]
        if dup:
            raise HTTPException(422, f"Variable(s) {dup} assigned to more than one group.")
        seen.update(vs)
    groups = [
        {"kind": g.kind, "variables": list(g.variables), **({"label": g.label} if g.label else {})}
        for g in body.groups
    ]
    singles = [v for v in body.singles if v not in seen]
    return {"groups": groups, "singles": singles}


@questions_router.post("/materials/{material_id}/regroup")
def regroup(
    material_id: str,
    body: GroupingOverride,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Stateless PREVIEW: validate a grouping override and return the reshaped
    question list (full browse payload) without persisting. The report wizard
    calls this live as the user edits a report's grouping; the override itself is
    saved WITH the report. (REQ-C-06, M-02)"""
    base = _load_singles(material_id, client)
    normalised = _validate_override(base, body)
    model = apply_grouping_override(base, normalised)
    return {"questions": _questions_payload(model, material_id, client)}


# ---------------------------------------------------------------------------
# W1.2 — Single-chart live-preview endpoint (REQ-C-19, REQ-C-13)
# ---------------------------------------------------------------------------


class _NumberFormatBody(BaseModel):
    mode: str = "auto"
    pct_decimals: int = 0
    mean_decimals: int = 1
    count_round_up: bool = False
    show_pct_sign: bool = True


class _SortSpecBody(BaseModel):
    basis: str = "data_order"
    topbox_codes: list[float] = []
    descending: bool = True


class _ElementTogglesBody(BaseModel):
    title: bool = True
    legend: bool = True
    n: bool = True
    axis_names: bool = True
    filter_var: bool = True
    data_labels: bool = True


class ChartSpecBody(BaseModel):
    """Request body for POST /materials/{material_id}/preview-chart.

    Mirrors ChartSpec fields.  ``template_slot`` defaults to "preview" because
    the wizard doesn't assign slots; the preview always renders a single blank slide.
    (REQ-C-05, REQ-C-13, REQ-C-19, REQ-D-06)
    """

    question_ref: str
    chart_type: str
    statistic: str = "pct"
    classifying_var: str | None = None
    number_format: _NumberFormatBody = _NumberFormatBody()
    sort: _SortSpecBody = _SortSpecBody()
    elements: _ElementTogglesBody = _ElementTogglesBody()
    scatter_xy: list[str] | None = None
    show_not_answered: bool = False
    show_empty_categories: bool = True
    not_answered_codes: list[float] | None = None
    category_label_overrides: list[tuple[str, str]] = []
    # The live preview must show the same headline as the rendered deck: when an
    # AI/edited slide title is set, the preview uses it instead of the question text.
    slide_title: str | None = None
    slide_description: str | None = None
    # Preview-only: when False the rendered PNG omits the title block (accent bar +
    # title + description) so the frontend can own that region with a progressive
    # "Generating title…" placeholder. Does NOT affect the persisted chart / deck.
    render_title: bool = True
    # Free-form per-chart-type options (plugin-declared config keys). Carries
    # special-slide bullet content (options["bullets"]); part of the cache key via
    # model_dump_json so editing bullets re-renders.
    options: dict[str, Any] = {}
    # The report's grouping override, so a preview of a chart on a manually-grouped
    # question resolves the same way the rendered deck will. Absent = auto-detect.
    grouping: dict[str, Any] | None = None


def _chart_spec_from_body(body: ChartSpecBody) -> ChartSpec:
    """Convert the Pydantic request body to a ChartSpec dataclass."""
    return ChartSpec(
        question_ref=body.question_ref,
        chart_type=body.chart_type,
        statistic=body.statistic,
        classifying_var=body.classifying_var,
        number_format=NumberFormat(
            mode=body.number_format.mode,
            pct_decimals=body.number_format.pct_decimals,
            mean_decimals=body.number_format.mean_decimals,
            count_round_up=body.number_format.count_round_up,
            show_pct_sign=body.number_format.show_pct_sign,
        ),
        sort=SortSpec(
            basis=body.sort.basis,
            topbox_codes=tuple(body.sort.topbox_codes),
            descending=body.sort.descending,
        ),
        template_slot="preview",
        elements=ElementToggles(
            # render_title=False omits the baked title block for the live preview.
            title=body.elements.title and body.render_title,
            legend=body.elements.legend,
            n=body.elements.n,
            axis_names=body.elements.axis_names,
            filter_var=body.elements.filter_var,
            data_labels=body.elements.data_labels,
        ),
        scatter_xy=tuple(body.scatter_xy) if body.scatter_xy is not None else None,
        show_not_answered=body.show_not_answered,
        show_empty_categories=body.show_empty_categories,
        not_answered_codes=(
            tuple(float(c) for c in body.not_answered_codes)
            if body.not_answered_codes is not None
            else None
        ),
        category_label_overrides=tuple(
            (str(full), str(short)) for full, short in body.category_label_overrides
        ),
        slide_title=body.slide_title,
        slide_description=body.slide_description,
        options=dict(body.options or {}),
    )


# Per-process cache salt: the in-memory store resets material ids (mat-1, mat-2…)
# on restart, so a cache keyed only on (material_id, spec) would serve images
# rendered by a PREVIOUS process — i.e. stale, pre-code-change renders. Salting
# the key per process makes every server start use a fresh preview namespace.
_PREVIEW_CACHE_SALT = uuid.uuid4().hex[:8]


def _preview_out_dir(material_id: str, spec_json: str) -> pathlib.Path:
    """Return a per-(process, material, spec) temp directory for preview artifacts."""
    key = hashlib.md5(
        f"{_PREVIEW_CACHE_SALT}:{material_id}:{spec_json}".encode()
    ).hexdigest()[:16]
    d = pathlib.Path(tempfile.gettempdir()) / "nsight-preview" / key
    d.mkdir(parents=True, exist_ok=True)
    return d


@questions_router.post("/materials/{material_id}/preview-chart")
def preview_chart(
    material_id: str,
    body: ChartSpecBody,
    client: DataHiveClient = Depends(get_client),
) -> Response:
    """Render a single ChartSpec as a PNG thumbnail for the wizard's live preview.

    Implementation: loads the material, builds a 1-ChartSpec image-mode Report,
    calls build_pptx → pptx_to_pdf → rasterize page 1 → returns PNG bytes.
    Requires LibreOffice (soffice) on PATH; returns 503 if absent.
    The entire render chain is wrapped so ANY failure returns a clean 422 with a
    short reason — never a 500 or a dropped connection.
    (REQ-C-05, REQ-C-13, REQ-C-19, REQ-D-06, RX-be.2, RX-be.3)
    """
    # Guard: LibreOffice required for PDF conversion
    if shutil.which("soffice") is None and shutil.which("libreoffice") is None:
        raise HTTPException(
            status_code=503,
            detail="LibreOffice (soffice) is not available; chart preview requires it.",
        )

    # Guard (RX-be.2): scatter requires explicit X and Y variables
    if body.chart_type == "scatter" and not body.scatter_xy:
        raise HTTPException(
            status_code=422,
            detail="scatter: Scatter needs an X and Y variable (scatter_xy)",
        )

    # 0. Cache hit: the deterministic per-(process, material, spec) dir already
    #    holds this exact render → return it without regenerating. The image is
    #    formed ONCE and reused; the per-process salt invalidates it on restart
    #    (so code changes never serve a stale render). Only a changed spec (or a
    #    new process) does the full build_pptx → PDF → rasterize chain below.
    out_dir = _preview_out_dir(material_id, body.model_dump_json())
    cached_png = out_dir / "preview.png"
    if cached_png.exists():
        return Response(content=cached_png.read_bytes(), media_type="image/png")

    # 1. Load material data
    raw = client.get_material(material_id)
    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        df, model = read_sav(tmp_path)
    finally:
        os.unlink(tmp_path)

    model = apply_grouping_override(model, body.grouping or {})

    # A stacked chart with no classifying variable is a valid single 100%-stacked
    # distribution bar (the "total-only" case) — it renders the answer categories
    # as the stack, so no classifying-variable guard is needed.

    # 2. Convert request body to ChartSpec
    spec = _chart_spec_from_body(body)

    # 3. Wrap in a 1-chart image-mode Report
    report = Report(
        name="preview",
        render_mode="image",
        template_ref="",
        charts=(spec,),
    )

    # 4. Render PPTX → PDF → PNG page 1, using UNIQUE work files + a per-render
    #    pages subdir so two concurrent identical requests can't tear each other's
    #    artifacts. The cached preview.png is published ATOMICALLY (os.replace),
    #    so the cache-hit branch above never reads a half-written file. (RX-be.2,
    #    concurrency)
    uid = uuid.uuid4().hex[:8]
    pptx_path = str(out_dir / f"preview.{uid}.pptx")
    try:
        build_pptx(report, model, df, pptx_path)
        pdf_path = pptx_to_pdf(pptx_path, str(out_dir))
        # Previews are shown at ~640px (big pane) / smaller (thumbs), so 110 DPI
        # is ample and ~40% lighter than deck DPI — smaller PNGs decode faster
        # and use less memory across 100+ cached previews.
        pngs = rasterize_pages(pdf_path, str(out_dir / f"pages-{uid}"), dpi=110)
    except HTTPException:
        raise  # already a well-formed HTTP error — pass through unchanged
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{body.chart_type}: {exc}",
        ) from exc

    if not pngs:
        raise HTTPException(
            status_code=422,
            detail=f"{body.chart_type}: Rasterization produced no pages.",
        )

    png_bytes = pathlib.Path(pngs[0]).read_bytes()
    # Atomically publish the cached PNG: write to a temp file in the same dir,
    # then os.replace so concurrent readers see a complete file.
    tmp_png = out_dir / f"preview.{uid}.png"
    tmp_png.write_bytes(png_bytes)
    os.replace(tmp_png, cached_png)
    return Response(content=png_bytes, media_type="image/png")
