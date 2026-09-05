"""What a classified chart's percentages are OF, and whether its Total is drawn.

A cross-tab of a base variable B (the question) by a classifier C can be
percentaged in two directions, and they are different numbers about different
things: "of women, 64% are in group 0" against "of group 0, 44% are women".
nSight does not guess which one an author means. The direction is a setting on
the slide, defaulting to the classifier — each classifying group summing to
100% — and `resolve_percent_base` exists only to answer for documents saved
before that was so.

`segmenter_score` lives here for a different question, asked elsewhere: which
variables are worth OFFERING as classifiers (the questions API). It has not
decided a percentage direction since 2026-07-10, and the docstring that said it
did outlived the code by long enough to mislead a reader of this module.
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
    # A STACKED bar's "Total" is a 100%-stacked reference (same 0–100 scale as every
    # other bar), so it's always a valid comparison — unlike a clustered bar where the
    # Total is a base-marginal bar on a different denominator. Show it by default. (2026-07-10)
    if getattr(spec, "chart_type", "") in ("stacked_horizontal_bar", "stacked_vertical_bar"):
        return True
    within_category_pct = (
        spec.statistic == "pct"
        and getattr(spec, "percent_base", "auto") in ("auto", "question", "classifier")
    )
    return not within_category_pct


def resolve_percent_base(question, spec, model) -> str:
    """What `percent_base == "auto"` meant, for the documents that still say it.

    "Automatic" was an option in the editor until it was dropped: it resolved to
    "classifier" every time, whichever way round the variables were, because the
    role-based heuristic behind it (the base wins when it outranks the
    classifier) guessed the wrong direction too often and was removed
    (2026-07-10). The name stayed on the control for a while and told authors
    that something had been worked out about their variables.

    Every report written in that time carries "auto", and each must keep
    rendering the numbers it rendered then — which is what this returns.
    """
    return "classifier"
