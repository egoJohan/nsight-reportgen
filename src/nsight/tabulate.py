from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ShareResult:
    pct: float
    n: int
    raw: float


@dataclass(frozen=True)
class PerceptionResult:
    positive: float
    neutral: float
    negative: float
    n: int


def _valid(frame: pd.DataFrame, var: str, weight: str | None):
    s = pd.to_numeric(frame[var], errors="coerce")
    w = pd.to_numeric(frame[weight], errors="coerce") if weight else pd.Series(1.0, index=frame.index)
    valid = s.notna() & w.notna()
    return s[valid], w[valid]


def share(frame: pd.DataFrame, *, var: str, positive_values: list[float],
          weight: str | None = None) -> ShareResult:
    s, w = _valid(frame, var, weight)
    total = w.sum()
    hit = w[s.isin(positive_values)].sum()
    raw = (hit / total * 100.0) if total else 0.0
    return ShareResult(pct=round(raw), n=int(s.shape[0]), raw=raw)


def perception_split(frame: pd.DataFrame, *, var: str, positive: list[float],
                     neutral: list[float], negative: list[float],
                     weight: str | None = None) -> PerceptionResult:
    s, w = _valid(frame, var, weight)
    total = w.sum()
    def pct(codes): return round(w[s.isin(codes)].sum() / total * 100.0) if total else 0.0
    return PerceptionResult(positive=pct(positive), neutral=pct(neutral),
                            negative=pct(negative), n=int(s.shape[0]))


def awareness_by_brand(frame: pd.DataFrame, *, brand_vars: dict[str, str],
                       positive_values: list[float] | None = None,
                       weight: str | None = None) -> dict[str, ShareResult]:
    pos = positive_values or [1.0]
    return {brand: share(frame, var=var, positive_values=pos, weight=weight)
            for brand, var in brand_vars.items()}


def top_of_mind(frame: pd.DataFrame, *, first_mention_var: str, brand: str,
                weight: str | None = None) -> ShareResult:
    s = frame[first_mention_var].astype("string").str.strip().str.casefold()
    target = brand.strip().casefold()
    w = pd.to_numeric(frame[weight], errors="coerce") if weight else pd.Series(1.0, index=frame.index)
    valid = s.notna() & w.notna()
    total = w[valid].sum()
    hit = w[valid & (s == target)].sum()
    raw = (hit / total * 100.0) if total else 0.0
    return ShareResult(pct=round(raw), n=int(valid.sum()), raw=raw)


def _pattern_hit(col: pd.Series, patterns: list[str]) -> pd.Series:
    """True where the (lowercased, stripped) text contains ANY of the patterns (substring)."""
    text = col.astype("string").str.strip().str.casefold().fillna("")
    hit = pd.Series(False, index=col.index)
    for p in patterns:
        hit = hit | text.str.contains(p.casefold(), regex=False)
    return hit


def spontaneous_any_mention(frame: pd.DataFrame, *, mention_vars: list[str],
                            patterns: list[str], weight: str | None = None) -> ShareResult:
    """Share of respondents who mentioned a brand in ANY open-list position.

    A respondent counts if any of the `mention_vars` columns contains any of
    `patterns` (case/space-insensitive substring match — patterns absorb spelling
    variants the deck's manual coding collapsed, e.g. 'esper' -> Esperi/Espericare).
    Base is the full frame (every respondent), matching the deck's n=1001.
    """
    w = pd.to_numeric(frame[weight], errors="coerce") if weight else pd.Series(1.0, index=frame.index)
    hit = pd.Series(False, index=frame.index)
    for var in mention_vars:
        hit = hit | _pattern_hit(frame[var], patterns)
    total = w.sum()
    raw = (w[hit].sum() / total * 100.0) if total else 0.0
    return ShareResult(pct=round(raw), n=int(len(frame)), raw=raw)


def top_of_mind_patterns(frame: pd.DataFrame, *, first_mention_var: str,
                         patterns: list[str], weight: str | None = None) -> ShareResult:
    """Top-of-mind (first mention) share using substring patterns. Base = full frame."""
    w = pd.to_numeric(frame[weight], errors="coerce") if weight else pd.Series(1.0, index=frame.index)
    hit = _pattern_hit(frame[first_mention_var], patterns)
    total = w.sum()
    raw = (w[hit].sum() / total * 100.0) if total else 0.0
    return ShareResult(pct=round(raw), n=int(len(frame)), raw=raw)
