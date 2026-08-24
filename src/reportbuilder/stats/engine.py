"""Statistics-engine orchestrator: compute(question, spec, data, model) -> SeriesResult.

Ties together aggregate_counts, base rules, statistics helpers, and sort into the
SeriesResult — the spine output (R1). REQ-C-14/15/16, M-03.
"""
from __future__ import annotations
import collections
import dataclasses
import os
import re
import pandas as pd
from reportbuilder.ingest.sav_reader import string_categories
from reportbuilder.model.question import Question, QuestionModel, Variable
from reportbuilder.model.report import ChartSpec, SortSpec
from reportbuilder.stats.aggregate import aggregate_counts
from reportbuilder.stats.base_rules import single_base, multi_base, segment_bases
from reportbuilder.stats.percent_base import resolve_percent_base, resolve_show_total
from reportbuilder.stats.registry import statistic as get_statistic
from reportbuilder.stats.series import Cell, SeriesResult
from reportbuilder.stats.sorting import sort_categories
from reportbuilder.stats.statistics import pct, count_value, summary_value, largest_remainder
# Import statistics module to trigger built-in registrations
import reportbuilder.stats.statistics  # noqa: F401

# Label used for the aggregated missing-values bucket (REQ-D-06, MV).
# Module constant so it can be imported by tests and localised in future.
NOT_ANSWERED_LABEL: str = "Not answered"


def _seg_key(code: float) -> str:
    """Segment key for a classifier code — matches segment_bases' formatting."""
    return str(int(code)) if float(code).is_integer() else str(code)


def _banner_masks(spec, data: pd.DataFrame, model: QuestionModel, var_name=None):
    """Segment masks when a classifier names a near-partition MULTI question.

    Resolution is variable-name-first — a real DataFrame column or model variable
    always wins — so this only fires for a qid. Returns None otherwise, leaving
    every existing classifier untouched. `var_name` defaults to the PRIMARY
    classifier; the separate layout asks about the second one too, so this is a
    pure resolver — the "a banner cannot be crossed" guard lives in compute().
    (spec 2026-08-02 §2.4, 2026-08-04)"""
    from reportbuilder.ingest.multi_group import member_masks, near_partition

    cv = var_name or getattr(spec, "classifying_var", None)
    if not cv or cv in data.columns or cv in model.variables:
        return None
    q = next((x for x in model.questions
              if x.qid == cv and x.kind == "multi"), None)
    if q is None:
        return None
    masks = member_masks(data, q.variables)
    if not masks or not near_partition(masks, len(data)):
        return None
    return {model.variable(v).label: m for v, m in zip(q.variables, masks)}


def _classifier_masks(spec, data: pd.DataFrame, model: QuestionModel, var_name=None):
    """One boolean mask per segment for ANY classifier form, or None.

    Unifies the three shapes a classifier can take — a banner qid (indicator
    columns), a coded STRING column, and a value-labelled numeric column — so paths
    that segment by hand (the batteries, the separate layout) don't each
    reimplement the resolution. `var_name` defaults to the PRIMARY classifier.
    Ordered: banner, then the column's own values. (spec 2026-08-02 §2.4)"""
    cv = var_name or getattr(spec, "classifying_var", None)
    banner = _banner_masks(spec, data, model, cv)
    if banner:
        return banner
    if not cv or cv not in data.columns:
        return None
    col = data[cv]
    if not pd.api.types.is_numeric_dtype(col):
        vals = col.dropna().astype(str).str.strip()
        vals = vals[vals != ""]
        if len(vals) and not _numeric_like(vals):
            stripped = col.astype(str).str.strip()
            return {v: (stripped == v) for v in string_categories(col)}
    var = model.variables.get(cv)
    if var is None or not var.value_labels:
        return None
    num = pd.to_numeric(col, errors="coerce")
    miss = getattr(var, "missing_values", frozenset())
    out: dict[str, pd.Series] = {}
    for vl in var.value_labels:
        if vl.value in miss:
            continue
        mask = num == float(vl.value)
        if bool(mask.any()):
            out[vl.label] = mask
    return out or None


def _classifier_label(cv: str, model: QuestionModel) -> str:
    """Display label for a classifier — a variable's label, a banner qid's question
    text, else the raw name. Used to prefix separate-layout segments so the two
    variables' groups can never collide. (spec 2026-08-04)"""
    v = model.variables.get(cv)
    if v is not None and (v.label or "").strip():
        return v.label
    q = next((x for x in model.questions if x.qid == cv), None)
    if q is not None and (q.text or "").strip():
        return q.text
    return cv


def _separate_layout(spec) -> bool:
    """True when the author asked for the two classifiers SIDE BY SIDE rather than
    crossed. Needs both variables — one classifier has nothing to sit beside.
    (spec 2026-08-04-separate-classifier-panels)"""
    opts = getattr(spec, "options", None) or {}
    return (opts.get("xtab_layout") == "separate"
            and bool(getattr(spec, "classifying_var", None))
            and bool(getattr(spec, "classifying_var_2", None)))


def _separate_masks(spec, data: pd.DataFrame, model: QuestionModel):
    """(masks, primary) for the SEPARATE layout, or None when it isn't asked for.

    Each variable contributes its own groups as ordinary cuts — no crossing, so a
    respondent counts once per variable and the thin cells a cross-tab produces
    (a 4-person gender group times three age bands) never arise. Segment labels are
    "<variable> · <group>" so two variables sharing a group label stay distinct, and
    `primary` maps each segment to its SOURCE VARIABLE — the hook the renderer
    groups panels by, which is what makes one panel come out per variable.

    A per-variable "<variable> · Total" mask is added when the Total series is on;
    a bare "Total" segment is never emitted, because it belongs to no panel.
    (spec 2026-08-04-separate-classifier-panels)"""
    if not _separate_layout(spec):
        return None
    want_total = resolve_show_total(spec, True)
    cvs = (spec.classifying_var, spec.classifying_var_2)
    labels = [_classifier_label(cv, model) for cv in cvs]
    if labels[0] == labels[1]:
        # Two DIFFERENT variables carrying the SAME label — common in recoded SAV
        # files. Left alone, both variables map to one `primary` value, so the two
        # collapse into a single panel of mixed series; and if they also share a
        # GROUP label the dict key collides and one variable's mask is overwritten,
        # silently dropping a segment from the chart. Disambiguate with the variable
        # NAME, and only in this case, so the normal case keeps its clean labels.
        # (2026-08-04 final review, I7)
        labels = [f"{lbl} ({cv})" for lbl, cv in zip(labels, cvs)]
    masks: dict[str, pd.Series] = {}
    primary: dict[str, str] = {}
    for cv, label in zip(cvs, labels):
        groups = _classifier_masks(spec, data, model, cv)
        if not groups:
            continue                       # stale/empty variable → its panel is dropped
        for group_label, m in groups.items():
            key = f"{label} · {group_label}"
            masks[key] = m
            primary[key] = label
        if want_total:
            any_group = pd.Series(False, index=data.index)
            for m in groups.values():
                any_group = any_group | m
            key = f"{label} · Total"
            masks[key] = any_group
            primary[key] = label
    return (masks, primary) if masks else None


def _numeric_like(values: pd.Series) -> bool:
    """True when the values are really numbers held as strings — those keep the
    existing numeric segmentation path so their value labels still resolve."""
    return bool(pd.to_numeric(values, errors="coerce").notna().all())


def _combo_segmentation(spec: ChartSpec, data: pd.DataFrame):
    """Cross-tab segmentation for TWO classifiers → (seg_series, ordered_keys).

    Returns (None, None) unless both `classifying_var` and `classifying_var_2` are
    set. The combo key is "<code1>|<code2>"; a row missing EITHER classifier is
    excluded (None). `ordered_keys` is numeric primary-major so the first
    classifier clusters (Male·Young, Male·Old, … Female·…). (REQ-C-14b)
    """
    cv1 = spec.classifying_var
    cv2 = getattr(spec, "classifying_var_2", None)
    # A coded STRING classifier (a path/concept column with no value labels) has no
    # numeric codes, so the pd.to_numeric path below would blank every row. Its
    # values ARE the segment keys — exactly what seg_series accepts. A column whose
    # strings are really numbers ("1"/"2") keeps the numeric path so its value
    # labels still resolve. (spec 2026-08-02 §1.2)
    if (cv1 and not cv2 and cv1 in data.columns
            and not pd.api.types.is_numeric_dtype(data[cv1])):
        vals = data[cv1].dropna().astype(str).str.strip()
        vals = vals[vals != ""]
        if len(vals) and not _numeric_like(vals):
            keys = pd.Series([None] * len(data), index=data.index, dtype=object)
            keys.loc[vals.index] = vals
            # Same ordering the picker and the label editor use — one source of truth.
            return keys, string_categories(data[cv1])
    if not (cv1 and cv2):
        return None, None
    c1 = pd.to_numeric(data[cv1], errors="coerce")
    c2 = pd.to_numeric(data[cv2], errors="coerce")
    both = c1.notna() & c2.notna()
    keys = pd.Series([None] * len(data), index=data.index, dtype=object)
    keys.loc[both] = [f"{_seg_key(a)}|{_seg_key(b)}" for a, b in zip(c1[both], c2[both])]
    pairs = sorted({(float(a), float(b)) for a, b in zip(c1[both], c2[both])})
    ordered = tuple(f"{_seg_key(a)}|{_seg_key(b)}" for a, b in pairs)
    return keys, ordered

# Task G.3: actionable message raised when a non-chartable (open-ended text)
# question reaches the engine, instead of a cryptic "could not convert string
# to float" further down the render chain.
TEXT_NOT_CHARTABLE_MSG: str = (
    "This question has open-ended text answers and can't be charted"
)


# Task J.1: word-cloud frequency path. A modest inline Finnish (+ a few English)
# stop-word set so connective/filler words don't dominate the cloud. Kept small
# and deterministic — extend deliberately rather than pulling a heavy NLP dep.
_WORDCLOUD_STOPWORDS: frozenset[str] = frozenset({
    "ja", "tai", "on", "ei", "en", "ole", "se", "ne", "että", "kuin", "mutta",
    "niin", "kun", "jos", "vai", "joka", "tämä", "tää", "nyt", "vielä", "myös",
    "sekä", "mikä", "kaikki", "ihan", "sitä", "tuo", "tämän", "olla", "ovat",
    "hyvin", "the", "of", "and", "for", "with", "not", "you", "are",
    # Filler / non-answer fragments — esp. the words of "en osaa sanoa" / "en
    # tiedä" so a leaked token from a partial match can't pollute the cloud.
    "osaa", "sanoa", "tiedä", "tieda", "mitään", "mitaan", "joku", "jotain",
    "jotakin", "muu", "muuta", "jne", "yms", "ehkä", "vaan", "ois", "olisi",
})

