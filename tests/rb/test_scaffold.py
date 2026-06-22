"""Test scaffold for reportbuilder package."""

import reportbuilder
from reportbuilder import model, stats, render, testing, ingest, export, store, api
import anthropic
import pdfplumber


def test_scaffold_imports():
    """Verify all reportbuilder subpackages and external deps are importable."""
    assert reportbuilder is not None
    assert model is not None
    assert stats is not None
    assert render is not None
    assert testing is not None
    assert ingest is not None
    assert export is not None
    assert store is not None
    assert api is not None
    assert anthropic is not None
    assert pdfplumber is not None
