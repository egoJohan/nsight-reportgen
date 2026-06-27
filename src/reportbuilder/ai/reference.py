"""Reference label corpus harvested from the originating PowerPoints.

The nSight analysts already produced *short* category labels and slide titles in
the source decks (``input/*.pptx``). When the report builder needs to shorten a
full SAV value label, we first try to reuse one of those human-authored short
forms verbatim (no AI call); only labels with no confident match are sent to
egoHive for AI-shortening.

``ReferenceLabels`` holds the harvested short labels + slide-title texts and
exposes:
- :meth:`load` — build (and cache) a corpus from a list of pptx paths, tolerating
  missing/unreadable files.
- :meth:`match` — return a reference short label for a full label, but only when
  it is a confident (exact-normalized or high-ratio fuzzy) match AND strictly
  shorter than the input (the reference labels are the short forms).
- :meth:`examples` — a small sample of short labels to feed the AI as a style
  guide.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from nsight.fidelity.extract import extract_deck

# High threshold so only near-identical strings count as a fuzzy hit (C.3).
FUZZY_THRESHOLD = 0.9

# Module-level cache keyed by the (resolved) path tuple (C.3: "cache module-level").
_CACHE: dict[tuple[str, ...], "ReferenceLabels"] = {}


def _normalize(s: str) -> str:
    """Casefold, strip, drop punctuation, and collapse whitespace for matching."""
    s = (s or "").casefold().strip()
    # Replace any non-word / non-space char with a space (unicode-aware).
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class ReferenceLabels:
    """A corpus of short reference labels + slide titles from the source decks."""

    def __init__(self, labels: list[str], titles: list[str]) -> None:
        self._labels: list[str] = [str(x) for x in labels if str(x).strip()]
        self._titles: list[str] = [str(x) for x in titles if str(x).strip()]
        # Normalized -> first-seen original short label (keep the first occurrence).
        self._norm_map: dict[str, str] = {}
        for lbl in self._labels:
            n = _normalize(lbl)
            if n and n not in self._norm_map:
                self._norm_map[n] = lbl

    # -- construction -------------------------------------------------------
    @classmethod
    def load(cls, paths: list[Path] | list[str]) -> "ReferenceLabels":
        """Harvest all chart category labels + slide texts from ``paths``.

        Missing or unreadable decks are skipped (never raises). Results are
        cached module-level keyed by the resolved path tuple.
        """
        key = tuple(str(Path(p)) for p in paths)
        cached = _CACHE.get(key)
        if cached is not None:
            return cached

        labels: list[str] = []
        titles: list[str] = []
        for p in paths:
            path = Path(p)
            if not path.exists():
                continue
            try:
                deck = extract_deck(path)
            except Exception:
                # Tolerate a corrupt/unreadable pptx — just skip it.
                continue
            for slide in deck.slides:
                for chart in slide.charts:
                    labels.extend(str(c) for c in chart.categories)
                titles.extend(str(t) for t in slide.texts)

        inst = cls(labels, titles)
        _CACHE[key] = inst
        return inst

    # -- matching -----------------------------------------------------------
    def match(self, full_label: str) -> str | None:
        """Return a confident reference short label for ``full_label`` or None.

        Strategy (kept simple + safe):
        1. exact normalized match,
        2. else a high-threshold fuzzy match (difflib ratio >= 0.9),
        and in BOTH cases only return a candidate that is strictly SHORTER than
        ``full_label`` (reference labels are the short forms). Never returns a
        string longer than or equal in length to the input.
        """
        if not full_label or not full_label.strip():
            return None
        target = _normalize(full_label)
        if not target:
            return None

        # 1. exact normalized hit
        cand = self._norm_map.get(target)
        if cand is not None and len(cand) < len(full_label):
            return cand

        # 2. fuzzy hit
        best: str | None = None
        best_ratio = 0.0
        for norm, orig in self._norm_map.items():
            if len(orig) >= len(full_label):
                continue  # never return a longer/equal candidate
            ratio = difflib.SequenceMatcher(None, target, norm).ratio()
            if ratio >= FUZZY_THRESHOLD and ratio > best_ratio:
                best, best_ratio = orig, ratio
        return best

    # -- style guide --------------------------------------------------------
    def examples(self, n: int = 12) -> list[str]:
        """Return up to ``n`` distinct short reference labels (shortest first)."""
        seen: set[str] = set()
        ordered: list[str] = []
        for lbl in sorted(set(self._labels), key=lambda s: (len(s), s)):
            key = lbl.strip()
            if key and key not in seen:
                seen.add(key)
                ordered.append(key)
            if len(ordered) >= n:
                break
        return ordered

    # -- introspection ------------------------------------------------------
    @property
    def labels(self) -> list[str]:
        return list(self._labels)

    @property
    def titles(self) -> list[str]:
        return list(self._titles)


__all__ = ["ReferenceLabels"]
