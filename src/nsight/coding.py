from __future__ import annotations

from collections import Counter

import pandas as pd


def _normalize(token: str) -> str:
    return token.strip().casefold()


def top_words(frame: pd.DataFrame, *, text_vars: list[str], top_n: int = 10,
              synonyms: dict[str, str] | None = None) -> list[tuple[str, int]]:
    """Count normalized free-text tokens across the given variables, return TOP-N.

    `synonyms` collapses variants to a canonical form. Counting is case/space-insensitive.
    """
    syn = synonyms or {}
    counter: Counter[str] = Counter()
    for var in text_vars:
        for val in frame[var].dropna().astype(str):
            tok = _normalize(val)
            if not tok:
                continue
            counter[syn.get(tok, tok)] += 1
    return counter.most_common(top_n)
