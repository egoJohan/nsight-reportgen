"""The prose path must go through datahive, and must fail closed.

nSight's slide titles and themes are written from a confidential brand tracker
— the client and every competitor, named, with things said about them the
client would not publish. The one thing that must never happen is that text
reaching a vendor in clear.

The last test is the guard that matters: it fails if anyone adds a function to
`reportbuilder.ai.text` that calls a model directly instead of taking the
injectable `chat` that defaults to the masked route.
"""
from __future__ import annotations

import inspect

from reportbuilder.ai import masked_chat

import httpx
import pytest

from nsight.agent.egohive_client import EgoHiveError
from reportbuilder.ai import text as ai_text
from reportbuilder.ai.masked_chat import datahive_chat


@pytest.fixture(autouse=True)
def _hive_env(monkeypatch):
    monkeypatch.setenv("NSIGHT_DATAHIVE_URL", "http://hive.test")
    monkeypatch.setenv("NSIGHT_DATAHIVE_TOKEN", "t-1")


def _reply(monkeypatch, status: int, payload: dict):
    def fake_post(url, **kw):
        return httpx.Response(status, json=payload,
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)


def test_a_masked_reply_is_returned(monkeypatch):
    _reply(monkeypatch, 200, {"text": "  Otsikko  ", "pseudonymized": True})
    assert datahive_chat("kirjoita otsikko") == "Otsikko"


def test_a_refusal_to_mask_is_not_a_reason_to_send_anyway(monkeypatch):
    """412 means the control worked. The caller degrades to a deterministic
    default; it never retries without masking."""
    _reply(monkeypatch, 412, {"detail": {
        "error": "pseudonymization_unavailable",
        "why": "pii_pseudonymize_internal_llm is off for this tenant"}})
    with pytest.raises(EgoHiveError, match="off for this tenant"):
        datahive_chat("kirjoita otsikko")


def test_a_reply_that_admits_it_was_not_masked_is_refused(monkeypatch):
    """The endpoint reports what it actually did. False here means the study's
    names went to a vendor in clear — worth failing over, not logging."""
    _reply(monkeypatch, 200, {"text": "Otsikko", "pseudonymized": False})
    with pytest.raises(EgoHiveError, match="not pseudonymised"):
        datahive_chat("kirjoita otsikko")


def test_no_hive_configured_means_no_model_at_all(monkeypatch):
    """There is no unmasked fallback route, so an unconfigured hive is a
    refusal rather than a direct call to a vendor."""
    monkeypatch.delenv("NSIGHT_DATAHIVE_URL", raising=False)
    with pytest.raises(EgoHiveError, match="no masked route"):
        datahive_chat("kirjoita otsikko")


def _prose_functions():
    """Every function here that takes an injectable `chat`."""
    for name, fn in vars(ai_text).items():
        if name.startswith("_") or not inspect.isfunction(fn):
            continue
        if fn.__module__ != ai_text.__name__:
            continue
        params = inspect.signature(fn).parameters
        if "chat" in params:
            yield name, params["chat"].default


#: The one function allowed to reach a model unmasked, and why.
#:
#: `pick_company_terms` is handed candidate strings read off the study's
#: structure and asked which of them name a company. Masking would replace
#: those strings with surrogates before the model saw them: it would be asked
#: to recognise names it had been stopped from reading. What makes it safe is
#: what does NOT go with them — no findings, no percentages, no respondent
#: answers. A bare list of names discloses nothing; the sensitivity is in
#: associating a company with a result. (Johan's call, 2026-09-02.)
_MAY_RUN_UNMASKED = {"pick_company_terms"}


def test_every_prose_function_defaults_to_the_masked_route():
    """The guard. A new function here that calls a model directly would send a
    confidential tracker to a vendor, and nothing else in the suite would say so.

    The defaults are purpose-bound wrappers now, not `datahive_chat` itself, so
    identity is the wrong test — it would have to be relaxed for every new
    purpose, and relaxing a guard is how one stops guarding. `masked` is set by
    `_bound` and nothing else, and every wrapper it makes calls `datahive_chat`.
    """
    offenders = [name for name, default in _prose_functions()
                 if name not in _MAY_RUN_UNMASKED
                 and default is not datahive_chat
                 and not getattr(default, "masked", False)]
    assert not offenders, (
        f"these take `chat` but do not default to the masked route: {offenders}")


def test_the_unmasked_exception_is_still_the_only_one():
    """Named, not loosened. A second function wanting this has to be argued for
    here, in the open, rather than inheriting an exemption someone else won."""
    unmasked = {name for name, default in _prose_functions()
                if not getattr(default, "masked", False)}
    assert unmasked == _MAY_RUN_UNMASKED


def test_each_prose_function_asks_for_the_purpose_its_prompt_describes():
    """datahive picks the model from `purpose`, so a wrong one here is answered
    by the wrong size of model — silently, and with plausible-looking output.

    These are read off each prompt, not guessed from the function name:
    `generate_group_subtitle` says "EI avainviesti, EI johtopäätös" (explicitly
    not a conclusion) so it only summarises, while `generate_conclusion_bullets`
    reads the whole report and may state what no single slide states, which is
    what `synthesise` means. Change one of these ONLY together with the prompt
    it describes.

    `generate_slide_title` SUMMARISES, and the reason is worth keeping because
    the prompt reads the other way at a glance. It does say "Otsikon tulee
    TULKITA tuloksia" — but interpreting "kyllä 62" as "selvä enemmistö" is
    condensation, not invention: it says less than the input and nothing the
    input did not say, which is the hive's own line between the two purposes.
    Measurement settled it. `synthesise` is bound to `generous` deliberation,
    and on this task deliberation cost 8.1s against 4.8s and returned the only
    headline with no quantity in it — a hedge, where the job was to report.
    """
    expected = {
        "generate_slide_title": "summarise",
        "generate_group_subtitle": "summarise",
        "shorten_labels": "rewrite",
        "generate_data_chat": "converse",
        "generate_overview_bullets": "summarise",
        "generate_conclusion_bullets": "synthesise",
        "generate_open_themes": "summarise",
        "pick_demographic_questions": "classify",
        # Choosing among the strings the caller supplied is exactly `classify`:
        # the answer is a subset of the input, never anything new.
        "pick_company_terms": "classify",
        "generate_demographics_bullets": "summarise",
    }
    actual = {name: getattr(default, "purpose", None)
              for name, default in _prose_functions()}
    assert actual == expected


def test_a_purpose_bound_wrapper_still_goes_through_datahive(monkeypatch):
    """`masked` is only trustworthy if the wrapper really routes through the
    masked path — the guard above rests on it."""
    seen = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen["purpose"] = kwargs["json"]["purpose"]
        # An error the module WRAPS, so the wrapper is exercised end to end
        # rather than escaping through it.
        raise httpx.ConnectError("stop here — the request shape is the assertion")

    monkeypatch.setenv("NSIGHT_DATAHIVE_URL", "https://hive.example")
    monkeypatch.setenv("NSIGHT_DATAHIVE_TOKEN", "t")
    monkeypatch.setattr("reportbuilder.ai.masked_chat.httpx.post", fake_post)

    with pytest.raises(EgoHiveError):
        masked_chat.rewrite("lyhennä tämä")
    assert seen["url"].endswith("/api/v1/llm/ask")
    assert seen["purpose"] == "rewrite"
