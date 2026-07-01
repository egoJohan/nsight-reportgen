"""Deterministic tests for the AI routes (``reportbuilder.api.routes_ai``).

The LLM boundary is always monkeypatched — no real network. We patch the
call-time-looked-up ``reportbuilder.api.routes_ai.egohive_chat`` seam (and, for
short-labels, ``_reference_labels`` so the pptx corpus is never read). Data is
served by ``client_mock`` (a Mock DataHiveClient → synthetic SAV), so any
material_id resolves. Synthetic qids: ``q1`` (single), ``m`` (multi), ``age``.
"""
from __future__ import annotations

import numpy as np
import pytest

import reportbuilder.api.routes_ai as R
from reportbuilder.ai.reference import ReferenceLabels
from nsight.agent.egohive_client import EgoHiveError

from suite._helpers import RecordingChat


MID = "mat-1"  # any id works with the Mock client


def _patch_chat(monkeypatch, reply):
    """Install a RecordingChat as the routes' egoHive seam; return it."""
    chat = reply if isinstance(reply, RecordingChat) else RecordingChat(reply)
    monkeypatch.setattr(R, "egohive_chat", chat)
    return chat


def _no_call(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("egohive_chat must not be called")

    monkeypatch.setattr(R, "egohive_chat", boom)


def _raise_egohive(monkeypatch):
    def boom(*a, **k):
        raise EgoHiveError("egohive down")

    monkeypatch.setattr(R, "egohive_chat", boom)


def _empty_reference(monkeypatch):
    monkeypatch.setattr(R, "_reference_labels", lambda: ReferenceLabels(labels=[], titles=[]))


# --------------------------------------------------------------------------- #
# /ai/slide-title
# --------------------------------------------------------------------------- #
def test_slide_title_returns_cleaned_title(client_mock, monkeypatch):
    # Quotes + markdown emphasis are stripped by _clean.
    chat = _patch_chat(monkeypatch, '"**Tyytyväisyys on korkealla tasolla**"')
    resp = client_mock.post(f"/materials/{MID}/ai/slide-title", json={"question_ref": "q1"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"title": "Tyytyväisyys on korkealla tasolla"}
    assert chat.calls == 1
    assert "Satisfaction" in chat.prompts[0]  # findings carry the question text


def test_slide_title_unknown_question_404(client_mock, monkeypatch):
    _patch_chat(monkeypatch, "x")
    resp = client_mock.post(f"/materials/{MID}/ai/slide-title", json={"question_ref": "nope"})
    assert resp.status_code == 404


def test_slide_title_egohive_error_503(client_mock, monkeypatch):
    _raise_egohive(monkeypatch)
    resp = client_mock.post(f"/materials/{MID}/ai/slide-title", json={"question_ref": "q1"})
    assert resp.status_code == 503
    assert "egoHive" in resp.json()["detail"]


def test_slide_title_empty_findings_falls_back_without_llm(client_mock, monkeypatch):
    # No computable findings → return the question text, never call the LLM.
    _no_call(monkeypatch)
    monkeypatch.setattr(R, "_findings_from_series", lambda series, n: [])
    resp = client_mock.post(f"/materials/{MID}/ai/slide-title", json={"question_ref": "q1"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"title": "Satisfaction"}


# --------------------------------------------------------------------------- #
# /ai/short-labels
# --------------------------------------------------------------------------- #
def test_short_labels_from_categories(client_mock, monkeypatch):
    _empty_reference(monkeypatch)
    _patch_chat(monkeypatch, "1. Tyytyväiset\n2. Tyytymättömät")
    resp = client_mock.post(
        f"/materials/{MID}/ai/short-labels",
        json={"categories": [
            "Erittäin tai melko tyytyväiset",
            "Erittäin tai melko tyytymättömät",
        ]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"overrides": [
        ["Erittäin tai melko tyytyväiset", "Tyytyväiset"],
        ["Erittäin tai melko tyytymättömät", "Tyytymättömät"],
    ]}


def test_short_labels_from_question_ref(client_mock, monkeypatch):
    _empty_reference(monkeypatch)
    _patch_chat(monkeypatch, "1. Kyllä\n2. Ei")
    resp = client_mock.post(f"/materials/{MID}/ai/short-labels", json={"question_ref": "q1"})
    assert resp.status_code == 200, resp.text
    assert "overrides" in resp.json()


def test_short_labels_unknown_question_404(client_mock, monkeypatch):
    _empty_reference(monkeypatch)
    _patch_chat(monkeypatch, "x")
    resp = client_mock.post(f"/materials/{MID}/ai/short-labels", json={"question_ref": "nope"})
    assert resp.status_code == 404


def test_short_labels_neither_field_422(client_mock):
    resp = client_mock.post(f"/materials/{MID}/ai/short-labels", json={})
    assert resp.status_code == 422


def test_short_labels_egohive_error_degrades_to_200(client_mock, monkeypatch):
    # shorten_labels swallows EgoHiveError → originals; endpoint stays 200.
    _empty_reference(monkeypatch)
    _raise_egohive(monkeypatch)
    resp = client_mock.post(
        f"/materials/{MID}/ai/short-labels", json={"categories": ["Jokin pitkä otsikko"]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"overrides": []}  # fell back to originals (no override)


def test_short_labels_reference_failure_503(client_mock, monkeypatch):
    def boom():
        raise RuntimeError("pptx corpus blew up")

    monkeypatch.setattr(R, "_reference_labels", boom)
    resp = client_mock.post(
        f"/materials/{MID}/ai/short-labels", json={"categories": ["A long label here"]}
    )
    assert resp.status_code == 503


# --------------------------------------------------------------------------- #
# /ai/themes  (previously untested)
# --------------------------------------------------------------------------- #
def test_themes_returns_bullets(client_mock, monkeypatch):
    chat = _patch_chat(monkeypatch, "- **Teema A** – noin 40 %\n- **Teema B** – noin 20 %")
    resp = client_mock.post(f"/materials/{MID}/ai/themes", json={"question_ref": "q1"})
    assert resp.status_code == 200, resp.text
    # _parse_bullets strips the leading marker but keeps markdown **bold** theme names.
    assert resp.json() == {"bullets": ["**Teema A** – noin 40 %", "**Teema B** – noin 20 %"]}
    assert chat.calls == 1


def test_themes_unknown_question_404(client_mock, monkeypatch):
    _patch_chat(monkeypatch, "x")
    resp = client_mock.post(f"/materials/{MID}/ai/themes", json={"question_ref": "nope"})
    assert resp.status_code == 404


def test_themes_egohive_error_503(client_mock, monkeypatch):
    _raise_egohive(monkeypatch)
    resp = client_mock.post(f"/materials/{MID}/ai/themes", json={"question_ref": "q1"})
    assert resp.status_code == 503


def test_themes_no_words_no_answers_returns_empty_without_llm(
    client_mock, monkeypatch, synthetic_model
):
    # Force both signals empty: no findings (word_freqs) and an all-NaN column
    # (no verbatim answers) → the route short-circuits to [] without any LLM call.
    _no_call(monkeypatch)
    df, model = synthetic_model
    df2 = df.copy()
    df2["q1"] = np.nan
    monkeypatch.setattr(R, "_load_df_model", lambda mid, cl: (df2, model))
    monkeypatch.setattr(R, "_findings_from_series", lambda series, n: [])
    resp = client_mock.post(f"/materials/{MID}/ai/themes", json={"question_ref": "q1"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"bullets": []}


# --------------------------------------------------------------------------- #
# /ai/overview
# --------------------------------------------------------------------------- #
def test_overview_returns_bullets(client_mock, monkeypatch):
    _patch_chat(
        monkeypatch,
        "- Tutkimus kartoitti asiakastyytyväisyyttä\n- Vastaajia oli runsaasti",
    )
    resp = client_mock.post(f"/materials/{MID}/ai/overview", json={"question_refs": ["q1"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["bullets"] == [
        "Tutkimus kartoitti asiakastyytyväisyyttä",
        "Vastaajia oli runsaasti",
    ]


def test_overview_empty_refs_uses_all_questions(client_mock, monkeypatch):
    chat = _patch_chat(monkeypatch, "- Yksi havainto")
    resp = client_mock.post(f"/materials/{MID}/ai/overview", json={})
    assert resp.status_code == 200, resp.text
    # With no refs the route feeds every question's text into the prompt.
    prompt = chat.prompts[0]
    assert "Satisfaction" in prompt and "Channel" in prompt and "Age" in prompt


def test_overview_egohive_error_503(client_mock, monkeypatch):
    _raise_egohive(monkeypatch)
    resp = client_mock.post(f"/materials/{MID}/ai/overview", json={})
    assert resp.status_code == 503


# --------------------------------------------------------------------------- #
# /ai/conclusion
# --------------------------------------------------------------------------- #
def test_conclusion_returns_bullets(client_mock, monkeypatch):
    _patch_chat(monkeypatch, "1. Tyytyväisyys on korkealla\n2. Suosittelu yleistä")
    resp = client_mock.post(f"/materials/{MID}/ai/conclusion", json={"question_refs": ["q1"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["bullets"] == ["Tyytyväisyys on korkealla", "Suosittelu yleistä"]


def test_conclusion_no_findings_returns_empty_without_llm(client_mock, monkeypatch):
    # Unknown refs → no computable findings → empty bullets, no LLM call.
    _no_call(monkeypatch)
    resp = client_mock.post(
        f"/materials/{MID}/ai/conclusion", json={"question_refs": ["nope"]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"bullets": []}


def test_conclusion_egohive_error_503(client_mock, monkeypatch):
    _raise_egohive(monkeypatch)
    resp = client_mock.post(f"/materials/{MID}/ai/conclusion", json={"question_refs": ["q1"]})
    assert resp.status_code == 503


# --------------------------------------------------------------------------- #
# /ai/demographics  (two LLM calls: pick, then bullets)
# --------------------------------------------------------------------------- #
def test_demographics_picks_and_returns_bullets(client_mock, monkeypatch):
    def reply(prompt):
        if "tunnukset" in prompt:  # the demographic-pick prompt
            return "q1, age"
        return "- Vastaajista enemmistö on tyytyväisiä"

    chat = _patch_chat(monkeypatch, RecordingChat(reply))
    resp = client_mock.post(f"/materials/{MID}/ai/demographics", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["question_refs"] == ["q1", "age"]
    assert body["bullets"] == ["Vastaajista enemmistö on tyytyväisiä"]
    # One chart descriptor per picked question, each with a chart_type.
    assert [c["question_ref"] for c in body["charts"]] == ["q1", "age"]
    assert all(c.get("chart_type") for c in body["charts"])
    assert chat.calls == 2  # pick + bullets


def test_demographics_egohive_error_503(client_mock, monkeypatch):
    _raise_egohive(monkeypatch)
    resp = client_mock.post(f"/materials/{MID}/ai/demographics", json={})
    assert resp.status_code == 503


# --------------------------------------------------------------------------- #
# /chat  (previously untested)
# --------------------------------------------------------------------------- #
def test_chat_returns_reply(client_mock, monkeypatch):
    chat = _patch_chat(monkeypatch, "Datan perusteella tyytyväisyys on korkea.")
    resp = client_mock.post(
        f"/materials/{MID}/chat",
        json={"messages": [{"role": "user", "content": "Miten tyytyväisyys jakautuu?"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"reply": "Datan perusteella tyytyväisyys on korkea."}
    assert "Miten tyytyväisyys jakautuu?" in chat.prompts[0]


def test_chat_empty_messages_422(client_mock):
    resp = client_mock.post(f"/materials/{MID}/chat", json={"messages": []})
    assert resp.status_code == 422


def test_chat_blank_message_422(client_mock):
    resp = client_mock.post(
        f"/materials/{MID}/chat", json={"messages": [{"role": "user", "content": "   "}]}
    )
    assert resp.status_code == 422


def test_chat_egohive_error_503(client_mock, monkeypatch):
    _raise_egohive(monkeypatch)
    resp = client_mock.post(
        f"/materials/{MID}/chat", json={"messages": [{"role": "user", "content": "hei"}]}
    )
    assert resp.status_code == 503


def test_chat_empty_reply_uses_finnish_fallback(client_mock, monkeypatch):
    _patch_chat(monkeypatch, "")  # LLM returns nothing
    resp = client_mock.post(
        f"/materials/{MID}/chat", json={"messages": [{"role": "user", "content": "hei"}]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "reply": "En osaa vastata tähän käytettävissä olevan datan perusteella."
    }
