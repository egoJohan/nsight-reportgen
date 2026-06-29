"""GET /materials/{id}/questions/{qid}/summary — metadata + computed stats."""
from __future__ import annotations

from unittest.mock import Mock

from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.testing.fixtures import synthetic_sav_bytes


def _client():
    mock = Mock()
    mock.get_material.return_value = synthetic_sav_bytes()
    return TestClient(create_app(client=mock))


def test_summary_has_metadata_and_distribution():
    c = _client()
    qs = c.get("/materials/mat-s/questions").json()["questions"]
    chartable = next(q for q in qs if q["chartable"] is not False)

    r = c.get(f"/materials/mat-s/questions/{chartable['qid']}/summary")
    assert r.status_code == 200
    s = r.json()
    assert s["qid"] == chartable["qid"]
    assert s["respondent_total"] > 0
    assert s["base_n"] is not None and s["base_n"] > 0
    assert isinstance(s["distribution"], list) and len(s["distribution"]) > 0
    row = s["distribution"][0]
    assert "category" in row and "count" in row and "pct" in row
    # Shares are a sane percentage.
    assert all(0 <= (d["pct"] or 0) <= 100 for d in s["distribution"])
    assert s["measurement"] in {"categorical", "scale", "multi", "text"}


def test_summary_unknown_qid_404():
    assert _client().get("/materials/mat-s/questions/nope/summary").status_code == 404
