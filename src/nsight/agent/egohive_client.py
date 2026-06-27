"""Reusable client for getting Finnish prose out of a running egoHive instance.

The nSight deck generator uses egoHive's Gemini-backed agent to turn raw
survey numbers into short Finnish key messages ("avainviestit").

How it works
------------
egoHive serves chat through a per-agent *endpoint*. A chat turn is two calls:

1. ``POST {base_url}/session/{endpoint_id}``  -> mint a ``session_id``
2. ``POST {base_url}/chat/{session_id}``      -> send a message, read the reply

The endpoint we use is configured with ``auth_type=none`` so the chat itself
needs no bearer token (the ``session_id`` is the credential). The stored
``email``/``password`` are kept for management/diagnostic calls (listing models,
recreating the agent) and are used by :func:`login` -> a bearer token.

Configuration is read from ``work/egohive_creds.json`` (gitignored) so no
secrets are hardcoded. Expected keys:

    base_url, endpoint_id, agent_id, model, auth_scheme,
    email, password  (optional, for management calls)

Public API
----------
    egohive_narrate(topic, numbers, **opts) -> str
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Optional

# Default location of the gitignored credentials file.
DEFAULT_CREDS_PATH = (
    Path(__file__).resolve().parents[3] / "work" / "egohive_creds.json"
)

# Network timeout (seconds) for a single egoHive HTTP call. Gemini completions
# can take a few seconds, so keep this generous.
DEFAULT_TIMEOUT = 60.0


class EgoHiveError(RuntimeError):
    """Raised when egoHive is unreachable, returns an error, or auth fails."""


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def load_creds(creds_path: str | Path | None = None) -> dict[str, Any]:
    """Load the egoHive credential/config blob.

    Raises EgoHiveError with an actionable message if the file is missing or
    malformed.
    """
    path = Path(creds_path) if creds_path else DEFAULT_CREDS_PATH
    if not path.exists():
        raise EgoHiveError(
            f"egoHive credentials file not found at {path}. "
            "Expected a JSON file with at least 'base_url' and 'endpoint_id'."
        )
    try:
        creds = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EgoHiveError(f"Could not read egoHive credentials at {path}: {exc}") from exc
    if not creds.get("base_url") or not creds.get("endpoint_id"):
        raise EgoHiveError(
            f"egoHive credentials at {path} are missing 'base_url' and/or "
            "'endpoint_id'."
        )
    return creds


# --------------------------------------------------------------------------- #
# Low-level HTTP
# --------------------------------------------------------------------------- #
def _request(
    method: str,
    url: str,
    *,
    body: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """Perform a JSON HTTP request, returning the parsed JSON response.

    Translates transport errors and non-2xx responses into EgoHiveError with a
    clear message (and the egoHive error code/detail when available).
    """
    data = None
    hdrs = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)

    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(detail)
            detail = parsed.get("detail", parsed)
        except json.JSONDecodeError:
            pass
        raise EgoHiveError(
            f"egoHive {method} {url} failed: HTTP {exc.code} {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise EgoHiveError(
            f"egoHive unreachable at {url}: {exc.reason}. "
            "Is the egohive-api container running on this host?"
        ) from exc

    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EgoHiveError(f"egoHive returned non-JSON from {url}: {raw[:200]!r}") from exc


# --------------------------------------------------------------------------- #
# Auth (management / diagnostics)
# --------------------------------------------------------------------------- #
def login(creds: Mapping[str, Any], *, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Obtain a bearer access token via email/password.

    Used for management calls (e.g. listing models). NOT required for chat,
    which authenticates via the minted session_id. Raises EgoHiveError if no
    email/password are configured or login fails.
    """
    email = creds.get("email")
    password = creds.get("password")
    if not email or not password:
        raise EgoHiveError(
            "No email/password in egoHive credentials; cannot obtain a bearer token."
        )
    base_url = creds["base_url"].rstrip("/")
    resp = _request(
        "POST",
        f"{base_url}/auth/login",
        body={"email": email, "password": password},
        timeout=timeout,
    )
    token = (resp or {}).get("access_token")
    if not token:
        raise EgoHiveError(f"egoHive login returned no access_token: {resp!r}")
    return token


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #
def _create_session(
    base_url: str, endpoint_id: str, *, timeout: float = DEFAULT_TIMEOUT
) -> str:
    """Mint a chat session from the agent endpoint, returning the session_id."""
    resp = _request(
        "POST",
        f"{base_url}/session/{endpoint_id}",
        body={},
        # auth_type=none validates Origin against allowed_origins (empty -> any),
        # but sending an Origin keeps us compatible if it is ever locked down.
        headers={"Origin": base_url},
        timeout=timeout,
    )
    session_id = (resp or {}).get("session_id")
    if not session_id:
        raise EgoHiveError(f"egoHive session creation returned no session_id: {resp!r}")
    return session_id


