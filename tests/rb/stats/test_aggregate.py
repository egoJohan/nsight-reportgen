from __future__ import annotations
import numpy as np
import pandas as pd
import pytest

from reportbuilder.stats.aggregate import aggregate_counts


def test_counts_single_var_total_only():
    df = pd.DataFrame({"q1": [1.0, 1.0, 2.0, np.nan]})
    counts = aggregate_counts(df, "q1")
    assert counts[(1.0, "Total")] == 2
    assert counts[(2.0, "Total")] == 1
    # NaN row must not produce any key with a NaN value-code
    assert not any(k for k in counts if k[0] is None or (isinstance(k[0], float) and np.isnan(k[0])))


def test_counts_with_classifier_has_segments_and_total():
    df = pd.DataFrame({
        "q1": [1.0, 2.0, 1.0, 2.0],
        "seg": [10.0, 10.0, 20.0, 20.0],
    })
    counts = aggregate_counts(df, "q1", classifying_var="seg")
    # Per-segment counts
    assert counts[(1.0, "10")] == 1
    assert counts[(2.0, "20")] == 1
    # Total counts still present
    assert counts[(1.0, "Total")] == 2
    assert counts[(2.0, "Total")] == 2
