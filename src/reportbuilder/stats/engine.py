"""Statistics-engine orchestrator: compute(question, spec, data, model) -> SeriesResult.

Ties together aggregate_counts, base rules, statistics helpers, and sort into the
SeriesResult — the spine output (R1). REQ-C-14/15/16, M-03.
"""
from __future__ import annotations
import collections
import dataclasses
import re
import pandas as pd
from reportbuilder.model.question import Question, QuestionModel, Variable
from reportbuilder.model.report import ChartSpec, SortSpec
from reportbuilder.stats.aggregate import aggregate_counts
from reportbuilder.stats.base_rules import single_base, multi_base, segment_bases
from reportbuilder.stats.registry import statistic as get_statistic
from reportbuilder.stats.series import Cell, SeriesResult
from reportbuilder.stats.sorting import sort_categories
from reportbuilder.stats.statistics import pct, count_value, summary_value
# Import statistics module to trigger built-in registrations
import reportbuilder.stats.statistics  # noqa: F401

# Label used for the aggregated missing-values bucket (REQ-D-06, MV).
# Module constant so it can be imported by tests and localised in future.
NOT_ANSWERED_LABEL: str = "Not answered"


def _seg_key(code: float) -> str:
    """Segment key for a classifier code — matches segment_bases' formatting."""
    return str(int(code)) if float(code).is_integer() else str(code)


def _combo_segmentation(spec: ChartSpec, data: pd.DataFrame):
    """Cross-tab segmentation for TWO classifiers → (seg_series, ordered_keys).

    Returns (None, None) unless both `classifying_var` and `classifying_var_2` are
    set. The combo key is "<code1>|<code2>"; a row missing EITHER classifier is
    excluded (None). `ordered_keys` is numeric primary-major so the first
    classifier clusters (Male·Young, Male·Old, … Female·…). (REQ-C-14b)
    """
    cv1 = spec.classifying_var
    cv2 = getattr(spec, "classifying_var_2", None)
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
    seg_series, ordered = _combo_segmentation(spec, data)
    if seg_series is not None or spec.classifying_var:
        if seg_series is not None:                   # cross-tab: two classifiers
            bases = segment_bases(data, var, seg_series=seg_series)
            segments = (*ordered, "Total")
        else:
            bases = segment_bases(data, var, spec.classifying_var)
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
                    *, seg_series: pd.Series | None = None) -> dict[str, int]:
    """Count sysmis + "not answered" rows per segment using the effective set.

    Returns a dict of {segment_label: count}. Always includes "Total".
    For segmented data the per-segment count only considers rows whose
    classifying variable has a valid (non-NaN) code — consistent with the
    segment_bases convention. (REQ-D-06, REQ-MV-01, REQ-MV-02)
    """
    s = pd.to_numeric(data[var.name], errors="coerce")
    missing_mask = s.isna() | s.isin(eff)
    result: dict[str, int] = {"Total": int(missing_mask.sum())}
    if seg_series is not None:
        for key in seg_series.dropna().unique():
            result[str(key)] = int((missing_mask & (seg_series == key)).sum())
    elif classifying_var is not None:
        seg = pd.to_numeric(data[classifying_var], errors="coerce")
        for code in sorted(seg.dropna().unique()):
            seg_label = str(int(code)) if float(code).is_integer() else str(code)
            result[seg_label] = int((missing_mask & (seg == code)).sum())
    return result


