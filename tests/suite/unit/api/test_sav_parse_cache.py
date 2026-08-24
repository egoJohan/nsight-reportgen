"""Reading the same SAV sixty times in a row.

Parsing one costs ~350 ms for a typical study — 229 variables, 1000
respondents — and every model load paid it. Previewing a sixty-slide deck spent
twenty seconds re-reading one file, on the CPU, with the requests contending
for it. Every path that touches a model goes through this seam, so caching here
is the whole fix.

The property that matters is not "it is faster" but "it cannot be stale": the
key is the file's CONTENT, so different bytes are a different entry and a
re-uploaded material can never be served the previous parse.
"""
from __future__ import annotations

import pytest

from reportbuilder.api import model_loader
import pandas as pd
import pyreadstat


class _Client:
    """Counts how often the blob is actually parsed, by counting fetches of it."""

    def __init__(self, blob: bytes) -> None:
        self.blob = blob
        self.fetches = 0

    def get_material(self, material_id: str) -> bytes:
        self.fetches += 1
        return self.blob

    def load_material_config(self, material_id: str):
        return None


@pytest.fixture(autouse=True)
def _clean_cache():
    model_loader._forget_parsed_savs()
    yield
    model_loader._forget_parsed_savs()


def _sav_bytes(tmp_path, label: str = "Satisfaction") -> bytes:
    """A minimal SAV. `label` gives us two files that differ in content."""
    path = tmp_path / f"{abs(hash(label)) % 10**8}.sav"
    pyreadstat.write_sav(
        pd.DataFrame({"q1": [1.0, 1.0, 2.0]}), str(path),
        column_labels={"q1": label},
        variable_value_labels={"q1": {1: "Yes", 2: "No"}},
        variable_measure={"q1": "nominal"})
    return path.read_bytes()


@pytest.fixture
def blob(tmp_path):
    return _sav_bytes(tmp_path)


def test_the_same_file_is_parsed_once(blob, monkeypatch):
    client = _Client(blob)
    parses = {"n": 0}
    real = model_loader.read_sav

    def counting(path):
        parses["n"] += 1
        return real(path)

    monkeypatch.setattr(model_loader, "read_sav", counting)
    for _ in range(5):
        model_loader.df_model_for_material("mat-1", client)
    assert parses["n"] == 1
    assert client.fetches == 5, "storage is still the authority on the bytes"


def test_different_bytes_are_never_served_the_previous_parse(blob, tmp_path):
    """The staleness question, which is the only one worth being careful about.

    Same material id, new file. Keyed on content, so this cannot go wrong by
    construction — pinned so it stays that way.
    """
    client = _Client(blob)
    first = model_loader.model_for_material("mat-1", client)

    assert [q.text for q in first.questions] == ["Satisfaction"]

    client.blob = _sav_bytes(tmp_path, label="Something else entirely")
    second = model_loader.model_for_material("mat-1", client)

    assert client.blob != blob
    assert [q.text for q in second.questions] == ["Something else entirely"]


def test_a_caller_cannot_corrupt_the_next_one(blob):
    """Each caller gets its own frame. A shared one would break the NEXT
    request rather than this one, which is the worst kind of bug to hand
    somebody."""
    client = _Client(blob)
    df1, _model = model_loader.df_model_for_material("mat-1", client)
    df1["a_column_someone_added"] = 1

    df2, _model2 = model_loader.df_model_for_material("mat-1", client)
    assert "a_column_someone_added" not in df2.columns


def test_it_does_not_hold_every_study_ever_opened(monkeypatch, tmp_path):
    monkeypatch.setattr(model_loader, "_PARSED_MAX", 2)
    for i in range(5):
        model_loader.model_for_material(
            f"mat-{i}", _Client(_sav_bytes(tmp_path, label=f"Study {i}")))
    assert len(model_loader._PARSED) <= 2