# Whole answers that are NON-RESPONSES — dropped entirely (every word) before
# tokenising, so "en osaa sanoa" / "en tiedä" never contribute "osaa"/"sanoa"/
# "tiedä" to the cloud.
_WORDCLOUD_NON_ANSWERS: frozenset[str] = frozenset({
    "", "-", "--", "?", "ei", "en", "eos", "e o s", "en tiedä", "en tieda",
    "en osaa sanoa", "ei osaa sanoa", "en osaa", "ei mitään", "ei mitaan",
    "ei tietoa", "ei kokemusta", "ei kommentteja", "ei kommenttia",
    "ei mielipidettä", "ei vastausta", "ei käsitystä", "en muista", "en keksi",
    "na", "n a", "ei oo", "ei ole", "tyhjä", "tyhja", "x", "xx",
})


def _is_non_answer_level(label: str) -> bool:
    """Whether a VALUE LABEL names a non-answer rather than a point on the scale.

    "En osaa sanoa" is an answer respondents give, but it is not a rung on the
    ladder: it belongs in the chart and not in the top box or the mean.

    Guessing this from the label's SHAPE — "it has no leading digit" — was
    wrong in both directions. A genuine endpoint typed without its number
    ("Täysin samaa mieltä" beside "1 - …", "2", "3", "4") was dropped from the
    box AND from both halves of the mean; and a "En osaa sanoa" that happens to
    be coded 6 on a word-only 1..5 scale was counted as scale point 6. So ask
    what the label SAYS. The vocabulary is the one the word cloud already uses
    for the same judgement, with the scale-specific phrasings added.
    """
    t = re.sub(r"[^\wäöåÄÖÅ\s]", " ", (label or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    return t in _NON_ANSWER_LEVELS


#: Whole labels that name a non-answer. Deliberately exact-match, not
#: substring: "En osaa sanoa" is one, "En osaa sanoa mitään hyvää" is a real
#: answer, and a scale point that merely CONTAINS "ei" ("Ei lainkaan tärkeä",
#: "Ei kumpaakaan") must never be caught by this.
_NON_ANSWER_LEVELS: frozenset[str] = frozenset({
    "en osaa sanoa", "ei osaa sanoa", "eos", "e o s", "en tiedä", "en tieda",
    "ei tietoa", "ei kokemusta", "ei mielipidettä", "ei mielipidetta",
    "ei vastausta", "ei käsitystä", "ei kasitysta", "en halua sanoa",
    "ei koske minua", "ei sovellu", "en ole käyttänyt", "en ole kayttanyt",
    # Punctuation is stripped to spaces before matching, so "don't know"
    # arrives here as "don t know".
    "don t know", "dont know", "do not know", "no opinion", "not applicable",
    "n a", "na", "prefer not to say", "no answer",
})


def _is_non_answer(text: str) -> bool:
    """True when an open-ended answer is a non-response ('en osaa sanoa', '-',
    'en tiedä', …) and should contribute NOTHING to the word cloud."""
    t = re.sub(r"[^\wäöåÄÖÅ\s]", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    return t in _WORDCLOUD_NON_ANSWERS
# Tokens shorter than this are dropped (e.g. "ok", "ei" handled by stopwords).
_WORDCLOUD_MIN_LEN: int = 3
# Maximum number of distinct words carried into the SeriesResult / cloud.
_WORDCLOUD_TOP_N: int = 60


def _wordcloud(question: Question, spec: ChartSpec, data: pd.DataFrame,
               model: QuestionModel) -> SeriesResult:
    """Word-frequency SeriesResult for a free-text question (Task J.1).

    Gathers the response strings across ALL of the question's member variables
    (multi text questions like var37 have several columns — combined), tokenises
    each (lowercase, unicode word tokens), drops short tokens, pure numbers, and a
    small Finnish stop-word set, then counts frequencies and keeps the top N words.

    The result reuses the standard SeriesResult/Cell contract so it flows through
    build_pptx → the wordcloud render plugin → slide_chrome unchanged:
    ``categories`` are the words, ``segments`` is ``("Total",)``, each cell carries
    ``count`` = the word frequency (statistic = "count"), and ``base_n["Total"]`` is
    the number of respondents who gave any text answer.

    Raises ``ValueError`` when there are no usable words (preview/render map this to a
    clean 422) — e.g. a wordcloud requested on a non-text question.
    """
    var_names = list(question.variables)
    counts: collections.Counter[str] = collections.Counter()
    answered_mask = pd.Series(False, index=data.index)
    for name in var_names:
        if name not in data.columns:
            continue
        col = data[name]
        is_str = col.map(lambda x: isinstance(x, str) and x.strip() != "")
        answered_mask = answered_mask | is_str
        for text in col[is_str]:
            # Skip whole non-responses ("en osaa sanoa", "-") so their words
            # never reach the cloud.
            if _is_non_answer(text):
                continue
            for tok in re.findall(r"\w+", text.lower(), re.UNICODE):
                if len(tok) < _WORDCLOUD_MIN_LEN:
                    continue
                if tok.isdigit():
                    continue
                if tok in _WORDCLOUD_STOPWORDS:
                    continue
                counts[tok] += 1

    if not counts:
        raise ValueError("No text answers to build a word cloud")

    # Fold per-question value merges: combine variant tokens into one word,
    # summing their counts (data cleaning — "esperi" + "esper" → "Esperi"). The
    # merged word keeps its display label as the key; its size reflects the sum.
    for label, members in getattr(question, "value_merges", ()) or ():
        merged = sum(counts.pop(str(m).lower(), 0) for m in members)
        if merged:
            counts[label] = counts.get(label, 0) + merged

    respondents = int(answered_mask.sum())
    # Deterministic ordering: count desc, then word asc to break ties stably.
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:_WORDCLOUD_TOP_N]
    total = sum(counts.values())

    overrides = spec.label_override_map() if hasattr(spec, "label_override_map") else {}
    categories: list[str] = []
    cells: dict[tuple[str, str], Cell] = {}
    for word, freq in top:
        display = overrides.get(word, word)
        # Defensive: skip a collision if an override maps two words to one label.
        if (display, "Total") in cells:
            continue
        categories.append(display)
        cells[(display, "Total")] = Cell(
            pct=(freq / total * 100.0) if total else None,
            count=float(freq),
            mean=None,
        )

    return SeriesResult(
        categories=tuple(categories),
        segments=("Total",),
        cells=cells,
        base_n={"Total": respondents},
        statistic="count",
    )


def _summary(question: Question, spec: ChartSpec, data: pd.DataFrame,
             model: QuestionModel, stat) -> SeriesResult:
    """Compute a summary-statistic SeriesResult — one category × segments.

    Works for any registered summary statistic (mean, median, sum, …).
    For mean: stores value in the named `mean` field for backward-compat.
    For others: stores in cell.extra so cell.value(stat.name) retrieves it.
    (REQ-C-15, REQ-N-02)
    """
    var = model.variable(question.variables[0])   # single var; multi: first var
    label = question.text or var.label
    fmt = spec.number_format
    separate = _separate_masks(spec, data, model)
    banner = None if separate is not None else _banner_masks(spec, data, model)
    seg_series, ordered = ((None, None) if (banner or separate is not None)
                           else _combo_segmentation(spec, data))
    usable_clf = spec.classifying_var and spec.classifying_var in data.columns
    if separate is not None:
        # A respondent belongs to a group of BOTH variables at once, so the key
        # SERIES this function otherwise uses to represent a segmentation cannot
        # express it — take each segment's rows straight from its own mask instead.
        # Cell shape mirrors the classifier branch below. (spec 2026-08-04)
        sep_masks, sep_primary = separate
        bases = segment_bases(data, var, seg_masks=sep_masks)
        cells: dict[tuple[str, str], Cell] = {}
        for seg, m in sep_masks.items():
            v = summary_value(data.loc[m, var.name], var, fmt, stat)
            if stat.name == "mean":
                cells[(label, seg)] = Cell(pct=None, count=None, mean=v)
            else:
                cells[(label, seg)] = Cell(pct=None, count=None, mean=None,
                                           extra=((stat.name, v),))
        return SeriesResult(categories=(label,), segments=tuple(sep_masks),
                            cells=cells, base_n=bases, statistic=stat.name,
                            segment_primary=sep_primary)
    if banner is not None or seg_series is not None or usable_clf:
        if banner is not None:                       # banner: indicator columns
            bases = segment_bases(data, var, seg_masks=banner)
            segments = (*banner.keys(), "Total")
            # A summary statistic reads one value per segment; represent the banner
            # as a key series (segments are disjoint by construction here).
            seg_series = pd.Series([None] * len(data), index=data.index, dtype=object)
            for label, m in banner.items():
                seg_series.loc[m] = label
        elif seg_series is not None:                 # cross-tab: two classifiers
            bases = segment_bases(data, var, seg_series=seg_series)
            segments = (*ordered, "Total")
        else:
            bases = segment_bases(data, var, spec.classifying_var,
                                  classifier_var=model.variables.get(spec.classifying_var))
            seg_series = pd.to_numeric(data[spec.classifying_var], errors="coerce")
            segments = tuple(s for s in bases if s != "Total") + ("Total",)
        cells: dict[tuple[str, str], Cell] = {}
        for seg in segments:
            # Mask by the segment key (string combo or numeric code); "|" marks a combo.
            if seg == "Total":
                vals = data[var.name]
            elif seg_series.dtype == object or "|" in seg:
                vals = data.loc[seg_series == seg, var.name]
            else:
                vals = data.loc[seg_series == float(seg), var.name]
            v = summary_value(vals, var, fmt, stat)
            if stat.name == "mean":
                cells[(label, seg)] = Cell(pct=None, count=None, mean=v)
            else:
                cells[(label, seg)] = Cell(pct=None, count=None, mean=None,
                                           extra=((stat.name, v),))
        base_n = {s: bases.get(s, 0) for s in segments}
    else:
        segments = ("Total",)
        vals = data[var.name]
        v = summary_value(vals, var, fmt, stat)
        if stat.name == "mean":
            cells = {(label, "Total"): Cell(pct=None, count=None, mean=v)}
        else:
            cells = {(label, "Total"): Cell(pct=None, count=None, mean=None,
                                            extra=((stat.name, v),))}
        base_n = {"Total": single_base(data, var)}
    return SeriesResult(categories=(label,), segments=segments, cells=cells,
                        base_n=base_n, statistic=stat.name)


def _auto_pct_decimals(values: list[float | None]) -> int:
    """Decimals auto mode would DISPLAY for these pct values (Task G.4).

    Mirrors the pct branch of render.image._mpl.auto_decimals (kept in sync) so
    the engine can decide whether a category's *displayed* value rounds to zero
    without importing the (matplotlib-heavy) image layer.
    """
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return 0
    all_large = all(v >= 10.0 for v in clean)
    frac_trivial = all(abs(v % 1) < 0.05 for v in clean)
    if all_large or frac_trivial:
        return 0
    sorted_vals = sorted(clean)
    if len(sorted_vals) > 1:
        min_spread = min(b - a for a, b in zip(sorted_vals, sorted_vals[1:]))
    else:
        min_spread = 1.0
    if any(v < 10.0 for v in clean) or min_spread < 1.0:
        return 1
    return 0


def _effective_pct_decimals(values: list[float | None], fmt) -> int:
    """Decimals actually shown for pct given the NumberFormat (auto or manual)."""
    if getattr(fmt, "mode", "auto") == "manual":
        return getattr(fmt, "pct_decimals", 0)
    return _auto_pct_decimals(values)


def _displayed_zero(cell: Cell | None, statistic: str, decimals: int) -> bool:
    """True when the cell's DISPLAYED value rounds to zero (Task G.4).

    For ``count`` the displayed integer rounds to 0; for ``pct`` (and other
    distribution stats) the value rounds to 0 at the effective decimals shown.
    A missing cell is treated as zero. This is what drives the
    show_empty_categories=False hide-empty filter — a tiny-but-nonzero category
    such as 4/1001 → "0 %" is now dropped, while a "0.4 %" (1-decimal) is kept.
    """
    if cell is None:
        return True
    if statistic == "count":
        return cell.count is None or round(float(cell.count)) == 0
    return cell.pct is None or round(float(cell.pct), decimals) == 0


def _drop_displayed_zero_rows(rows, cells, segments, statistic, fmt):
    """Drop rows whose displayed value rounds to 0 across ALL segments (Task G.4).

    Computes the effective per-segment pct decimals from the surviving category
    values (matching how the renderer formats the series), removes the dropped
    cells from ``cells`` in place, and returns the kept rows.
    """
    displays = [r[0] for r in rows]
    seg_dec = {
        seg: _effective_pct_decimals(
            [cells[(d, seg)].pct for d in displays if (d, seg) in cells], fmt
        )
        for seg in segments
    }
    kept = []
    for r in rows:
        disp = r[0]
        if all(
            _displayed_zero(cells.get((disp, seg)), statistic, seg_dec[seg])
            for seg in segments
        ):
            for seg in segments:
                cells.pop((disp, seg), None)
        else:
            kept.append(r)
    return kept


def _effective_missing(spec: ChartSpec, var: Variable) -> set[float]:
    """Resolve the effective "Not answered" code set.

    When spec.not_answered_codes is provided (not None) it overrides the
    SAV-detected user-missing set; otherwise the variable's own missing_values
    is used. System-missing/NaN is always treated as "Not answered" on top of
    this set. (REQ-D-06)
    """
    codes = getattr(spec, "not_answered_codes", None)
    if codes is not None:
        return set(codes)
    return set(var.missing_values)


def _missing_counts(data: pd.DataFrame, var: Variable, eff: set[float],
                    classifying_var: str | None = None,
                    *, seg_series: pd.Series | None = None,
                    seg_masks: dict[str, pd.Series] | None = None) -> dict[str, int]:
    """Count sysmis + "not answered" rows per segment using the effective set.

    Returns a dict of {segment_label: count}. Always includes "Total".
    For segmented data the per-segment count only considers rows whose
    classifying variable has a valid (non-NaN) code — consistent with the
    segment_bases convention. (REQ-D-06, REQ-MV-01, REQ-MV-02)

    `seg_masks` IS the segmentation when given — one boolean mask per segment,
    mirroring `segment_bases`/`aggregate_counts`, so the keys here match the
    segment labels those produce. Mask-segmented paths (a banner classifier, the
    SEPARATE layout) have no classifier COLUMN to coerce: keying off
    `classifying_var` there either raises (a banner qid is not a column) or
    returns raw codes ("1", "2") that no segment is named after, so every lookup
    silently yields 0 and "Not answered" prints 0 % everywhere.
    (spec 2026-08-04-separate-classifier-panels)
    """
    s = pd.to_numeric(data[var.name], errors="coerce")
    missing_mask = s.isna() | s.isin(eff)
    result: dict[str, int] = {"Total": int(missing_mask.sum())}
    if seg_masks is not None:
        for key, m in seg_masks.items():
            result[str(key)] = int((missing_mask & m).sum())
    elif seg_series is not None:
        for key in seg_series.dropna().unique():
            result[str(key)] = int((missing_mask & (seg_series == key)).sum())
    elif classifying_var is not None:
        seg = pd.to_numeric(data[classifying_var], errors="coerce")
        for code in sorted(seg.dropna().unique()):
            seg_label = str(int(code)) if float(code).is_integer() else str(code)
            result[seg_label] = int((missing_mask & (seg == code)).sum())
    return result


_STACKED_BAR_TYPES = frozenset({"stacked_horizontal_bar", "stacked_vertical_bar"})


#: Sort bases that rank bars by a summed share of one END of the scale, as
#: (how many levels, from the bottom?). Top-box answers "who agrees most";
#: bottom-box answers "where is the dissatisfaction", which a reader could
#: previously only approximate by reading a top-box sort backwards — not the
#: same thing when the mass sits in the middle of the scale.
_BOX_SORT_BASES = {
    "topbox_sum": (2, False),
    "top3_sum": (3, False),
    "bottom2_sum": (2, True),
    "bottom3_sum": (3, True),
}

#: The same idea for the row-summary column. Named separately because the
#: row-summary vocabulary has always used "top2_sum" where the sort basis says
#: "topbox_sum".
_BOX_ROW_SUMMARIES = {
    "top2_sum": (2, False),
    "top3_sum": (3, False),
    "bottom2_sum": (2, True),
    "bottom3_sum": (3, True),
}


def _top_scale_categories(var: Variable, categories: list[str], n: int,
                          lowest: bool = False,
                          overrides: dict[str, str] | None = None) -> list[str]:
    """The display labels of the `n` HIGHEST rating-scale points of `var` that are
    present in `categories` (e.g. the top-2 or top-3 agreement levels), or the `n`
    LOWEST when `lowest`. Empty when the variable isn't a rating scale.

    `overrides` is the author's category-label map, and it has to be applied here:
    `categories` are DISPLAY labels while a scale level knows only the label on the
    variable. Without it, shortening one label to fit a slide meant nothing matched,
    the caller found no levels to sum, and the sort silently did nothing while the
    control still read "Top 2".
    """
    lv = scale_levels(var)                     # [(code, label, point), …]
    if not lv:
        return []
    shown = overrides or {}
    ranked = [shown.get(label, label)
              for _c, label, _p in sorted(lv, key=lambda t: t[2], reverse=not lowest)]
    # Count SCALE LEVELS consumed, not distinct labels produced. Two levels
    # shortened to the same string collapse to one entry here, and counting
    # entries meant the loop went on to take the level BELOW them — so "Top 2"
    # became top level plus neutral, and the sort ranked the wrong group first.
    out: list[str] = []
    taken = 0
    for label in ranked:
        if label not in categories:
            continue
        taken += 1
        if label not in out:
            out.append(label)
        if taken >= n:
            break
    return out


def _single(question: Question, spec: ChartSpec, data: pd.DataFrame,
            model: QuestionModel) -> SeriesResult:
    var = model.variable(question.variables[0])
    eff = _effective_missing(spec, var)
    overrides = spec.label_override_map() if hasattr(spec, "label_override_map") else {}
    show_empty: bool = getattr(spec, "show_empty_categories", True)
    labels = {vl.value: vl.label for vl in var.value_labels
              if vl.value not in eff}
    separate = _separate_masks(spec, data, model)
    banner = None if separate is not None else _banner_masks(spec, data, model)
    seg_series, ordered = ((None, None) if (banner or separate is not None)
                           else _combo_segmentation(spec, data))
    # The mask set that IS the segmentation, when one is (banner / separate mode).
    # Every per-segment computation must be given the SAME segmentation, or its keys
    # don't match the segment labels. (2026-08-04)
    act_masks: dict[str, pd.Series] | None = None
    if separate is not None:                         # two classifiers SIDE BY SIDE
        sep_masks, sep_primary = separate
        act_masks = sep_masks
        bases = segment_bases(data, var, missing_override=eff, seg_masks=sep_masks)
        counts = aggregate_counts(data, var.name, seg_masks=sep_masks)
        segments = tuple(sep_masks)                  # no bare "Total": it is no panel
    elif banner is not None:                         # banner: indicator columns
        act_masks = banner
        bases = segment_bases(data, var, missing_override=eff, seg_masks=banner)
        counts = aggregate_counts(data, var.name, seg_masks=banner)
        segments = (*banner.keys(), "Total")
    elif seg_series is not None:                     # cross-tab: two classifiers
        bases = segment_bases(data, var, missing_override=eff, seg_series=seg_series)
        counts = aggregate_counts(data, var.name, seg_series=seg_series)
        segments = (*ordered, "Total")
    elif spec.classifying_var and spec.classifying_var in data.columns:
        bases = segment_bases(data, var, spec.classifying_var, missing_override=eff,
                              classifier_var=model.variables.get(spec.classifying_var))
        counts = aggregate_counts(data, var.name, spec.classifying_var)
        segments = tuple(s for s in bases if s != "Total")
        segments = (*segments, "Total") if segments else ("Total",)
    else:
        # No usable classifier — including a stored qid that no longer resolves to a
        # near-partition banner (the data changed). Degrade to a single Total series
        # rather than failing, matching the lenient handling of stale groupings.
        bases = {"Total": single_base(data, var, missing_override=eff)}
        counts = aggregate_counts(data, var.name)
        segments = ("Total",)

    # When show_not_answered is True, recompute over total (valid + missing). (REQ-D-06, MV)
    show_na: bool = getattr(spec, "show_not_answered", False)
    if show_na:
        missing_n = _missing_counts(data, var, eff, spec.classifying_var,
                                    seg_series=seg_series, seg_masks=act_masks)
        denom = {seg: bases.get(seg, 0) + missing_n.get(seg, 0) for seg in segments}
        # The N footer reads base_n["Total"] whether or not "Total" is a SEGMENT
        # (separate mode has none — a bare Total belongs to no panel). It must go
        # through the same valid+missing arithmetic as the segments, or the same
        # slide prints a smaller N in separate mode than crossed. (2026-08-04)
        denom_total = bases.get("Total", 0) + missing_n.get("Total", 0)
    else:
        denom = {seg: bases.get(seg, 0) for seg in segments}
        denom_total = bases.get("Total", 0)

    # Natural ("data order") sorting key. For a RATING SCALE, order by the scale
    # point parsed from the label's leading digit (1..N) — NOT the SAV's stored
    # code/position, because labelled endpoints ("1=Täysin eri mieltä",
    # "7=Täysin samaa mieltä") are often stored with large out-of-order codes, so
    # raw storage order yields e.g. 2,3,4,5,6,1,7. A non-numeric label in a scale
    # (e.g. "En osaa sanoa") sorts after the numeric points.
    # A numeric scale labelled only on SOME points (e.g. 1..7 with text on the
    # endpoints) is charted with ALL points as numbers (never dropping the unlabelled
    # 2..6), ordered high→low, and the text labels moved to a caption. Otherwise the
    # normal path: categories are the labelled codes, rating scales ordered by point.
    scale_entries, scale_caption = _partial_scale(var, data, eff)
    if scale_entries is not None:
        entries = scale_entries
        is_rating = False  # scale_entries is not None already forces data_order below
    else:
        rating = _rating_scale(var)
        is_rating = len(rating) >= max(3, len(labels) - 1)
        entries = [
            (code, overrides.get(label, label),
             float(rating.get(code, 1000 + idx) if is_rating else idx))
            for idx, (code, label) in enumerate(labels.items())
        ]

    # Which of those entries are points ON the rating scale, and where each sits.
    # The row-summary column (top/bottom box, mean) must follow the SCALE, and the
    # display order above is not always it:
    #   * a WORD-labelled scale has no leading digit to parse, so `entries` falls
    #     back to the order the labels happen to occupy in the SAV — and plenty of
    #     exports write them high→low, which made "top 2" the two most NEGATIVE
    #     levels. scale_levels() reads the word-only case (contiguous codes ARE the
    #     points), so use it when the digit parse found nothing.
    #   * "En osaa sanoa" is an ANSWER, not a scale point. It parked at 1000+idx,
    #     i.e. past 5, and so was counted into the top box. Anything the scale does
    #     not contain is left out of the summary entirely.
    # When no scale can be read at all, nothing here is meaningful, so the display
    # order stands — as it always did. (review 2026-08-24)
    if scale_entries is not None:
        summary_points = {code: pt for code, _lbl, pt in entries}
    elif is_rating:
        # `is_rating` tolerates ONE label the digit parse could not read, and
        # that label is not always "En osaa sanoa" — it is just as often a real
        # endpoint typed without its number ("Täysin samaa mieltä" beside
        # "1 - …", "2", "3", "4"). Treating every unparsed label as a
        # non-answer dropped that endpoint from the box AND from both halves of
        # the mean, on a chart that still drew in the right order. So ask what
        # the label says, and give a real level the point its code implies.
        summary_points = dict(rating)
        for code, label in labels.items():
            if code in summary_points or _is_non_answer_level(label):
                continue
            summary_points[code] = float(code)
    else:
        summary_points = {code: pt for code, _lbl, pt in scale_levels(var)}
        if not summary_points:
            summary_points = {code: pt for code, _lbl, pt in entries}
    # Whatever route got us here, a non-answer is never a scale point.
    summary_points = {code: pt for code, pt in summary_points.items()
                      if not _is_non_answer_level(labels.get(code, ""))}

    # Cross-tab percentage DIRECTION (percent_base). Only meaningful with a real
    # classifier: "question" distributes the classifier within each base category
    # (each base-category row sums to 100%); "total" is over the grand total;
    # "classifier" (legacy) distributes the base var within each segment. "auto" is
    # resolved to a concrete direction upstream; anything else → "classifier".
    grand_total = denom.get("Total", 0)
    real_segs = [s for s in segments if s != "Total"]
    pb = getattr(spec, "percent_base", "auto")
    if not (spec.classifying_var and real_segs):
        pb = "classifier"
    elif separate is not None:
        # The segments come from two UNRELATED variables, so "within each answer
        # category" would distribute across cuts that share no denominator and
        # print labels that don't sum. Each panel is a plain per-group
        # distribution. (spec 2026-08-04)
        pb = "classifier"
    elif spec.chart_type in _STACKED_BAR_TYPES:
        # A 100%-stacked bar's bars ARE the classifier groups, each a full stack of the
        # base categories → the only coherent direction is "classifier" (base distributed
        # within each classifier group, so each bar sums to 100%). Any other direction
        # would print labels that don't add up to the 100%-filled bar. (2026-07-10)
        pb = "classifier"
    elif pb == "auto":
        pb = resolve_percent_base(question, spec, model)
    elif pb not in ("classifier", "question", "total"):
        pb = "classifier"
    denom_q: dict[str, int] = {}
    if pb == "question":
        for _code, _display, _di in entries:
            denom_q[_display] = sum(counts.get((_code, s), 0) for s in real_segs)

    cells: dict[tuple[str, str], Cell] = {}
    raw_cb: dict[tuple[str, str], tuple[float, int]] = {}  # (count, base) per cell
    rows = []
    for code, display, data_index in entries:
        for seg in segments:
            c = counts.get((code, seg), 0)
            if pb == "total":
                base = grand_total
            elif pb == "question":
                # Real segments distribute within the base category; the "Total"
                # reference column stays the overall (grand-total) marginal.
                base = grand_total if seg == "Total" else denom_q.get(display, 0)
            else:
                base = denom.get(seg, 0)
            raw_cb[(display, seg)] = (c, base)
            cells[(display, seg)] = Cell(pct=pct(c, base, spec.number_format),
                                         count=count_value(c, spec.number_format),
                                         mean=None)
        if separate is not None:
            # Separate-panel mode has no bare "Total" segment (each panel keeps its
            # own per-variable "<label> · Total" instead), so there is no
            # cells[(display, "Total")] to read. aggregate_counts/segment_bases still
            # carry the OVERALL union under the "Total" key — the same numbers the
            # crossed path's Total column would have carried — so the row's sort
            # values (pct/count/topbox) stay real numbers instead of collapsing to
            # None, which crashed sort_categories for any basis other than
            # data_order/top3_sum (e.g. the UI's default "pct" sort). (2026-08-04)
            _tot_c = counts.get((code, "Total"), 0)
            _tot_b = bases.get("Total", 0)
            total_cell = Cell(pct=pct(_tot_c, _tot_b, spec.number_format),
                              count=count_value(_tot_c, spec.number_format), mean=None)
        else:
            total_cell = cells[(display, "Total")]
        rows.append((display, code, {"pct": total_cell.pct, "count": total_cell.count,
                                     "mean": 0.0, "data_index": data_index,
                                     "topbox": total_cell.pct}))

    # Hide categories whose DISPLAYED value rounds to 0 across ALL segments. (Task G.4)
    if not show_empty:
        rows = _drop_displayed_zero_rows(
            rows, cells, segments, spec.statistic, spec.number_format
        )

    # A partially-labelled scale is always shown in scale order, high→low (its
    # data_index carries -point, so 7 sits at the top) regardless of the spec's sort
    # basis — a frequency sort would scramble the scale. (REQ-C-24c)
    # A STACKED bar split by a classifier likewise keeps its scale stack in order — the
    # sort there targets the BARS (the classifier segments), reordered further below.
    # A STACKED bar of a RATING SCALE keeps its scale order too, classifier or not: a
    # 100%-stack of an ordered scale is only readable in scale order, and the
    # row-summary column ("Top 2", net) is only checkable by eye when the summed
    # segments sit next to each other in the stack — a size sort scatters them. A
    # stacked bar of a plain categorical (no inherent order) still honours the slide's
    # frequency sort. (defect: mat-erisan var212 legend rendered 4,3,5,2,1 instead of
    # 1..5, so "Top 2" (4+5) read as the two visually-biggest bands (3+4) instead)
    _bars_are_segments = spec.chart_type in _STACKED_BAR_TYPES and bool(spec.classifying_var)
    _stacked_rating_scale = spec.chart_type in _STACKED_BAR_TYPES and is_rating
    sort_spec = (SortSpec(basis="data_order")
                 if (scale_entries is not None or _bars_are_segments
                     or _stacked_rating_scale) else spec.sort)
    categories: list[str] = list(sort_categories(rows, sort_spec))

    if show_na:
        # Append "Not answered" last — after all real sorted categories.
        na_display = overrides.get(NOT_ANSWERED_LABEL, NOT_ANSWERED_LABEL)
        na_total = missing_n.get("Total", 0)
        # Suppress a 0-count "Not answered" bucket when empty categories are hidden.
        if show_empty or na_total != 0:
            for seg in segments:
                mc = missing_n.get(seg, 0)
                base = denom.get(seg, 0)
                raw_cb[(na_display, seg)] = (mc, base)
                cells[(na_display, seg)] = Cell(
                    pct=pct(mc, base, spec.number_format),
                    count=count_value(mc, spec.number_format),
                    mean=None,
                )
            categories.append(na_display)

    # Stacked + classifier: reorder the BARS (segments) by the chosen criterion — the
    # top-2/top-3 summed share of each bar's HIGHEST scale levels — so the most-"agree"
    # group leads while the scale stack stays 1..N. (customer: sort the categories, not
    # the values)
    if _bars_are_segments and spec.sort.basis in _BOX_SORT_BASES:
        n_top, _lowest = _BOX_SORT_BASES[spec.sort.basis]
        top_cats = _top_scale_categories(var, categories, n_top, lowest=_lowest,
                                         overrides=overrides)
        if top_cats:
            def _topbox(seg: str) -> float:
                return sum((cells.get((c, seg)) or Cell(pct=None)).pct or 0.0
                           for c in top_cats)

            reals = [s for s in segments if s != "Total"]
            if separate is not None:
                # Sort WITHIN each panel. A global sort would interleave the two
                # variables' segments and destroy the panel grouping. (2026-08-04)
                # Each panel's OWN "<label> · Total" is a reference bar, not a group
                # to rank — like the bare "Total" pinned outside separate mode, it is
                # excluded from the sort and pinned at the END of its panel.
                # (2026-08-04)
                _sp = separate[1]

                def _is_panel_total(s: str) -> bool:
                    return s == f"{_sp[s]} · Total"

                order: list[str] = []
                for panel in dict.fromkeys(_sp[s] for s in reals):
                    panel_segs = [s for s in reals if _sp[s] == panel]
                    groups = [s for s in panel_segs if not _is_panel_total(s)]
                    totals = [s for s in panel_segs if _is_panel_total(s)]
                    order += sorted(groups, key=_topbox, reverse=spec.sort.descending)
                    order += totals
                reals = order
            else:
                reals.sort(key=_topbox, reverse=spec.sort.descending)
            segments = tuple(reals) + (("Total",) if "Total" in segments else ())

    # Largest-remainder rounding so each 100%-partition's displayed %s sum to exactly
    # 100 (avoids e.g. 54 % + 45 % = 99 %). pct statistic only; the partition axis
    # follows the percentage direction. (2026-07-10)
    if spec.statistic == "pct":
        dec = spec.number_format.pct_decimals

        def _reround(keys):
            keys = [k for k in keys if k in cells]
            bs = [raw_cb.get(k, (0, 0))[1] for k in keys]
            base_g = bs[0] if bs else 0
            if base_g and all(b == base_g for b in bs):
                cs = [raw_cb.get(k, (0, 0))[0] for k in keys]
                for k, p in zip(keys, largest_remainder(cs, base_g, dec)):
                    cells[k] = dataclasses.replace(cells[k], pct=p)

        if pb == "question":
            for cat in categories:                      # each base-category's segments
                _reround([(cat, s) for s in segments if s != "Total"])
            if "Total" in segments:                     # the grand-total distribution column
                _reround([(cat, "Total") for cat in categories])
        else:                                           # classifier/total: each column
            for seg in segments:
                _reround([(cat, seg) for cat in categories])

    # A stacked bar carries the right-hand row-summary column (one value per BAR),
    # exactly like a battery. The bars are the classifier groups; with NO classifier
    # the single 'Total' column IS the one bar (see _stacked_layout) and is just as
    # much a row to summarise. (2026-07-10, 2026-08-03)
    row_summaries = None
    statements: list[str] = []
    if (spec.chart_type in _STACKED_BAR_TYPES
            and getattr(spec, "row_summary_fn", "none") != "none"):
        # Stack levels in ASCENDING scale order, independent of the display sort, so
        # "top 2" always means the two highest scale points. A partially-labelled scale
        # charts high→low and carries -point as its ordering key, hence the flip.
        flip = -1.0 if scale_entries is not None else 1.0
        shown = set(categories)
        scale = sorted(((code, lbl, summary_points[code]) for code, lbl, _ in entries
                        if lbl in shown and code in summary_points),
                       key=lambda e: flip * e[2])
        # "Sum"/"net" name their levels explicitly, so they see every rendered level,
        # scale point or not: an author who ticks "En osaa sanoa" means it.
        levels = [(code, lbl) for code, lbl, _ in entries if lbl in shown]
        # Every rendered bar gets a value, the "Total" reference bar included — it is
        # a row like any other. Values are keyed by bar, not positional.
        statements = list(segments)
        row_summaries = _compute_row_summaries(
            spec, statements, [d for _, d in levels], [c for c, _ in levels], cells,
            scale_levels=[d for _, d, _ in scale],
            # The SCALE POINT, not the SAV code. `points` above stays on codes
            # because that is what an author's picked row_summary_codes name,
            # but a mean weighted by code prints 1.0 for a reverse-coded file
            # where everyone answered "5", and 13.0 for one coded 11..15.
            scale_points=[pt for _c, _d, pt in scale])

    base_n = {s: denom.get(s, 0) for s in segments}
    base_n.setdefault("Total", denom_total)
    return SeriesResult(categories=tuple(categories), segments=segments, cells=cells,
                        base_n=base_n,
                        statistic=spec.statistic, caption=scale_caption,
                        row_summaries=row_summaries,
                        row_summary_keys=tuple(statements),
                        segment_primary=(separate[1] if separate is not None else None))


def _partial_scale(var: Variable, data: pd.DataFrame, eff: set[float]):
    """Detect a numeric integer scale labelled on only SOME points (e.g. 1..7 with
    text on the endpoints). Returns ``(entries, caption)`` where entries is
    ``[(code, "<n>", -n), …]`` for EVERY data point (shown as its number, ordered
    high→low so 7 is at the top) and caption is ``"1 = … · 7 = …"``. Returns
    ``(None, None)`` for fully-labelled or non-scale variables (unchanged path)."""
    if var.name not in data.columns:
        return None, None
    s = pd.to_numeric(data[var.name], errors="coerce")
    data_pts = {int(x) for x in s.dropna().unique()
                if float(x).is_integer() and x not in eff}
    labeled = {int(vl.value): vl.label for vl in var.value_labels
               if float(vl.value).is_integer() and vl.value not in eff}
    if not data_pts or not labeled:
        return None, None
    # A partial rating scale has UNLABELLED points that actually got responses (the
    # 2..6 of a 1..7 endpoint-labelled scale). This is what separates it from a normal
    # categorical that merely has a far-coded labelled category (e.g. NA=9): there the
    # data points are all labelled, so this is False and we take the normal path.
    if not any(p not in labeled for p in data_pts):
        return None, None
    all_pts = data_pts | set(labeled)
    lo, hi = min(all_pts), max(all_pts)
    # Plausible rating-scale span (endpoints define it). Too narrow or too wide → no.
    if not (4 <= (hi - lo) <= 10):
        return None, None
    # Full CONTIGUOUS range so every point shows (an unanswered middle point as a
    # 0% bar, no gaps).
    pts = list(range(lo, hi + 1))
    if not any(p not in labeled for p in pts):
        return None, None   # fully labelled → normal path
    entries = [(float(p), str(p), float(-p)) for p in pts]
    caption = " · ".join(f"{p} = {labeled[p]}" for p in sorted(labeled))
    return entries, caption


def _multi(question: Question, spec: ChartSpec, data: pd.DataFrame,
           model: QuestionModel) -> SeriesResult:
    vars_ = [model.variable(n) for n in question.variables]
    overrides = spec.label_override_map() if hasattr(spec, "label_override_map") else {}
    show_empty: bool = getattr(spec, "show_empty_categories", True)

    # Optional cross-tab: split the options by a classifying variable (or a two-
    # classifier combo). Each segment gets its OWN base — respondents in that segment
    # who answered the multi — so a cell reads "% of <segment> who selected <option>".
    # Segments are code strings; compute() relabels them to the classifier's value
    # labels via _relabel_segments / _relabel_combo_segments. (2026-07-10)
    separate = _separate_masks(spec, data, model)
    banner = None if separate is not None else _banner_masks(spec, data, model)
    seg_series, ordered = ((None, None) if (banner or separate is not None)
                           else _combo_segmentation(spec, data))
    seg_codes: list[str] = []
    seg_mask: dict[str, "pd.Series"] = {}
    if separate is not None:                          # two classifiers SIDE BY SIDE
        for label, m in separate[0].items():
            seg_codes.append(label)
            seg_mask[label] = m
    elif banner is not None:
        # A banner classifier is ALREADY one mask per segment — exactly this shape.
        for label, m in banner.items():
            if bool(m.any()):
                seg_codes.append(label)
                seg_mask[label] = m
    elif seg_series is not None:
        for sc in ordered:
            m = (seg_series == sc)
            if bool(m.any()):
                seg_codes.append(sc)
                seg_mask[sc] = m
    elif spec.classifying_var and spec.classifying_var in data.columns:
        clf_var = model.variables.get(spec.classifying_var)
        clf = pd.to_numeric(data[spec.classifying_var], errors="coerce")
        miss = getattr(clf_var, "missing_values", frozenset()) if clf_var else frozenset()
        for vl in (clf_var.value_labels if clf_var else []):
            if vl.value in miss:
                continue
            m = (clf == float(vl.value))
            if bool(m.any()):
                code = str(int(vl.value)) if float(vl.value).is_integer() else str(vl.value)
                seg_codes.append(code)
                seg_mask[code] = m

    # No bare "Total" segment in separate mode: each panel carries its own
    # "<label> · Total" instead, and a Total across two unrelated variables is
    # noise (matches _single's separate-mode handling).
    # (spec 2026-08-04-separate-classifier-panels)
    segments = tuple(seg_codes) if separate is not None else tuple(seg_codes) + ("Total",)
    base_total = multi_base(data, vars_)
    seg_base = {sc: multi_base(data[seg_mask[sc]], vars_) for sc in seg_codes}
    seg_base["Total"] = base_total

    cells: dict[tuple[str, str], Cell] = {}
    rows = []
    for idx, v in enumerate(vars_):
        display = overrides.get(v.label, v.label)
        s = pd.to_numeric(data[v.name], errors="coerce")
        sel = (s == 1.0) & ~s.isin(v.missing_values)
        tc = int(sel.sum())
        cells[(display, "Total")] = Cell(pct=pct(tc, base_total, spec.number_format),
                                         count=count_value(tc, spec.number_format), mean=None)
        for sc in seg_codes:
            c = int((sel & seg_mask[sc]).sum())
            cells[(display, sc)] = Cell(pct=pct(c, seg_base[sc], spec.number_format),
                                        count=count_value(c, spec.number_format), mean=None)
        cell = cells[(display, "Total")]
        rows.append((display, float(idx), {"pct": cell.pct, "count": cell.count,
                                           "mean": 0.0, "data_index": idx, "topbox": cell.pct}))

    # Hide members whose DISPLAYED value rounds to 0 when show_empty is False. (Task G.4)
    if not show_empty:
        rows = _drop_displayed_zero_rows(
            rows, cells, segments, spec.statistic, spec.number_format
        )

    categories = tuple(sort_categories(rows, spec.sort))
    return SeriesResult(categories=categories, segments=segments, cells=cells,
                        base_n=seg_base, statistic=spec.statistic,
                        segment_primary=(separate[1] if separate is not None else None))


def _code_label_map(var: Variable, seg_codes: set[str]) -> dict[str, str]:
    """{code_string: value_label} for a classifier variable. Empty labels + a
    derived binary 0/1 SEGMENT FLAG (label == name) → {"1": name, "0": "Muut"}."""
    m: dict[str, str] = {}
    for vl in var.value_labels:
        key = str(int(vl.value)) if float(vl.value).is_integer() else str(vl.value)
        m[key] = vl.label
    if not m and (var.label or "").strip() == var.name and seg_codes and seg_codes <= {"0", "1"}:
        m = {"1": var.label, "0": "Muut"}
    return m


def _relabel_combo_segments(result: SeriesResult, model: QuestionModel,
                            cv1: str, cv2: str) -> SeriesResult:
    """Relabel cross-tab combo segments "<c1>|<c2>" → "<label1> · <label2>" using both
    classifiers' value labels, and tag each with its PRIMARY group so the renderer can
    group the bars. The cross-tab Total BAR is DROPPED (a total across both classifiers is
    noise); base_n["Total"] is kept for the footer. Unknown codes pass through."""
    try:
        var1, var2 = model.variable(cv1), model.variable(cv2)
    except Exception:
        return result
    parts = [s.split("|", 1) for s in result.segments if s != "Total" and "|" in s]
    if not parts:
        return result
    m1 = _code_label_map(var1, {p[0] for p in parts})
    m2 = _code_label_map(var2, {p[1] for p in parts})

    def rl(seg: str) -> str:
        if seg == "Total" or "|" not in seg:
            return seg
        a, b = seg.split("|", 1)
        return f"{m1.get(a, a)} · {m2.get(b, b)}"

    # Segments WITHOUT the Total bar (kept in base_n via rl("Total") == "Total").
    new_segs = tuple(rl(s) for s in result.segments if s != "Total")
    segment_primary = {
        rl(s): m1.get(s.split("|", 1)[0], s.split("|", 1)[0])
        for s in result.segments if "|" in s
    }
    return dataclasses.replace(
        result,
        segments=new_segs,
        cells={(cat, rl(seg)): cell for (cat, seg), cell in result.cells.items()
               if seg != "Total"},
        base_n={rl(s): n for s, n in result.base_n.items()},
        segment_primary=segment_primary or None,
        row_summary_keys=tuple(rl(s) for s in result.row_summary_keys),
    )


def _relabel_segments(result: SeriesResult, model: QuestionModel,
                      classifying_var: str) -> SeriesResult:
    """Map segment codes (e.g. "10002") to the classifying variable's value
    labels (e.g. "25-34 vuotias") for display. "Total" is kept; codes without a
    label pass through unchanged."""
    try:
        var = model.variable(classifying_var)
    except Exception:
        return result
    seg_codes = {s for s in result.segments if s != "Total"}
    code_to_label = _code_label_map(var, seg_codes)
    if not code_to_label:
        return result

    def rl(seg: str) -> str:
        return seg if seg == "Total" else code_to_label.get(seg, seg)

    new_segs = tuple(rl(s) for s in result.segments)
    if new_segs == result.segments:
        return result
    new_cells = {(cat, rl(seg)): cell for (cat, seg), cell in result.cells.items()}
    new_base = {rl(s): n for s, n in result.base_n.items()}
    return dataclasses.replace(
        result, segments=new_segs, cells=new_cells, base_n=new_base,
        # The row-summary values are keyed by segment, so their keys are display
        # labels too — otherwise the renderer looks them up by label and finds none.
        row_summary_keys=tuple(rl(s) for s in result.row_summary_keys),
    )


def _combo_two_var(question: Question, spec: ChartSpec, data: pd.DataFrame,
                   model: QuestionModel) -> SeriesResult:
    """Two-variable combo: the question's categories are the shared x-axis; the
    bars are the question's distribution (%), and the line is the MEAN of a
    compatible numeric secondary variable within each category (dual axis). The
    secondary mean is stored in the line segment's ``pct`` field so the existing
    combo renderer (bars=seg0, line=seg1) plots it on the right axis unchanged."""
    var = model.variable(question.variables[0])
    sec_name = spec.options.get("combo_secondary")
    sec = model.variable(sec_name)
    # Primary distribution (%), single series over the question's categories.
    base_spec = dataclasses.replace(
        spec, options={}, classifying_var=None, statistic="pct",
        chart_type="vertical_bar",
    )
    base = _single(question, base_spec, data, model)
    pcol = pd.to_numeric(data[var.name], errors="coerce")
    # Secondary values: map rating codes (e.g. 1000x) to their 1..N scale point
    # via the value-label leading digit; otherwise use the raw numeric value.
    sec_num = pd.to_numeric(data[sec_name], errors="coerce")
    sec_scale = _rating_scale(sec)
    scol = sec_num.map(sec_scale) if sec_scale else sec_num
    label_to_code = {vl.label: vl.value for vl in var.value_labels}
    primary_label = (var.label or var.name)[:30]
    secondary_label = (sec.label or sec.name)[:30]

    cells: dict[tuple[str, str], Cell] = {}
    for cat in base.categories:
        ptot = base.cell(cat, "Total")
        cells[(cat, primary_label)] = Cell(pct=(ptot.pct if ptot else None))
        code = label_to_code.get(cat)
        vals = scol[pcol == code].dropna() if code is not None else scol.iloc[0:0]
        cells[(cat, secondary_label)] = Cell(
            pct=(float(vals.mean()) if len(vals) else None)
        )
    return SeriesResult(
        categories=base.categories,
        segments=(primary_label, secondary_label),
        cells=cells,
        base_n=dict(base.base_n),
        statistic="pct",
    )


def compute(question: Question, spec: ChartSpec, data: pd.DataFrame,
            model: QuestionModel) -> SeriesResult:
    """Compute the SeriesResult for one question + chart spec (R1 spine)."""
    # Two-variable combo: question distribution (bars) + secondary var mean (line).
    if spec.chart_type == "combo" and spec.options.get("combo_secondary"):
        try:
            return _combo_two_var(question, spec, data, model)
        except Exception:
            pass  # fall through to the standard (classifier) combo
    # Task J.1: word-cloud chart type — route to the word-frequency path regardless
    # of question kind. Free-text questions become chartable this way; a wordcloud
    # requested on a non-text question yields no words → clean ValueError/422.
    if spec.chart_type == "wordcloud":
        return _wordcloud(question, spec, data, model)
    # Task G.3: open-ended text questions have no numeric basis — fail early with
    # an actionable message instead of a cryptic float-conversion error downstream.
    qvars = [model.variable(n) for n in question.variables]
    if qvars and all(v.measurement == "text" for v in qvars):
        raise ValueError(TEXT_NOT_CHARTABLE_MSG)
    cv2 = getattr(spec, "classifying_var_2", None)
    if question.kind == "comparison":
        # An explicit comparison overlays its member questions as series — chart-type
        # agnostic (radar draws polygons, a grouped bar draws clusters). Members not in
        # the model are dropped; a lone survivor falls back to its own normal chart.
        members = [model.question(q) for q in question.members if _has_question(model, q)]
        if len(members) >= 2:
            builder = _battery_comparison if members[0].kind == "battery" else _multi_comparison
            return builder(members[0], spec, data, model, members=members)
        if members:
            return compute(members[0], spec, data, model)
        raise ValueError("comparison has no resolvable members")
    # Crossing a BANNER classifier (segments from separate columns, possibly
    # overlapping) with a second variable has no defensible base. The SEPARATE
    # layout never crosses, so it is allowed. This guard lived inside
    # _banner_masks until that became a pure resolver. (spec 2026-08-02 §2.5,
    # 2026-08-04)
    #
    # It sits BELOW the comparison dispatch on purpose: `_multi_comparison` /
    # `_battery_comparison` overlay their member questions as the series and never
    # consult a classifier at all, so a saved comparison slide carrying a leftover
    # banner `classifying_var` + `classifying_var_2` has always computed fine,
    # ignoring both. Guarding above the dispatch made those slides 422 on preview
    # and export blank — a regression on a feature this layout never touched.
    # (2026-08-04 final review, I5)
    if cv2 and not _separate_layout(spec) and _banner_masks(spec, data, model):
        raise ValueError(
            f"'{spec.classifying_var}' is a banner classifier (its segments come "
            f"from separate columns and may overlap) and cannot be combined with a "
            f"second classifying variable ('{cv2}'). Set the two-variable layout to "
            f"Separate panels, remove the second classifier, or classify by an "
            f"ordinary variable instead."
        )
    if question.kind == "battery":
        # A battery shown as a stacked bar is a 100% DISTRIBUTION: each statement
        # is a bar split by the shared rating-scale levels (the source decks'
        # agreement-scale slides). A radar of a battery that has PARALLEL siblings
        # (the same attribute set rated for several entities/brands) compares
        # those entities across the attributes (the source decks' brand-image
        # radar). Otherwise it's the mean-per-statement bars.
        if spec.chart_type in ("stacked_horizontal_bar", "stacked_vertical_bar"):
            result = _battery_stacked(question, spec, data, model)
        elif spec.chart_type == "radar" and len(_parallel_batteries(question, model)) > 1:
            result = _battery_comparison(question, spec, data, model)
        else:
            result = _battery(question, spec, data, model)
    else:
        stat = get_statistic(spec.statistic)   # clear KeyError if unregistered
        if stat.family == "summary":
            result = _summary(question, spec, data, model, stat)
        elif question.kind == "multi":
            # A multi on a radar with PARALLEL siblings (same option set, one per
            # adjective) overlays them as series (the brand-image radar). A lone multi
            # stays a single-series distribution.
            if spec.chart_type == "radar" and len(_parallel_questions(question, model)) > 1:
                result = _multi_comparison(question, spec, data, model)
            else:
                result = _multi(question, spec, data, model)
        else:
            result = _single(question, spec, data, model)
    # Display segment codes as the classifying variable's value labels (a cross-tab
    # of two classifiers joins both labels: "Male · 25-34 vuotias"). The SEPARATE
    # layout already emits display labels, and _relabel_combo_segments would split
    # them on "|" and mangle them. (2026-08-04)
    if _separate_layout(spec):
        pass
    elif spec.classifying_var and cv2:
        result = _relabel_combo_segments(result, model, spec.classifying_var, cv2)
    elif spec.classifying_var:
        result = _relabel_segments(result, model, spec.classifying_var)
    # Resolve whether the "Total" reference series is drawn (ChartSpec.show_total +
    # the percentage direction). Renderers read SeriesResult.show_total. (2026-07-10)
    has_real_classifier = any(s != "Total" for s in result.segments)
    result = dataclasses.replace(result, show_total=resolve_show_total(spec, has_real_classifier))
    return result


def _rating_scale(var: Variable) -> dict[float, float]:
    """Map a rating variable's value codes to their 1..N scale point, parsed from
    the leading integer of each value label ("5 - Vastaa erittäin hyvin" -> 5,
    "3" -> 3). Codes whose label has no leading integer (e.g. "En osaa sanoa")
    are omitted -> treated as no-answer."""
    scale: dict[float, float] = {}
    for vl in var.value_labels:
        m = re.match(r"\s*(\d+)", vl.label or "")
        if m and vl.value not in var.missing_values:
            scale[vl.value] = float(m.group(1))
    return scale


def scale_levels(var: Variable) -> list[tuple[float, str, float]]:
    """Ordered ``(code, label, scale_point)`` for a rating scale — for use where a
    scale is ALREADY asserted (the battery paths / manual battery validation), NOT for
    reclassifying standalone questions.

    Prefers the leading integer of each value label ("5 - Erittäin tärkeä" → 5). When
    the labels are word-only, falls back to the value CODES as the points, provided the
    non-missing codes are a contiguous run of 3..11 integers — so a word-labelled
    importance scale ("Ei lainkaan tärkeä" … "Erittäin tärkeä", coded 1..5) is a real
    scale. Returns ``[]`` when it isn't. (REQ-C-24d)
    """
    pairs = [(vl.value, vl.label or "") for vl in var.value_labels
             if vl.value not in var.missing_values
             and not _is_non_answer_level(vl.label or "")]
    if len(pairs) < 3:
        return []
    # Leading-digit labels → the parsed points (keeps out-of-order SAV codes correct).
    # Uses the digit-labelled points when there are ≥3 (matching _rating_scale, so a
    # scale with a stray non-digit label doesn't regress).
    dpts = [(c, lbl, float(m.group(1)))
            for c, lbl in pairs if (m := re.match(r"\s*(\d+)", lbl))]
    if len(dpts) >= 3:
        return sorted(dpts, key=lambda t: t[2])
    # Word-only labels → the codes ARE the points if they're a contiguous integer run.
    codes = sorted(c for c, _ in pairs)
    if all(float(c).is_integer() for c in codes):
        ints = [int(c) for c in codes]
        if 3 <= len(ints) <= 11 and ints == list(range(ints[0], ints[0] + len(ints))):
            by = {vl.value: (vl.label or "") for vl in var.value_labels}
            return [(float(c), by.get(c, str(int(c))), float(c)) for c in codes]
    return []


def battery_scale_levels(vars_: list[Variable]) -> list[tuple[float, str]]:
    """The shared rating-scale ``(point, label)`` pairs a STACKED battery stacks by,
    ascending by point.

    Members share one scale, so the levels come from the FIRST member with a
    parseable one. Empty when no member has a scale."""
    level_label: dict[float, str] = {}
    for v in vars_:
        lv = scale_levels(v)
        if lv:
            for _code, label, point in lv:
                level_label.setdefault(point, label)
            break
    return [(p, level_label[p]) for p in sorted(level_label)]


def scale_endpoint_gloss(categories) -> str:
    """For a numeric rating scale whose levels read '1 - Täysin eri mieltä' … '7 - Täysin
    samaa mieltä' (bare numbers in the middle), return the endpoint gloss
    '1 = Täysin eri mieltä · 7 = Täysin samaa mieltä' — the wording that moves off the
    (numbers-only) stacked-bar legend into the subtitle. Empty when the categories
    aren't such a scale, or neither endpoint carries a description."""
    cats = [str(c) for c in categories]
    if len(cats) < 3:
        return ""
    parsed = []
    for c in cats:
        m = re.match(r"\s*(\d+)\s*[-–:.)]?\s*(.*)", c)
        if not m:
            return ""  # a non-numeric level → not a numeric scale
        parsed.append((m.group(1), m.group(2).strip()))
    ends = [f"{n} = {desc}" for n, desc in (parsed[0], parsed[-1]) if desc]
    return " · ".join(ends)


def _drop_empty_segments(seg_masks, vars_: list[Variable], data: pd.DataFrame):
    """Remove segments in which NOBODY answered this battery.

    Some studies ask each path its own variable set (Houkuttelevuus_1 for path 1,
    Houkuttelevuus_2 for path 2), so cross-tabbing one of those batteries by the
    path leaves the other path with no data. Drawing blank bars for it is noise;
    `_multi` already skips empty segments the same way. (spec 2026-08-02 §2.4)"""
    if not seg_masks:
        return seg_masks
    answered = pd.Series(False, index=data.index)
    for v in vars_:
        scale = {c: p for c, _lbl, p in scale_levels(v)}
        answered = answered | pd.to_numeric(
            data[v.name], errors="coerce").map(scale).notna()
    kept = {lbl: m for lbl, m in seg_masks.items() if bool((answered & m).any())}
    return kept or None


def _battery(question: Question, spec: ChartSpec, data: pd.DataFrame,
             model: QuestionModel) -> SeriesResult:
    """A rating battery: one bar per member (category), value = the MEAN rating
    on the members' shared 1..N scale (no-answer codes excluded). Members were
    relabelled to their category by the battery grouper, so category == label.

    With a classifying variable each member gets one bar PER SEGMENT — the natural
    clustered shape — so a concept test can compare the paths on every attribute.
    (spec 2026-08-02 §2.4)"""
    vars_ = [model.variable(n) for n in question.variables]
    overrides = spec.label_override_map() if hasattr(spec, "label_override_map") else {}
    seg_masks = _drop_empty_segments(
        _classifier_masks(spec, data, model), vars_, data)
    # Always compute the Total column; resolve_show_total decides whether it's drawn.
    all_mask = pd.Series(True, index=data.index)
    segs: dict[str, pd.Series] = dict(seg_masks or {})
    segs["Total"] = all_mask

    cells: dict[tuple[str, str], Cell] = {}
    rows = []
    answered_any = pd.Series(False, index=data.index)
    base_by_seg: dict[str, int] = {}
    for idx, v in enumerate(vars_):
        display = overrides.get(v.label, v.label)
        scale = {c: p for c, _lbl, p in scale_levels(v)}
        mapped = pd.to_numeric(data[v.name], errors="coerce").map(scale)
        answered_any = answered_any | mapped.notna()
        for seg, mask in segs.items():
            sub = mapped[mask]
            n = int(sub.notna().sum())
            mean = float(sub.mean()) if n > 0 else None
            cells[(display, seg)] = Cell(pct=None, count=float(n), mean=mean)
        # Sorting keys come from the Total column so the category order is stable
        # however the segments differ.
        tot = cells[(display, "Total")]
        key = tot.mean if tot.mean is not None else 0.0
        rows.append((display, float(idx),
                     {"pct": key, "count": tot.count, "mean": key,
                      "data_index": idx, "topbox": key}))

    for seg, mask in segs.items():
        base_by_seg[seg] = int((answered_any & mask).sum())
    categories = tuple(sort_categories(rows, spec.sort))
    segments = (*(s for s in segs if s != "Total"), "Total")
    return SeriesResult(categories=categories, segments=segments, cells=cells,
                        base_n=base_by_seg, statistic="mean")


def _has_question(model: QuestionModel, qid: str) -> bool:
    return any(q.qid == qid for q in model.questions)


def _parallel_questions(question: Question, model: QuestionModel) -> list[Question]:
    """All questions of the SAME kind (including *question*) whose member CATEGORY
    label-set is identical — the parallel series a comparison overlays:
      - batteries sharing the same ATTRIBUTE set (a rating grid across entities/brands);
      - multis sharing the same OPTION set (an adjective grid across services).
    EXACT, order-independent set match (conservative — only auto-overlay questions that
    truly share the axes)."""
    if question.kind not in ("battery", "multi"):
        return [question]

    def catset(q: Question) -> frozenset:
        return frozenset(model.variable(v).label for v in q.variables)

    target = catset(question)
    sibs = [
        q for q in model.questions
        if q.kind == question.kind and catset(q) == target
    ]
    return sibs or [question]


def _parallel_batteries(question: Question, model: QuestionModel) -> list[Question]:
    """Backward-compatible alias — parallel questions for a battery (brand-image radar)."""
    return _parallel_questions(question, model)


def _entity_label(question: Question) -> str:
    """A short entity (brand) label for a battery, taken from the lead-in before
    the question prompt: 'Attendo — Arvioi …' -> 'Attendo'."""
    text = (question.text or "").strip()
    for sep in (" — ", " – ", " - ", ": ", ":"):
        if sep in text:
            head = text.split(sep, 1)[0].strip()
            if head:
                return head
    return question.qid.replace("battery-", "").replace("-", " ").title()


def _battery_comparison(question: Question, spec: ChartSpec, data: pd.DataFrame,
                        model: QuestionModel, members: list[Question] | None = None) -> SeriesResult:
    """Compare PARALLEL rating batteries (same attributes, one per entity/brand):
    categories = the shared attributes, segments = the entities, each cell the
    MEAN rating of that entity on that attribute (shared 1..N scale). Mirrors the
    source decks' brand-image radar (attributes × brands). `members` (explicit series)
    overrides the `_parallel_batteries` auto-detect when given."""
    sibs = members if members is not None else _parallel_batteries(question, model)
    overrides = spec.label_override_map() if hasattr(spec, "label_override_map") else {}
    raw_attrs = [model.variable(v).label for v in question.variables]   # canonical order
    attrs = [overrides.get(a, a) for a in raw_attrs]                    # display labels
    cells: dict[tuple[str, str], Cell] = {}
    base_n: dict[str, int] = {}
    entities: list[str] = []
    for q in sibs:
        ent = _series_label(q, sibs)
        entities.append(ent)
        by_label = {overrides.get(lbl, lbl): v for v, lbl in
                    ((v, model.variable(v).label) for v in q.variables)}
        answered = pd.Series(False, index=data.index)
        for attr in attrs:
            vn = by_label.get(attr)
            if vn is None:
                cells[(attr, ent)] = Cell(pct=None, count=0.0, mean=None)
                continue
            scale = {c: p for c, _lbl, p in scale_levels(model.variable(vn))}
            mapped = pd.to_numeric(data[vn], errors="coerce").map(scale)
            answered = answered | mapped.notna()
            n = int(mapped.notna().sum())
            cells[(attr, ent)] = Cell(
                pct=None, count=float(n),
                mean=float(mapped.mean()) if n > 0 else None,
            )
        base_n[ent] = int(answered.sum())
    base_n["Total"] = max(base_n.values(), default=0)
    return SeriesResult(categories=tuple(attrs), segments=tuple(entities),
                        cells=cells, base_n=base_n, statistic="mean")


_AFFIX_SEPS = " -–—:·,;/|"   # space, hyphen, en/em dash, colon, middot, …


def _series_label(question: Question, group: list[Question]) -> str:
    """The DISTINGUISHING part of a parallel question's text vs its siblings: strip the
    COMMON prefix AND suffix shared by the whole group, each rounded to a separator so a
    word is never cut. This ONE rule unifies both kinds — battery (entity at the HEAD,
    "Attendo — Arvioi X" → "Attendo") and multi (adjective at the TAIL,
    "… -Rohkea" → "Rohkea"). Falls back to `_entity_label` / full text when there
    is no clean common part."""
    me = (question.text or "").strip()
    texts = [(q.text or "").strip() for q in group]
    if len(texts) < 2:
        return _entity_label(question)
    pre = os.path.commonprefix(texts)
    suf = os.path.commonprefix([t[::-1] for t in texts])[::-1]
    while pre and pre[-1] not in _AFFIX_SEPS:   # round prefix back to a separator
        pre = pre[:-1]
    while suf and suf[0] not in _AFFIX_SEPS:     # round suffix forward to a separator
        suf = suf[1:]
    core = me[len(pre): len(me) - len(suf)] if len(pre) + len(suf) < len(me) else ""
    core = core.strip(_AFFIX_SEPS).strip()
    return core or _entity_label(question)


def _multi_comparison(question: Question, spec: ChartSpec, data: pd.DataFrame,
                      model: QuestionModel, members: list[Question] | None = None) -> SeriesResult:
    """Compare PARALLEL multi-response questions (same option set, one per adjective):
    categories = the shared OPTIONS (services, the axes), segments = the questions
    (adjectives, the polygons), each cell the % of respondents who ticked that option for
    that adjective. The multi twin of `_battery_comparison`. `members` (explicit series)
    overrides the `_parallel_questions` auto-detect when given."""
    sibs = members if members is not None else _parallel_questions(question, model)
    overrides = spec.label_override_map() if hasattr(spec, "label_override_map") else {}
    raw_options = [model.variable(v).label for v in question.variables]  # this q's axis order
    options = [overrides.get(o, o) for o in raw_options]                 # display labels
    cells: dict[tuple[str, str], Cell] = {}
    base_n: dict[str, int] = {}
    segments: list[str] = []
    seen: dict[str, int] = {}
    for q in sibs:
        label = _series_label(q, sibs)
        if label in seen:                     # disambiguate a repeated series label
            seen[label] += 1
            label = f"{label} ({seen[label]})"
        else:
            seen[label] = 1
        segments.append(label)
        by_label = {overrides.get(lbl, lbl): v for v, lbl in
                    ((v, model.variable(v).label) for v in q.variables)}
        base = multi_base(data, [model.variable(v) for v in q.variables])
        for opt in options:
            vn = by_label.get(opt)
            if vn is None:                    # this adjective lacks this option → empty cell
                cells[(opt, label)] = Cell(pct=None, count=0.0, mean=None)
                continue
            v = model.variable(vn)
            s = pd.to_numeric(data[vn], errors="coerce")
            c = int(((s == 1.0) & ~s.isin(v.missing_values)).sum())
            cells[(opt, label)] = Cell(pct=pct(c, base, spec.number_format),
                                       count=count_value(c, spec.number_format), mean=None)
        base_n[label] = base
    base_n["Total"] = max(base_n.values(), default=0)
    return SeriesResult(categories=tuple(options), segments=tuple(segments),
                        cells=cells, base_n=base_n, statistic="pct")


def _compute_row_summaries(spec, statements, levels, points, cells,
                           scale_levels=None, scale_points=None):
    """One summary value per statement (bar) for the right-hand row-summary column,
    or None when the feature is off. `levels` are the stack labels in ascending
    `points` order; `points[i]` is the numeric scale value of `levels[i]`;
    `cells[(level, stmt)].pct` is the % of that level for that statement. Aligned to
    `statements` (the bars). (spec 2026-07-07-row-summary-column)

    `scale_levels`/`scale_points` are the subset that lies on the rating scale, in
    scale order — which is what "top 2" and the mean are about. They differ from
    `levels` when a rendered level is not a scale point ("En osaa sanoa") or when
    the file's order is not the scale's. Defaults to `levels`/`points` for callers
    whose levels are already exactly the scale. (review 2026-08-24)"""
    fn = getattr(spec, "row_summary_fn", "none")
    if fn == "none" or not levels or not statements:
        return None
    scale_levels = levels if scale_levels is None else scale_levels
    scale_points = points if scale_points is None else scale_points
    label_by_point = {p: lbl for p, lbl in zip(points, levels)}

    def cell_pct(lvl, stmt):
        c = cells.get((lvl, stmt))
        return (c.pct or 0.0) if c else 0.0

    def picked(codes):
        return [label_by_point[p] for p in codes if p in label_by_point]

    nf = spec.number_format
    decimals = nf.mean_decimals if fn == "mean" else nf.pct_decimals
    out = []
    for stmt in statements:
        if fn in _BOX_ROW_SUMMARIES:
            n_top, _lowest = _BOX_ROW_SUMMARIES[fn]
            picked_levels = (scale_levels[:n_top] if _lowest
                             else scale_levels[-n_top:])
            val = sum(cell_pct(l, stmt) for l in picked_levels)
        elif fn == "sum":
            val = sum(cell_pct(l, stmt) for l in picked(spec.row_summary_codes))
        elif fn == "net":
            val = (sum(cell_pct(l, stmt) for l in picked(spec.row_summary_pos_codes))
                   - sum(cell_pct(l, stmt) for l in picked(spec.row_summary_neg_codes)))
        elif fn == "mean":
            num = sum(p * cell_pct(lbl, stmt)
                      for p, lbl in zip(scale_points, scale_levels))
            den = sum(cell_pct(lbl, stmt) for lbl in scale_levels)
            val = (num / den) if den else 0.0
        else:
            val = 0.0
        out.append(round(val, decimals))
    return tuple(out)


def _battery_stacked(question: Question, spec: ChartSpec, data: pd.DataFrame,
                     model: QuestionModel) -> SeriesResult:
    """A rating battery rendered as a 100%-STACKED distribution.

    Each member statement becomes a BAR; the stack SEGMENTS are the shared
    rating-scale levels (1..N, e.g. 'Täysin eri mieltä' … 'Täysin samaa mieltä'),
    each cell the % of that statement's answers at that level. The stacked
    renderer consumes this as categories = levels (stack), segments = statements
    (bars). Mirrors the source decks' agreement-scale slides.
    """
    vars_ = [model.variable(n) for n in question.variables]
    # Shared scale levels from the first member with a parseable scale (digit- OR
    # word-labelled, via scale_levels).
    scale_pts = battery_scale_levels(vars_)            # [(point, label)], 1..N ascending
    points = [p for p, _lbl in scale_pts]
    levels = [lbl for _p, lbl in scale_pts]            # stack-segment labels
    # Bar labels (member order), honouring the author's category-label overrides —
    # the editor lists the member labels, so a shortened label must reach the bars.
    overrides = spec.label_override_map() if hasattr(spec, "label_override_map") else {}
    statements = [overrides.get(v.label, v.label) for v in vars_]

    # Optional split by a classifying variable. Statement x level x segment is three
    # dimensions and a SeriesResult holds two, so a segment turns each statement into
    # several BARS labelled "<statement> · <segment>"; `segment_primary` then groups
    # them by statement, putting the paths adjacent — the comparison a concept test
    # exists to make. (spec 2026-08-02 §2.4)
    seg_masks = _drop_empty_segments(
        _classifier_masks(spec, data, model), vars_, data)
    all_mask = pd.Series(True, index=data.index)
    seg_items = list((seg_masks or {}).items()) or [(None, all_mask)]

    cells: dict[tuple[str, str], Cell] = {}
    base_by_bar: dict[str, int] = {}
    segment_primary: dict[str, str] = {}
    bars: list[str] = []
    answered_any = pd.Series(False, index=data.index)
    for v, stmt in zip(vars_, statements):
        scale = {c: p for c, _lbl, p in scale_levels(v)}
        mapped = pd.to_numeric(data[v.name], errors="coerce").map(scale)
        answered_any = answered_any | mapped.notna()
        for seg_label, mask in seg_items:
            bar = stmt if seg_label is None else f"{stmt} · {seg_label}"
            bars.append(bar)
            if seg_label is not None:
                segment_primary[bar] = stmt
            sub = mapped[mask]
            n = int(sub.notna().sum())
            base_by_bar[bar] = n
            vc = sub.value_counts()
            # Largest-remainder so each bar's scale levels sum to exactly 100 %.
            counts_l = [int(vc.get(p, 0)) for p in points]
            pcts_l = largest_remainder(counts_l, n, spec.number_format.pct_decimals)
            for lbl, c, pv in zip(levels, counts_l, pcts_l):
                cells[(lbl, bar)] = Cell(pct=pv, count=float(c), mean=None)

    # "Top 2/3 sum" sort: order the statement bars by their summed two (or three) highest
    # scale levels (e.g. 4+5), descending — so the most-"agree" statement leads. Auto-
    # derives the top-N from the scale, so it works for any N. (REQ-S-04)
    # With a split, statements are reordered as a BLOCK (ranked by their Total) so the
    # per-statement groups stay intact.
    if spec.sort.basis in _BOX_SORT_BASES and len(levels) >= 2:
        n_top, _lowest = _BOX_SORT_BASES[spec.sort.basis]
        # `levels` runs low -> high, so one end is a head slice and the other a tail.
        top = levels[:n_top] if _lowest else levels[-n_top:]

        def _topbox(bar: str) -> float:
            return sum((cells[(lvl, bar)].pct or 0.0) for lvl in top)

        if segment_primary:
            by_stmt: dict[str, list[str]] = {}
            for bar in bars:
                by_stmt.setdefault(segment_primary[bar], []).append(bar)
            order = sorted(by_stmt,
                           key=lambda s: sum(_topbox(b) for b in by_stmt[s]) / len(by_stmt[s]),
                           reverse=spec.sort.descending)
            bars = [b for s in order for b in by_stmt[s]]
        else:
            bars = sorted(bars, key=_topbox, reverse=spec.sort.descending)

    base_n = {"Total": int(answered_any.sum()), **base_by_bar}
    return SeriesResult(
        categories=tuple(levels), segments=tuple(bars),
        cells=cells, base_n=base_n, statistic="pct",
        # NOT segment_primary: the cross-tab grouping draws the primary as a ROTATED
        # label beside the axis, which assumes short values ("Mies"/"Nainen"). A
        # battery's primary is a full statement, and rendering those rotated smears
        # them together and crushes the plot. The statement-major ORDER already puts
        # each statement's segments adjacent, and every bar keeps its own readable
        # "<statement> · <segment>" tick. (spec 2026-08-02 §2.4)
        row_summaries=_compute_row_summaries(spec, bars, levels, points, cells),
        row_summary_keys=tuple(bars),
    )
