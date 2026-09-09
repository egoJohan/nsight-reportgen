"""Registering a study's sensitive terms with datahive's PII policy.

datahive does the pseudonymisation — it holds the map, it substitutes on the
way out to a model and restores on the way back. What it needs from nSight is
the list of terms, and it takes that as STORED POLICY (`deny_terms`) rather
than as a per-request argument.

That distinction is the whole point. If the terms rode along with each prompt,
the guarantee would depend on every present and future call site remembering to
attach them — and a call site that forgets fails silently, sending real names
to a model with nothing to notice. Registered as policy, a caller that forgets
everything still gets masked text, because the masking is not the caller's job.

Terms register under ORGANIZATION with score 1.0 and are matched as
case-insensitive substrings, so `Attendo` also covers `Attendosta`, `Attendon`
and `Attendolla` — which is what makes this work in Finnish, where the shipped
NER model finds about 15 % of brand mentions and every inflected form is a form
it did not see.

Names whose stem MOVES (`Mehiläinen` → `Mehiläisestä`) need a morphology rule,
and that rule lives in datahive, keyed by the language we declare here. It is
declared rather than guessed: see `TERM_LANGUAGE`.
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

#: The entity type accepted terms register under. Anything datahive detects at
#: this type is pseudonymised; the type name is datahive's, not ours.
ENTITY_TYPE = "ORGANIZATION"

#: Detection types the policy asks for alongside the terms. ORGANIZATION is
#: excluded from datahive's defaults for a good reason — spaCy scores any
#: capitalised token 0.85, so as a DETECTOR it is noise — but the terms below
#: arrive at score 1.0 from an explicit list, so enabling the type is what lets
#: them through rather than a claim that the model is any good at it.
ENABLED_TYPES = (ENTITY_TYPE, "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER")


class RegistrationFailed(RuntimeError):
    """The terms did not reach datahive.

    Raised rather than logged, and the caller must not record the acceptance:
    a study whose terms are accepted locally but absent from datahive's policy
    is the exact failure this feature exists to prevent — the report gate opens
    and nothing is masked.
    """


#: The language our terms are written in, declared to datahive rather than left
#: to its language router. The router reads a language off the text in front of
#: it, and our text is survey labels and chart titles — three words with no
#: function word to go on. Guessing there sends Finnish terms down the English
#: path, where the `-nen` stem rule never fires and `Mehiläisestä` stops
#: matching `Mehiläinen`, with nothing in the output to say so.
TERM_LANGUAGE = "fi"


def register_sensitive_terms(base_url: str, token: str, terms: list[str],
                             *, workspace_id: str | None = None,
                             language: str = TERM_LANGUAGE,
                             timeout: float = 30.0) -> dict:
    """Store *terms* as datahive's deny list, replacing what is there.

    Replacing rather than merging is deliberate: the accepted list is the whole
    truth about what must be masked, and a merge would make a REMOVED term keep
    being masked for ever with nothing showing why.

    Raises :class:`RegistrationFailed` on anything other than success. The
    caller is expected to let that propagate.
    """
    url = base_url.rstrip("/") + "/api/v1/pii/policy"
    payload = {
        "workspace_id": workspace_id,
        "policy": {
            "enabled_types": list(ENABLED_TYPES),
            "term_language": language,
            "deny_terms": {ENTITY_TYPE: list(terms)},
        },
    }
    try:
        resp = httpx.put(url, json=payload, timeout=timeout,
                         headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as exc:
        raise RegistrationFailed(
            f"could not reach datahive to register the terms: {exc}") from exc
    if resp.status_code >= 400:
        raise RegistrationFailed(
            f"datahive refused the terms ({resp.status_code}): {resp.text[:200]}")

    # READ IT BACK. A 2xx says the request was accepted, not that the policy
    # now contains these terms — and the difference is the whole protection.
    # Nothing catches it downstream either: `/llm/ask` answers
    # `pseudonymized: true` when the deny list is EMPTY, because the flag means
    # "the pseudonymiser ran", not "your terms were masked". So this is the only
    # place the claim can be checked. (Johan, 2026-09-09)
    live = set(registered_terms(base_url, token, workspace_id=workspace_id,
                                timeout=timeout))
    missing = [t for t in terms if t not in live]
    if missing:
        raise RegistrationFailed(
            f"datahive accepted the request but {len(missing)} term(s) are not "
            f"in its policy afterwards (e.g. {missing[:3]}); nothing would be "
            "masked for them")
    log.info("pii: registered %s sensitive term(s) with datahive", len(terms))
    return {"registered": len(terms)}


def registered_terms(base_url: str, token: str, *,
                     workspace_id: str | None = None,
                     timeout: float = 30.0) -> list[str]:
    """What datahive currently holds. For showing the truth rather than what we
    believe we sent."""
    url = base_url.rstrip("/") + "/api/v1/pii/policy"
    params = {"workspace_id": workspace_id} if workspace_id else None
    try:
        resp = httpx.get(url, params=params, timeout=timeout,
                         headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        policy = (resp.json() or {}).get("policy") or {}
    except (httpx.HTTPError, ValueError) as exc:
        raise RegistrationFailed(f"could not read datahive's policy: {exc}") from exc
    return [str(t) for t in (policy.get("deny_terms") or {}).get(ENTITY_TYPE, [])]


#: How long a policy read is trusted before it is asked again. The list changes
#: only when somebody accepts terms, and the check below runs once per AI call —
#: a Design step asks for a headline per chart, so re-reading the policy sixty
#: times in a minute buys nothing.
_POLICY_TTL_S = 30.0
_policy_cache: dict[str, tuple[float, frozenset[str]]] = {}


def live_terms(base_url: str, token: str, *, now: float,
               workspace_id: str | None = None) -> frozenset[str]:
    """What datahive is masking on right now, cached for `_POLICY_TTL_S`."""
    key = f"{base_url}|{workspace_id or ''}"
    hit = _policy_cache.get(key)
    if hit is not None and now - hit[0] < _POLICY_TTL_S:
        return hit[1]
    terms = frozenset(registered_terms(base_url, token, workspace_id=workspace_id))
    _policy_cache[key] = (now, terms)
    return terms


def forget_policy_cache() -> None:
    """Drop what we believe datahive holds. Called after a write, so the next
    check reads the new truth rather than the 30 seconds either side of it."""
    _policy_cache.clear()