def _send_message(
    base_url: str, session_id: str, content: str, *, timeout: float = DEFAULT_TIMEOUT
) -> str:
    """Send one chat message and return the assistant's text reply."""
    resp = _request(
        "POST",
        f"{base_url}/chat/{session_id}",
        body={"content": content},
        timeout=timeout,
    )
    text = (resp or {}).get("content")
    if text is None:
        raise EgoHiveError(f"egoHive chat returned no content: {resp!r}")
    return text.strip()


def _build_prompt(topic: str, numbers: Mapping[str, Any]) -> str:
    """Compose the Finnish narration request from topic + numbers."""
    numbers_json = json.dumps(dict(numbers), ensure_ascii=False)
    return (
        f"Aihe: {topic}. "
        f"Luvut: {numbers_json}. "
        "Kirjoita yksi lyhyt suomenkielinen avainviesti naiden lukujen pohjalta. "
        "Mainitse suurin arvo ja sita vastaava nimi."
    )


def egohive_narrate(
    topic: str,
    numbers: Mapping[str, Any],
    *,
    base_url: Optional[str] = None,
    endpoint_id: Optional[str] = None,
    creds_path: str | Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Return a short Finnish key message for ``topic`` given ``numbers``.

    Authenticates/configures from ``work/egohive_creds.json`` (overridable via
    ``creds_path``), sends the topic + numbers to the egoHive Gemini agent via
    the chat API, and returns the assistant's text.

    Args:
        topic: The survey topic, e.g. "Autettu tunnettuus".
        numbers: Mapping of label -> value, e.g. {"Attendo": 86, "Esperi": 75}.
        base_url: Override the configured egoHive API base (".../api/v1").
        endpoint_id: Override the configured agent endpoint id.
        creds_path: Override the credentials file location.
        timeout: Per-request network timeout in seconds.

    Returns:
        The assistant's Finnish reply text.

    Raises:
        EgoHiveError: if egoHive is unreachable, auth/config is invalid, or the
            chat call fails.
    """
    if not topic or not str(topic).strip():
        raise EgoHiveError("egohive_narrate requires a non-empty topic.")
    if not numbers:
        raise EgoHiveError("egohive_narrate requires a non-empty numbers mapping.")

    creds = load_creds(creds_path)
    base = (base_url or creds["base_url"]).rstrip("/")
    ep = endpoint_id or creds["endpoint_id"]

    session_id = _create_session(base, ep, timeout=timeout)
    prompt = _build_prompt(topic, numbers)
    return _clean(_send_message(base, session_id, prompt, timeout=timeout))


def egohive_chat(
    prompt: str,
    *,
    base_url: Optional[str] = None,
    endpoint_id: Optional[str] = None,
    creds_path: str | Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Generic one-shot chat turn against the egoHive Gemini agent.

    Mints a fresh session, sends ``prompt``, and returns the assistant's text
    reply with markdown emphasis and surrounding quotes stripped. Unlike
    :func:`_clean`, this PRESERVES line breaks so callers that batch several
    items into a single prompt (e.g. a numbered list) can parse the multi-line
    reply; callers that want a single headline line should apply :func:`_clean`.

    Args:
        prompt: The full prompt text to send.
        base_url / endpoint_id / creds_path: Optional overrides; default to the
            values in ``work/egohive_creds.json``.
        timeout: Per-request network timeout in seconds.

    Returns:
        The assistant's cleaned reply text (line breaks preserved).

    Raises:
        EgoHiveError: if the prompt is empty, config/creds are invalid, or the
            egoHive call fails (unreachable / non-2xx / malformed response).
    """
    if not prompt or not str(prompt).strip():
        raise EgoHiveError("egohive_chat requires a non-empty prompt.")

    creds = load_creds(creds_path)
    base = (base_url or creds["base_url"]).rstrip("/")
    ep = endpoint_id or creds["endpoint_id"]

    session_id = _create_session(base, ep, timeout=timeout)
    reply = _send_message(base, session_id, prompt, timeout=timeout)

    # Light cleanup that keeps newlines (single-line callers apply _clean).
    cleaned = (reply or "").replace("**", "").replace("__", "").strip()
    if len(cleaned) >= 2 and cleaned[0] in "\"'" and cleaned[-1] in "\"'":
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _clean(text: str) -> str:
    """Strip markdown emphasis and surrounding quotes the model may add, keep one line."""
    t = (text or "").strip()
    t = t.replace("**", "").replace("__", "")
    if len(t) >= 2 and t[0] in "\"'" and t[-1] in "\"'":
        t = t[1:-1].strip()
    return t.split("\n")[0].strip()


__all__ = ["egohive_narrate", "egohive_chat", "login", "load_creds", "EgoHiveError"]
