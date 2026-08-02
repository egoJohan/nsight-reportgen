"""SAV reader — Task 2.1/2.2/2.3: variables, labels, value labels, measurement, missing codes, single questions.

A0.1 — Metadata curation (REQ-C-05): survey-platform system variables (Response ID,
IP Address, dates, session/contact ids, pid/psid, etc.) are excluded from `questions`
but kept in `variables` so downstream code can still access them by name.
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pyreadstat

from reportbuilder.model.question import QuestionModel, Question, Variable, ValueLabel


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or name.lower()


def _measurement(spss_measure: str) -> str:
    return "scale" if (spss_measure or "").lower() == "scale" else "categorical"


# A coded string column (few short values, each repeated many times) is a
# CATEGORICAL, not an open-ended answer — e.g. a packaging study's path column
# holding "Pakkausilme 1"/"Pakkausilme 2". `ratio` is the discriminator: a genuine
# open-end has roughly one row per distinct value even when few people answered
# ("Muu, mikä?" -> 5 distinct, 5 answers), while a coded category is repeated
# across the sample. `maxlen` is only a guard against pathological repeated
# boilerplate — a sweep over maxlen 20..120 x ratio 5..20 across 147 real text
# variables gave an identical outcome in every cell, so the rule rests on
# `distinct` and `ratio`. (spec 2026-08-02 §1.1)
_CODED_MAX_DISTINCT = 12
_CODED_MIN_RATIO = 10.0
_CODED_MAX_LEN = 80


def _is_coded_string(series: pd.Series) -> bool:
    """True when a label-less string column looks like a coded categorical."""
    nn = series.dropna().astype(str)
    nn = nn[nn.str.strip() != ""]
    if len(nn) == 0:
        return False
    distinct = nn.nunique()
    if distinct == 0 or distinct > _CODED_MAX_DISTINCT:
        return False
    if int(nn.str.len().max()) > _CODED_MAX_LEN:
        return False
    return (len(nn) / distinct) >= _CODED_MIN_RATIO


def _is_text_variable(series: pd.Series, value_labels: tuple) -> bool:
    """Detect open-ended free-text variables (Task G.1).

    A variable is open-ended text when it has NO usable numeric value labels AND
    the bulk of its non-null values are not coercible to numbers (e.g. free-text
    answers like "Alzheimer potilas"). Such variables have no chartable numeric
    basis and must be flagged non-chartable rather than crashing the renderer.

    A coded STRING categorical is excluded — see `_is_coded_string`. A column with
    no non-blank answers stays text (and so non-chartable), which is safer than a
    categorical with no categories.
    """
    if value_labels:
        return False  # coded categorical — has a numeric basis
    nn = series.dropna()
    if len(nn) == 0:
        return False
    coerced = pd.to_numeric(nn, errors="coerce")
    if float(coerced.isna().mean()) <= 0.5:
        return False
    return not _is_coded_string(nn)


def _user_missing(ranges: list | None) -> frozenset[float]:
    codes: set[float] = set()
    for r in ranges or []:
        lo, hi = (r["lo"], r["hi"]) if isinstance(r, dict) else (r[0], r[1])
        lo, hi = float(lo), float(hi)
        if lo == hi:
            codes.add(lo)
        else:
            codes.update(float(c) for c in range(int(lo), int(hi) + 1))
    return frozenset(codes)


# ---------------------------------------------------------------------------
# A0.1 — Metadata / system-variable detection (REQ-C-05)
# ---------------------------------------------------------------------------

# Known survey-platform system variable names (case-insensitive exact match).
# Extend this list when new platform exports are onboarded.
_METADATA_NAMES: frozenset[str] = frozenset({
    # SmartSurvey / generic V-prefixed system fields
    "vrid",
    "vdatesub",
    "vstatus",
    "vcid",
    "vsessionid",
    "vip",
    "vlong",
    "vlat",
    "vgeocountry",
    "vgeocity",
    "vgeoregion",
    "vpostal",
    "vcomment",
    "vreferer",
    "vuseragent",
    "vlanguage",
})

# Exact label strings (case-insensitive, stripped) that signal a metadata variable.
# Use exact-label matching to stay conservative — a label like "Employment Status"
# will NOT match the entry "status" because the full string differs.
_METADATA_LABEL_EXACT: frozenset[str] = frozenset({
    "response id",
    "respondent",
    "date submitted",
    "submitted",
    "status",
    "contact id",
    "session id",
    "sessionid",
    "ip address",
    "url",
    "referer",
    "referrer",
    "email",
    "collector",
    "duration",
    "started",
    "ended",
    "timestamp",
    "weight",
    "pid",
    "psid",
    "language",
    "longitude",
    "latitude",
    "user agent",
    "comments",
    "link name",
})

# Exact variable names (case-insensitive) for platform-derived recode/counter
# columns that are not survey questions: branch/quota recodes and the
# per-question choice counter.
_METADATA_NAMES_EXTRA: frozenset[str] = frozenset({
    "branch_numeric",
    "q_nchoices",
    "linkname",
})

# Label *prefixes* (case-insensitive) that signal survey-engine paradata whose
# trailing text varies per export (so they can't be matched exactly):
#   - "URL_…"      URL query-string captures / their numeric recodes
#   - "Hidden value …"  platform hidden fields
#   - "Survey timer", "Answer count", "New Percent Branch …"  paradata/quota
# Prefix (not substring) matching keeps a real question that merely *mentions*
# one of these words from being dropped.
_METADATA_LABEL_PREFIXES: tuple[str, ...] = (
    "url_",
    "hidden value",
    "survey timer",
    "answer count",
    "new percent branch",
)

# Variable-name prefixes for URL-derived recode columns (URLprofiilinew,
# URLregion, URL_Villas_numeric, …). Survey questions use the `var<N>` scheme,
# so a leading "url" never collides with a real question.
_METADATA_NAME_PREFIXES: tuple[str, ...] = (
    "url",
)


def _is_metadata(name: str, label: str) -> bool:
    """Return True if this variable is a survey-platform metadata/system field.

    Checks (all case-insensitive):
    - _METADATA_NAMES / _METADATA_NAMES_EXTRA: known system/recode variable names.
    - _METADATA_NAME_PREFIXES: name prefixes for URL-derived recodes.
    - _METADATA_LABEL_EXACT: exact label strings that identify metadata.
    - _METADATA_LABEL_PREFIXES: label prefixes for paradata with varying suffixes.

    Conservative by design: label matching is exact or prefix-anchored (never a
    loose substring) so real questions (e.g. label "Employment Status", or a
    question that merely mentions a URL) are not accidentally dropped. Analyst
    segmentation variables (binary flags, aggregate ratings) carry real data and
    are intentionally NOT matched here. (REQ-C-05)
    """
    nm = name.lower().strip()
    if nm in _METADATA_NAMES or nm in _METADATA_NAMES_EXTRA:
        return True
    if nm.startswith(_METADATA_NAME_PREFIXES):
        return True
    lbl = label.lower().strip()
    if lbl in _METADATA_LABEL_EXACT:
        return True
    if lbl.startswith(_METADATA_LABEL_PREFIXES):
        return True
    return False


def _is_constant_marker(name: str, var: "Variable", series) -> bool:
    """Return True for a structural/total marker column that is NOT a real
    question: it has no human label (label == variable name), no value labels,
    is not free text, AND carries no information (<= 1 distinct value, i.e. a
    constant or all-empty column — e.g. a "TOTAALI" section divider).

    Deliberately strict so real derived variables (binary flags, aggregate
    ratings, segments) — which have varying data — are never dropped.
    """
    if var.value_labels or var.measurement == "text":
        return False
    if (var.label or "").strip() != name:
        return False
    try:
        return int(series.nunique(dropna=True)) <= 1
    except Exception:
        return False


def _is_unlabeled_helper(name: str, var: "Variable") -> bool:
    """Return True for an unlabeled derived helper/recode column — one with no
    human label (label == variable name) and no value labels. Two flavours:

    - categorical flags/segments (Holiday Club's ``vieralijat``, ``contracts_1``,
      ``VillastaiGold``); and
    - scale RATING aggregates (Attendo's ``MahdHyvänArjen``, ``TarjLaadHoiva``,
      ``Inhimilli`` … — per-attribute recodes that just duplicate a rating
      battery's statements under a cryptic code).

    Both are analyst working columns, NOT survey questions, so they are excluded
    from the question browser. They are NOT removed from the variables dict, so
    they remain available as classifying / combo-secondary variables (nothing is
    lost). Free text (``measurement == "text"``) is untouched — those are real
    open-ended questions.
    """
    if var.value_labels or var.measurement == "text":
        return False
    return (var.label or "").strip() == name


# ---------------------------------------------------------------------------
# Public reader
# ---------------------------------------------------------------------------

def sav_file_label(path: str | pathlib.Path) -> str | None:
    """The SAV's file-level label (the study title embedded in the file), if any.

    Metadata-only read (fast) so it can be used to name a case from the SAV
    itself, falling back to the file name when absent.
    """
    try:
        _df, meta = pyreadstat.read_sav(str(path), metadataonly=True)
    except Exception:
        return None
    label = (getattr(meta, "file_label", None) or "").strip()
    return label or None


def read_sav(path: str | pathlib.Path) -> tuple[pd.DataFrame, QuestionModel]:
    df, meta = pyreadstat.read_sav(str(path), apply_value_formats=False, user_missing=True)
    labels = dict(meta.column_names_to_labels)
    value_labels = dict(meta.variable_value_labels)
    measures = dict(getattr(meta, "variable_measure", {}) or {})
    missing_ranges = dict(getattr(meta, "missing_ranges", {}) or {})

    variables: dict[str, Variable] = {}
    for name in df.columns:
        # Preserve the SAV's value-label DEFINITION order (what pyreadstat returns) —
        # it is the survey's intended display order. Sorting by code destroyed it, so a
        # scale whose codes aren't in scale order (e.g. a 5-point scale later extended
        # with intermediate points as codes 6–8) rendered semantically jumbled under
        # "data order". Digit-labelled rating scales are still re-ordered by their parsed
        # point downstream; this only fixes text-labelled scales.
        vls = tuple(
            ValueLabel(float(code), str(lbl))
            for code, lbl in value_labels.get(name, {}).items()
        )
        measurement = _measurement(measures.get(name, ""))
        # Task G.1: classify open-ended free-text variables as measurement "text"
        # so questions built from them can be flagged non-chartable downstream.
        if _is_text_variable(df[name], vls):
            measurement = "text"
        elif not vls and _is_coded_string(df[name]):
            # A coded STRING column is a categorical whatever the SAV's measure
            # attribute claims — these are often exported as "scale", and a string
            # column has no numeric basis to be a scale on. (spec 2026-08-02 §1.1)
            measurement = "categorical"
        variables[name] = Variable(
            name=name,
            label=labels.get(name) or name,
            measurement=measurement,
            value_labels=vls,
            missing_values=_user_missing(missing_ranges.get(name)),
        )

    # A0.1: build questions from non-metadata variables only. Metadata,
    # constant markers, and unlabeled categorical helper flags remain accessible
    # in `variables` (the latter still usable as classifying variables) but are
    # excluded from `questions` to keep the question browser clean (REQ-C-05).
    questions = [
        Question(qid=_slug(name), kind="single", variables=(name,), text=variables[name].label)
        for name in df.columns
        if not _is_metadata(name, variables[name].label)
        and not _is_constant_marker(name, variables[name], df[name])
        and not _is_unlabeled_helper(name, variables[name])
    ]
    model = QuestionModel(variables=variables, questions=questions)
    return df, model
