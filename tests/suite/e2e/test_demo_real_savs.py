"""`@pytest.mark.demo`: the three real client SAVs through a local-fs demo app.

Runs only under ``-m demo`` with ``NSIGHT_DEMO=1`` (the ``demo_app`` fixture
skips otherwise) and only when the real SAVs are present (``real_sav_paths``
skips otherwise). For EACH SAV: upload via the materials API, list questions,
pick a chartable single-choice question, create a small vertical_bar report and
round-trip it. The full soffice render is an extra `@pytest.mark.export`-gated
assertion; the upload+questions+report round-trip runs regardless of soffice.
"""
from __future__ import annotations

import json

import pytest

from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
    report_to_json,
)

pytestmark = pytest.mark.demo


def _upload(client, cid, sav_path):
    with open(sav_path, "rb") as fh:
        data = fh.read()
    resp = client.post(
        f"/cases/{cid}/materials",
        files={"file": (sav_path.name, data, "application/octet-stream")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _report_json(question_ref: str) -> dict:
    spec = ChartSpec(
        question_ref=question_ref, chart_type="vertical_bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="slot1",
        elements=ElementToggles(),
    )
    report = Report(name=f"demo-{question_ref}", render_mode="native",
                    template_ref="t.pptx", charts=(spec,))
    return json.loads(report_to_json(report))


def _pick_single_choice(questions: list[dict]) -> dict:
    """A chartable single-choice question; fall back to any chartable one."""
    chartable = [q for q in questions if q.get("chartable")]
    for q in chartable:
        if q.get("kind") == "single":
            return q
    assert chartable, "no chartable question in this SAV"
    return chartable[0]


def test_real_savs_upload_questions_report_roundtrip(demo_app, real_sav_paths):
    client, cid = demo_app

    for sav_path in real_sav_paths:
        up = _upload(client, cid, sav_path)
        mid = up["material_id"]
        assert up["question_count"] > 0, f"{sav_path.name}: no questions parsed"

        q = client.get(f"/materials/{mid}/questions")
        assert q.status_code == 200, q.text
        questions = q.json()["questions"]
        assert questions, f"{sav_path.name}: empty questions list"

        chosen = _pick_single_choice(questions)
        qid = chosen["qid"]

        created = client.post(f"/cases/{cid}/reports", json=_report_json(qid))
        assert created.status_code == 200, created.text
        rid = created.json()["report_id"]

        got = client.get(f"/cases/{cid}/reports/{rid}")
        assert got.status_code == 200
        assert got.json()["charts"][0]["question_ref"] == qid


@pytest.mark.export
def test_real_savs_full_render(demo_app, real_sav_paths, require_soffice):
    """The full render (LibreOffice) over the first real SAV — export-gated."""
    client, cid = demo_app

    sav_path = real_sav_paths[0]
    up = _upload(client, cid, sav_path)
    mid = up["material_id"]

    questions = client.get(f"/materials/{mid}/questions").json()["questions"]
    qid = _pick_single_choice(questions)["qid"]
    rid = client.post(f"/cases/{cid}/reports", json=_report_json(qid)).json()["report_id"]

    r = client.post(
        f"/cases/{cid}/reports/{rid}/render",
        json={"material_id": mid, "view": "slides"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) >= {"pptx", "pdf", "preview", "pdf_url"}

    pdf = client.get(f"/cases/{cid}/reports/{rid}/preview.pdf")
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"
