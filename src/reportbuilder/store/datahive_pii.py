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


def register_sensitive_terms(base_url: str, token: str, terms: list[str],
                             *, workspace_id: str | None = None,
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
