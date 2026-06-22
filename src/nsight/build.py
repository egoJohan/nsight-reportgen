"""Deterministic SlideFill builder + brief->template preflight.

Numbers come ONLY from this builder / tabulate. The LLM narrator never produces a
number that lands in a chart.
"""

from __future__ import annotations

import pandas as pd

from nsight.brief import SlideJob
from nsight.render.renderer import ChartFill, SlideFill, TextFill
from nsight.render.template import Template
from nsight.segments import segment_mask
from nsight.tabulate import (
    awareness_by_brand,
    spontaneous_any_mention,
    top_of_mind_patterns,
)


def build_slidefill(
    job: SlideJob,
    frame: pd.DataFrame,
    *,
    brand_vars: dict[str, str],
    weight: str | None,
    key_message: str | None = None,
) -> SlideFill:
    mask = segment_mask(job.segment, frame)
    seg = frame[mask]

    sf = SlideFill(slide_idx=job.slide_idx)

    if job.metric == "aided_awareness":
        chart = job.chart or {}
        brands = chart.get("brands") or list(brand_vars.keys())
        res = awareness_by_brand(
            seg,
            brand_vars={b: brand_vars[b] for b in brands},
            positive_values=[1.0],
            weight=weight,
        )
        sf.charts.append(
            ChartFill(
                name=chart["name"],
                categories=None,
                series=None,
                series_name=chart["series_name"],
                values_by_category={b: res[b].pct / 100.0 for b in brands},
                occurrence=chart.get("occurrence", 0),
            )
        )
    elif job.metric == "general_opinion":
        # 5 opinion-level series across 2 categories (private / public). Emit one
        # ChartFill per series, each setting both category proportions.
        from nsight.attendo_bindings import (
            OPINION_PRIVATE_VAR,
            OPINION_PUBLIC_VAR,
            OPINION_SERIES_CODES,
        )

        chart = job.chart or {}
        private_cat = chart["private_category"]
        public_cat = chart["public_category"]
        priv = pd.to_numeric(frame[OPINION_PRIVATE_VAR], errors="coerce")
        pub = pd.to_numeric(frame[OPINION_PUBLIC_VAR], errors="coerce")
        priv_total = priv.notna().sum()
        pub_total = pub.notna().sum()
        for series_name, code in OPINION_SERIES_CODES.items():
            p = round((priv == code).sum() / priv_total, 2) if priv_total else 0.0
            q = round((pub == code).sum() / pub_total, 2) if pub_total else 0.0
            sf.charts.append(
                ChartFill(
                    name=chart["name"],
                    series_name=series_name,
                    values_by_category={private_cat: p, public_cat: q},
                    occurrence=chart.get("occurrence", 0),
                )
            )

    elif job.metric == "spontaneous_awareness":
        # Two-series chart: "Top of mind" (first mention) and "Kaikki" (any mention).
        from nsight.attendo_bindings import (
            SPONTANEOUS_FIRST_VAR,
            SPONTANEOUS_MENTION_VARS,
            SPONTANEOUS_PATTERNS,
        )

        chart = job.chart or {}
        brands = chart.get("brands") or list(SPONTANEOUS_PATTERNS.keys())
        tom_series = chart.get("tom_series", "Top of mind")
        any_series = chart.get("any_series", "Kaikki")
        tom_vals: dict[str, float] = {}
        any_vals: dict[str, float] = {}
        for b in brands:
            pats = SPONTANEOUS_PATTERNS[b]
            tom_vals[b] = top_of_mind_patterns(
                seg, first_mention_var=SPONTANEOUS_FIRST_VAR, patterns=pats, weight=weight
            ).pct / 100.0
            any_vals[b] = spontaneous_any_mention(
                seg, mention_vars=SPONTANEOUS_MENTION_VARS, patterns=pats, weight=weight
            ).pct / 100.0
        sf.charts.append(
            ChartFill(
                name=chart["name"],
                series_name=tom_series,
                values_by_category=tom_vals,
                occurrence=chart.get("occurrence", 0),
            )
        )
        sf.charts.append(
            ChartFill(
                name=chart["name"],
                series_name=any_series,
                values_by_category=any_vals,
                occurrence=chart.get("occurrence", 0),
            )
        )

    elif job.metric == "image_words":
        # Brand-image spontaneous words: regenerate the current-wave TOP-10 word
        # list (pure tabulation; no LLM). The deck lays each wave out as a single
        # rounded-rectangle text box whose first paragraphs are a "TOP 10" header +
        # wave label + blank line, followed by one paragraph per word formatted
        # "Word (count)". We rewrite only the word paragraphs (from `start`).
        from nsight.attendo_bindings import (
            IMAGE_SYNONYMS,
            IMAGE_WORD_VARS,
        )
        from nsight.coding import top_words

        spec = job.raw.get("words") or {}
        top_n = int(spec.get("top_n", 10))
        start = int(spec.get("start", 3))
        words = top_words(
            seg, text_vars=IMAGE_WORD_VARS, top_n=top_n, synonyms=IMAGE_SYNONYMS
        )
        lines = [f"{word.capitalize()} ({count})" for word, count in words]
        sf.texts.append(
            TextFill(
                name=spec["name"],
                lines=lines,
                start=start,
                occurrence=spec.get("occurrence", 0),
            )
        )

    else:
        raise ValueError(f"unknown metric: {job.metric!r}")

    if job.key_message and key_message is not None:
        sf.texts.append(
            TextFill(
                name=job.key_message["name"],
                value=key_message,
                occurrence=job.key_message.get("occurrence", 0),
            )
        )

    return sf


def preflight(jobs: list[SlideJob], template: Template) -> list[str]:
    """Resolve every chart/table/key_message shape; return KeyError messages."""
    errors: list[str] = []
    for job in jobs:
        for spec in (job.chart, job.table, job.key_message, job.raw.get("words")):
            if not spec:
                continue
            try:
                template.shape(
                    slide_idx=job.slide_idx,
                    name=spec["name"],
                    occurrence=spec.get("occurrence", 0),
                )
            except KeyError as exc:
                errors.append(f"[{job.id}] {exc}")
    return errors