def _single(question: Question, spec: ChartSpec, data: pd.DataFrame,
            model: QuestionModel) -> SeriesResult:
    var = model.variable(question.variables[0])
    eff = _effective_missing(spec, var)
    overrides = spec.label_override_map() if hasattr(spec, "label_override_map") else {}
    show_empty: bool = getattr(spec, "show_empty_categories", True)
    labels = {vl.value: vl.label for vl in var.value_labels
              if vl.value not in eff}
    seg_series, ordered = _combo_segmentation(spec, data)
    if seg_series is not None:                       # cross-tab: two classifiers
        bases = segment_bases(data, var, missing_override=eff, seg_series=seg_series)
        counts = aggregate_counts(data, var.name, seg_series=seg_series)
        segments = (*ordered, "Total")
    elif spec.classifying_var:
        bases = segment_bases(data, var, spec.classifying_var, missing_override=eff)
        counts = aggregate_counts(data, var.name, spec.classifying_var)
        segments = tuple(s for s in bases if s != "Total")
        segments = (*segments, "Total") if segments else ("Total",)
    else:
        bases = {"Total": single_base(data, var, missing_override=eff)}
        counts = aggregate_counts(data, var.name, spec.classifying_var)
        segments = ("Total",)

    # When show_not_answered is True, recompute over total (valid + missing). (REQ-D-06, MV)
    show_na: bool = getattr(spec, "show_not_answered", False)
    if show_na:
        missing_n = _missing_counts(data, var, eff, spec.classifying_var,
                                    seg_series=seg_series)
        denom = {seg: bases.get(seg, 0) + missing_n.get(seg, 0) for seg in segments}
    else:
        denom = {seg: bases.get(seg, 0) for seg in segments}

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
    else:
        rating = _rating_scale(var)
        is_rating = len(rating) >= max(3, len(labels) - 1)
        entries = [
            (code, overrides.get(label, label),
             float(rating.get(code, 1000 + idx) if is_rating else idx))
            for idx, (code, label) in enumerate(labels.items())
        ]

    cells: dict[tuple[str, str], Cell] = {}
    rows = []
    for code, display, data_index in entries:
        for seg in segments:
            c = counts.get((code, seg), 0)
            base = denom.get(seg, 0)
            cells[(display, seg)] = Cell(pct=pct(c, base, spec.number_format),
                                         count=count_value(c, spec.number_format),
                                         mean=None)
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
    sort_spec = SortSpec(basis="data_order") if scale_entries is not None else spec.sort
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
                cells[(na_display, seg)] = Cell(
                    pct=pct(mc, base, spec.number_format),
                    count=count_value(mc, spec.number_format),
                    mean=None,
                )
            categories.append(na_display)

    return SeriesResult(categories=tuple(categories), segments=segments, cells=cells,
                        base_n={s: denom.get(s, 0) for s in segments},
                        statistic=spec.statistic, caption=scale_caption)


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
    base = multi_base(data, vars_)
    cells: dict[tuple[str, str], Cell] = {}
    rows = []
    for idx, v in enumerate(vars_):
        display = overrides.get(v.label, v.label)
        s = pd.to_numeric(data[v.name], errors="coerce")
        c = int(((s == 1.0) & ~s.isin(v.missing_values)).sum())
        cells[(display, "Total")] = Cell(pct=pct(c, base, spec.number_format),
                                         count=count_value(c, spec.number_format), mean=None)
        cell = cells[(display, "Total")]
        rows.append((display, float(idx), {"pct": cell.pct, "count": cell.count,
                                           "mean": 0.0, "data_index": idx, "topbox": cell.pct}))

    # Hide members whose DISPLAYED value rounds to 0 when show_empty is False. (Task G.4)
    if not show_empty:
        rows = _drop_displayed_zero_rows(
            rows, cells, ("Total",), spec.statistic, spec.number_format
        )

    categories = tuple(sort_categories(rows, spec.sort))
    return SeriesResult(categories=categories, segments=("Total",), cells=cells,
                        base_n={"Total": base}, statistic=spec.statistic)


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
        result, segments=new_segs, cells=new_cells, base_n=new_base
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
            result = _multi(question, spec, data, model)
        else:
            result = _single(question, spec, data, model)
    # Display segment codes as the classifying variable's value labels (a cross-tab
    # of two classifiers joins both labels: "Male · 25-34 vuotias").
    if spec.classifying_var and getattr(spec, "classifying_var_2", None):
        result = _relabel_combo_segments(
            result, model, spec.classifying_var, spec.classifying_var_2)
    elif spec.classifying_var:
        result = _relabel_segments(result, model, spec.classifying_var)
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
             if vl.value not in var.missing_values]
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


