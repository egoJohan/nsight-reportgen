"""E2E fixtures for the fresh backend suite (`tests/suite/e2e`).

Two demo-mode fixtures, mirroring ``tests/rb/e2e/conftest.py``:

  * ``real_sav_paths`` — the three current client SAVs, resolved from the
    gitignored test-data copy first, then the tracked ``input/`` dir. Skips
    when none are present.
  * ``demo_app`` — a ``TestClient`` over a real local-fs ``InMemoryDataHiveClient``
    rooted at a throwaway temp dir, with a case already created. Skips unless
    ``NSIGHT_DEMO=1`` so the standard suite never runs it. Returns
    ``(client, case_id)``.
"""
from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient


# Filenames of the three current client SAVs (see tests/rb/e2e/data/README.md).
_SAV_FILENAMES = (
    "spss_FINAL_HolidayClub.sav",
    "spss AttendoSuomi-Brandiseuranta_112025.sav",
    "spss Synsam_segmenteillä_vainvalittu_segmmalli.sav",
)

# conftest -> e2e -> suite -> tests -> proto
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_DATA_DIR = _REPO_ROOT / "tests" / "rb" / "e2e" / "data" / "sav"
_INPUT_DIR = _REPO_ROOT / "input"


def _resolve_sav(name: str) -> pathlib.Path | None:
    """Prefer the gitignored test-data copy; fall back to the tracked input/ file."""
    for base in (_DATA_DIR, _INPUT_DIR):
        p = base / name
        if p.is_file():
            return p
    return None


@pytest.fixture
def real_sav_paths() -> list[pathlib.Path]:
    paths = [p for p in (_resolve_sav(n) for n in _SAV_FILENAMES) if p is not None]
    if not paths:
        pytest.skip(
            "No client SAVs found — copy them into tests/rb/e2e/data/sav/ "
            "(see README) or ensure input/ contains them."
        )
    return paths


@pytest.fixture
def demo_app(tmp_path, monkeypatch):
    """A TestClient backed by the local-fs InMemoryDataHiveClient (NSIGHT_DEMO
    path), rooted at a throwaway temp dir. Skips unless NSIGHT_DEMO=1 so the
    standard suite never runs it. Returns (client, case_id)."""
    if os.environ.get("NSIGHT_DEMO") != "1":
        pytest.skip("demo-group test — set NSIGHT_DEMO=1 to run")

    from reportbuilder.api.app import create_app
    from reportbuilder.store.memory_client import InMemoryDataHiveClient

    store_dir = tmp_path / "store"
    store_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NSIGHT_DEMO_DIR", str(store_dir))

    client = InMemoryDataHiveClient(storage_dir=str(store_dir))
    app = create_app(client=client)
    tc = TestClient(app)

    resp = tc.post("/cases", json={"name": "nsight-demo-real-savs"})
    assert resp.status_code in (200, 201), resp.text
    case_id = resp.json()["case_id"]
    assert case_id, f"unexpected /cases response: {resp.json()!r}"
    return tc, case_id
