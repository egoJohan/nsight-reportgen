"""Asking a model a question, without telling it who the study is about.

nSight's prose — slide titles, themes, shortened labels — is written by a
frontier model, and the material it is written from is confidential: a brand
tracker names its client and every competitor, and says things about them the
client would not publish. Those names must not reach a vendor.

The masking is NOT done here, and that is the design. This sends the prompt to
datahive, which pseudonymises it, calls the model, and de-pseudonymises the
reply before returning it. Real names go in and real names come back; what the
vendor saw is not nSight's to get right.

The alternative — nSight masking before it calls a model — was rejected for a
reason that outlives any one call site: it would put the guarantee in the hands
of every present and future caller, and a caller that forgets fails silently,
sending real names to a vendor with nothing to notice. Datahive holds the
accepted terms as stored policy, so a prompt is masked because of where it is
sent, not because of who remembered to mask it.

**Fail closed.** `require_pseudonymization` is on, so datahive refuses (412)
rather than sending a prompt it would not mask — no accepted terms, licence
lapsed, tenant toggle off, no pseudonymizer. A refusal is raised as
:class:`EgoHiveError`, which every caller already treats as "no AI text this
time" and degrades to a deterministic default. Losing a generated headline is a
visibly worse deck; leaking the client's name is a different kind of problem.
"""
from __future__ import annotations

import logging
import os

import httpx

from nsight.agent.egohive_client import EgoHiveError

log = logging.getLogger(__name__)

#: What the text is FOR, in datahive's vocabulary. It selects the role and
#: through it the model, so an operator can move this workload without nSight
#: changing. Deliberately one of datahive's generic purposes rather than a word
#: like "title": the endpoint serves every caller, not this product.
PURPOSE = "synthesise"

#: Generous — a frontier completion behind a relay can take a while, and the
#: caller's own fallback is worse than waiting.
DEFAULT_TIMEOUT = 90.0

#: What kind of content the prose path sends, declared to datahive's egress
#: check. Unclassified content demands worst-case clearance there, which is the
#: right default for a caller that will not say — but we can say.
#:
#: "personal" is the honest answer for this product and not "none". A slide
#: title is built from a question and aggregated percentages, which is harmless
#: enough; but the SAME path writes themes from open-text answers, and a
#: respondent asked about care providers writes about their own health. Calling
#: that "none" would be a claim nobody checked, made once, in the direction that
#: turns a control off.
#:
#: A prompt carrying special-category or criminal-data content must NOT go
#: through this default — pass `regulatory_class` explicitly and let the hive's
#: egress policy decide whether that provider may see it.
REGULATORY_CLASS = "personal"


def datahive_chat(prompt: str, *, purpose: str = PURPOSE,
                  regulatory_class: str = REGULATORY_CLASS,
                  timeout: float = DEFAULT_TIMEOUT) -> str:
    """One completion, with the study's names hidden from the model.

    Signature-compatible with ``egohive_chat`` so it can be the default `chat`
    for :mod:`reportbuilder.ai.text` without touching any call site.

    Raises :class:`EgoHiveError` on anything that means "no answer" — including
    a refusal to send unmasked, which is a success of the control and a failure
    of the request.
    """
    if not prompt or not str(prompt).strip():
        raise EgoHiveError("datahive_chat requires a non-empty prompt.")
    url = os.environ.get("NSIGHT_DATAHIVE_URL")
    token = os.environ.get("NSIGHT_DATAHIVE_TOKEN")
    if not url or not token:
        # No route to the masking path is not a reason to take the unmasked
        # one. There isn't an unmasked one.
        raise EgoHiveError(
            "NSIGHT_DATAHIVE_URL/TOKEN are unset, so there is no masked route "
            "to a model; refusing to send the study's text anywhere else.")

    try:
        resp = httpx.post(
            url.rstrip("/") + "/api/v1/llm/ask",
            json={
                "prompt": prompt,
                "purpose": purpose,
                "regulatory_class": regulatory_class,
                "require_pseudonymization": True,
                "timeout_s": timeout,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout + 10,
        )
    except httpx.HTTPError as exc:
        raise EgoHiveError(f"could not reach datahive to ask the model: {exc}") from exc

    if resp.status_code == 412:
        # The control worked. Say so precisely — an operator reading "AI
        # unavailable" cannot tell a lapsed licence from an unset toggle.
        detail = _why(resp)
        log.warning("ai: datahive refused to send an unmasked prompt: %s", detail)
        raise EgoHiveError(f"datahive would not have masked this prompt: {detail}")
    if resp.status_code >= 400:
        raise EgoHiveError(f"datahive refused the request ({resp.status_code}): "
                           f"{resp.text[:200]}")

    data = resp.json() or {}
    # Assert it rather than assume it. The endpoint reports what it actually
    # did, and a False here means the prompt went out in clear despite the
    # request — worth failing the call over, not logging quietly.
    if not data.get("pseudonymized"):
        raise EgoHiveError(
            "datahive answered but reported the prompt was not pseudonymised")
    text = (data.get("text") or "").strip()
    if not text:
        raise EgoHiveError("datahive returned an empty completion")
    return text


def _why(resp: httpx.Response) -> str:
    """The specific missing condition datahive named, if it named one."""
    try:
        detail = (resp.json() or {}).get("detail")
    except ValueError:
        return resp.text[:200]
    if isinstance(detail, dict):
        return str(detail.get("why") or detail.get("message") or detail)
    return str(detail or resp.text[:200])
