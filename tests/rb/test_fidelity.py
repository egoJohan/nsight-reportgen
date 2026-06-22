"""Tests for fidelity gate layers 1 & 2 (design §10)."""
from __future__ import annotations

import pytest
from reportbuilder.stats.series import Cell, SeriesResult
from reportbuilder.testing.fidelity import (
    assert_series_match,
    numbers_from_pdf,
    numbers_from_pptx,
)


# ---------------------------------------------------------------------------
# Fixture: SeriesResult with Yes=60%, No=40%
# ---------------------------------------------------------------------------

@pytest.fixture
def yes_no_series() -> SeriesResult:
    categories = ("Yes", "No")
    segments = ("Total",)
    cells = {
        ("Yes", "Total"): Cell(pct=60.0, count=60.0, mean=None),
        ("No", "Total"): Cell(pct=40.0, count=40.0, mean=None),
    }
    base_n = {"Total": 100}
    return SeriesResult(
        categories=categories,
        segments=segments,
        cells=cells,
        base_n=base_n,
        statistic="pct",
    )


# ---------------------------------------------------------------------------
# Layer 1: numbers_from_pptx
# ---------------------------------------------------------------------------

def test_numbers_from_pptx_reads_series(tmp_native_pptx):
    """Native chart values read back correctly."""
    extracted = numbers_from_pptx(tmp_native_pptx)
    assert "Total" in extracted
    assert extracted["Total"] == pytest.approx([60.0, 40.0])


# ---------------------------------------------------------------------------
# Layer 1: assert_series_match — success path
# ---------------------------------------------------------------------------

def test_assert_series_match_passes(tmp_native_pptx, yes_no_series):
    """assert_series_match raises nothing when values are present."""
    extracted = numbers_from_pptx(tmp_native_pptx)
    # Should not raise
    assert_series_match(extracted, yes_no_series)


# ---------------------------------------------------------------------------
# Layer 1: assert_series_match — drift detection
# ---------------------------------------------------------------------------

def test_assert_series_match_detects_drift(yes_no_series):
    """Drifted extracted dict triggers AssertionError."""
    drifted = {"Total": [60.0, 33.0]}  # 40.0 replaced by 33.0
    with pytest.raises(AssertionError) as exc_info:
        assert_series_match(drifted, yes_no_series)
    # 40.0 should be reported as missing
    assert "40" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Layer 2: numbers_from_pdf
# ---------------------------------------------------------------------------

def test_numbers_from_pdf_parses_tokens(tmp_path):
    """numbers_from_pdf extracts numeric tokens written as text into a PDF."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.pyplot as plt

    pdf_path = str(tmp_path / "test.pdf")
    with PdfPages(pdf_path) as pp:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "60% and 40%", transform=ax.transAxes, fontsize=14)
        ax.axis("off")
        pp.savefig(fig)
        plt.close(fig)

    result = numbers_from_pdf(pdf_path)
    assert 60.0 in result
    assert 40.0 in result