def _battery(question: Question, spec: ChartSpec, data: pd.DataFrame,
             model: QuestionModel) -> SeriesResult:
    """A rating battery: one bar per member (category), value = the MEAN rating
    on the members' shared 1..N scale (no-answer codes excluded). Members were
    relabelled to their category by the battery grouper, so category == label."""
    vars_ = [model.variable(n) for n in question.variables]
    cells: dict[tuple[str, str], Cell] = {}
    rows = []
    answered_any = pd.Series(False, index=data.index)
    for idx, v in enumerate(vars_):
        scale = {c: p for c, _lbl, p in scale_levels(v)}
        s = pd.to_numeric(data[v.name], errors="coerce")
        mapped = s.map(scale)
        answered_any = answered_any | mapped.notna()
        n = int(mapped.notna().sum())
        mean = float(mapped.mean()) if n > 0 else None
        cells[(v.label, "Total")] = Cell(pct=None, count=float(n), mean=mean)
        key = mean if mean is not None else 0.0
        rows.append((v.label, float(idx),
                     {"pct": key, "count": n, "mean": key, "data_index": idx, "topbox": key}))

    base = int(answered_any.sum())
    categories = tuple(sort_categories(rows, spec.sort))
    return SeriesResult(categories=categories, segments=("Total",), cells=cells,
                        base_n={"Total": base}, statistic="mean")


def _parallel_batteries(question: Question, model: QuestionModel) -> list[Question]:
    """All batteries (including *question*) whose member ATTRIBUTE LABEL-SET is
    identical — i.e. the same rating grid asked for several entities/brands.

    These are exactly what a brand-image radar compares across entities. Matching
    is by the SET of member labels (order-independent), so the batteries don't
    need their attributes in the same column order."""
    if question.kind != "battery":
        return [question]
    target = frozenset(model.variable(v).label for v in question.variables)
    sibs = [
        q for q in model.questions
        if q.kind == "battery"
        and frozenset(model.variable(v).label for v in q.variables) == target
    ]
    return sibs or [question]


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
                        model: QuestionModel) -> SeriesResult:
    """Compare PARALLEL rating batteries (same attributes, one per entity/brand):
    categories = the shared attributes, segments = the entities, each cell the
    MEAN rating of that entity on that attribute (shared 1..N scale). Mirrors the
    source decks' brand-image radar (attributes × brands)."""
    sibs = _parallel_batteries(question, model)
    attrs = [model.variable(v).label for v in question.variables]   # canonical order
    cells: dict[tuple[str, str], Cell] = {}
    base_n: dict[str, int] = {}
    entities: list[str] = []
    for q in sibs:
        ent = _entity_label(q)
        entities.append(ent)
        by_label = {model.variable(v).label: v for v in q.variables}
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
    level_label: dict[float, str] = {}
    for v in vars_:
        lv = scale_levels(v)
        if lv:
            for _code, label, point in lv:
                level_label.setdefault(point, label)
            break
    points = sorted(level_label)                       # 1..N ascending
    levels = [level_label[p] for p in points]          # stack-segment labels
    statements = [v.label for v in vars_]              # bar labels (member order)

    cells: dict[tuple[str, str], Cell] = {}
    base_by_stmt: dict[str, int] = {}
    answered_any = pd.Series(False, index=data.index)
    for v in vars_:
        scale = {c: p for c, _lbl, p in scale_levels(v)}
        mapped = pd.to_numeric(data[v.name], errors="coerce").map(scale)
        answered_any = answered_any | mapped.notna()
        n = int(mapped.notna().sum())
        base_by_stmt[v.label] = n
        vc = mapped.value_counts()
        for p, lbl in zip(points, levels):
            c = int(vc.get(p, 0))
            cells[(lbl, v.label)] = Cell(
                pct=pct(c, n, spec.number_format), count=float(c), mean=None
            )

    # "Top 2 sum" sort: order the statement bars by their summed two highest scale
    # levels (e.g. 4+5), descending — so the most-"agree" statement leads. Auto-
    # derives the top-2 from the scale, so it works for any N. (REQ-S-04)
    if spec.sort.basis == "topbox_sum" and len(levels) >= 2:
        top2 = levels[-2:]
        statements = sorted(
            statements,
            key=lambda stmt: sum((cells[(lvl, stmt)].pct or 0.0) for lvl in top2),
            reverse=spec.sort.descending,
        )

    base_n = {"Total": int(answered_any.sum()), **base_by_stmt}
    return SeriesResult(categories=tuple(levels), segments=tuple(statements),
                        cells=cells, base_n=base_n, statistic="pct")
