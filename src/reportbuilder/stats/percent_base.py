"""Deterministic resolution of a classified chart's percentage DIRECTION.

A cross-tab of a base variable B (the question) by a classifier C can be
percentaged in two directions. The natural denominator is whichever variable is
the stronger *segmenter* — the conditioning sub-population an analyst reads "of
X, this many are Y" over. We score both and put the denominator on the stronger
one; the base wins only when it strictly outranks the classifier (ties keep the
legacy "classifier" direction). The manual `percent_base` override always wins;
this is only consulted for `percent_base == "auto"`.

The role heuristics mirror the questions API (`api.routes_questions`) so the
"which variables are segmenters" judgement is consistent across the app.
"""
from __future__ import annotations

import re

# Respondent-background concepts (age/gender/region/income/education/…). Matched on
# the question text OR the variable label. Kept in sync with routes_questions.
_DEMOGRAPHIC_RE = re.compile(
    r"\b("
    r"ik[äa]|ik[äa]inen|vuotias|syntym|age|"                      # age
    r"sukupuoli|identifioit|mies\b|nais|gender|"                  # gender
    r"asu[ity]|asuinpaikk|asuinalue|maakun|kaupungi|postinumero|" # region/location
    r"miss[äa]\s+p[äa]in|alue|seutu|region|location|area|"
    r"tulot|tulota|ansio|bruttotul|income|"                       # income
    r"koulutus|education|"                                        # education
    r"kotitalou|asuntokun|household|"                             # household
    r"montako\s+.*taloud|taloutee?si\s+kuulu|"
    r"ty[öo]tilan|occupation|employment|siviilis[äa]"             # occupation / marital
    r")", re.IGNORECASE,
)


def _is_likert_scale(var) -> bool:
    """A 1..N Likert rating item (labels mostly sequential digits starting at 1,
    e.g. '1=Täysin eri mieltä' … '7=Täysin samaa mieltä'). Such items are what a
    survey MEASURES, not how respondents are segmented."""
    pts: list[int] = []
    for vl in var.value_labels:
        m = re.match(r"^\s*(\d+)", vl.label or "")
        if m:
            pts.append(int(m.group(1)))
    if len(pts) < max(3, len(var.value_labels) - 1):
        return False  # not mostly-numeric → not a Likert scale
    uniq = sorted(set(pts))
    return uniq[0] == 1 and uniq == list(range(1, len(uniq) + 1)) and uniq[-1] <= 11


def _looks_demographic(text: str) -> bool:
    return bool(text) and bool(_DEMOGRAPHIC_RE.search(text))


def segmenter_score(var, text: str = "") -> int:
    """How strongly a variable acts as a conditioning/segmenting population — the
    higher, the more naturally it is the DENOMINATOR of a cross-tab:

      3  demographic background (gender/age/region/income/education)
      2  derived segment / low-cardinality categorical (2..10 non-Likert)
      1  other categorical
      0  Likert rating / numeric scale / free text (the thing MEASURED)
    """
    if var.measurement in ("text", "scale"):
        return 0
    if _is_likert_scale(var):
        return 0
    nv = len(var.value_labels)
    if (_looks_demographic(text) or _looks_demographic(var.label or "")) and 2 <= nv <= 15:
        return 3
    if 2 <= nv <= 10:
        return 2
    return 1


def resolve_show_total(spec, has_real_classifier: bool) -> bool:
    """Whether the cross-tab "Total" reference series should be drawn (2026-07-10).

    "on"/"off" force it. "auto" hides it only in a WITHIN-CATEGORY percentage
    distribution — statistic == "pct" with a direction that makes each group sum to
    100% (question/classifier, and "auto" which always resolves to one of those) —
    because there the Total sits on a different denominator and can't be read next to
    the segments. It stays for counts/means, for "% of total", and for single-series
    charts where the Total IS the only series."""
    mode = getattr(spec, "show_total", "auto")
    if mode == "on":
        return True
    if mode == "off":
        return False
    if not has_real_classifier:
        return True                       # single series → the Total is the series
    within_category_pct = (
        spec.statistic == "pct"
        and getattr(spec, "percent_base", "auto") in ("auto", "question", "classifier")
    )
    return not within_category_pct


def resolve_percent_base(question, spec, model) -> str:
    """Resolve `percent_base == "auto"` to a concrete direction ("question" or
    "classifier"). No classifier → "classifier" (only a Total). The base variable
    takes the denominator only when it strictly outranks the classifier."""
    cv = getattr(spec, "classifying_var", None)
    if not cv or not question.variables:
        return "classifier"
    base_var = model.variables.get(question.variables[0])
    clf_var = model.variables.get(cv)
    if base_var is None or clf_var is None:
        return "classifier"
    base_score = segmenter_score(base_var, question.text or "")
    clf_score = segmenter_score(clf_var, clf_var.label or "")
    return "question" if base_score > clf_score else "classifier"
