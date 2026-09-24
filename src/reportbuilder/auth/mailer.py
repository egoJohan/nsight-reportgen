"""Sending nSight's own mail: invitation links (spec §6), and an access
request nudging whoever can decide it (auth/access_request_mail.py).

THE HIVE SENDS FIRST (2026-09-25): `send_via_hive` posts to the hive's
`POST /api/v1/email/hive/send`, which sends as the hive itself through its
configured relay -- the same hive, URL and token nSight stores its data in.
SMTP (`settings/email.json`) is the fallback, used only when the hive does not
send (no sender configured, no relay, a hive too old to have the route) and
SMTP is configured. `deliver` is the one place that order is decided.

No mail-provider dependency: smtplib is the standard library. Configuration
lives in datahive (`settings/email.json`, spec §9) rather than an
environment variable, so moving hive moves the mail setup with it (spec
§2). Every kind of email nSight sends is a small module next to this one
(auth/invites.py, auth/access_request_mail.py) composing `EmailConfig`,
`config_from_settings` and `send_via_smtp` from here -- this module owns
only the transport and the config shape, never a message's subject or
body. If a second kind of TRANSPORT is ever needed (an API provider
instead of raw SMTP), that is a second function next to send_via_smtp,
not a rewrite of this module's shape.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable

import httpx

log = logging.getLogger(__name__)

EMAIL_KEY = "email.json"


@dataclass(frozen=True)
class EmailConfig:
    host: str
    port: int
    username: str
    password: str
    from_addr: str
    use_tls: bool = True


def config_from_settings(stored: dict | None) -> "EmailConfig | None":
    """*stored* is whatever `Repository.get_setting(auth, EMAIL_KEY)`
    returns. None when unconfigured -- a caller with no config must send
    nothing, not raise (spec §6: "delivery may fail without failing the
    invitation")."""
    if not stored or not stored.get("host") or not stored.get("from_addr"):
        return None
    return EmailConfig(
        host=stored["host"],
        port=int(stored.get("port") or 587),
        username=stored.get("username", ""),
        password=stored.get("password", ""),
        from_addr=stored["from_addr"],
        use_tls=bool(stored.get("use_tls", True)),
    )


#: (config, to, subject, body) -> True if the message was handed to the
#: server successfully. Injected everywhere email is sent, so a test never
#: opens a real socket -- see auth/invites.py.
Sender = Callable[[EmailConfig, str, str, str], bool]


def send_via_smtp(config: EmailConfig, to: str, subject: str, body: str) -> bool:
    """The real transport. Never raises -- a delivery failure must not
    fail the invitation it was sent for (spec §6); the caller decides what
    False means for the UI (`emailed: false` plus the link to copy)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.from_addr
    msg["To"] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP(config.host, config.port, timeout=10) as smtp:
            if config.use_tls:
                smtp.starttls(context=ssl.create_default_context())
            if config.username:
                smtp.login(config.username, config.password)
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        log.warning("invitation email to '%s' could not be sent: %s", to, exc)
        return False


#: (to, subject, html) -> True if the hive accepted the message for sending.
#: Injected like `Sender`, so no test reaches a hive.
HiveSender = Callable[[str, str, str], bool]

HIVE_SEND_PATH = "/api/v1/email/hive/send"


def send_via_hive(to: str, subject: str, html: str) -> bool:
    """Send through the hive nSight stores its data in. Never raises.

    False -- and nothing sent -- when nSight has no hive (the env is unset,
    as in tests), or the hive refuses: 400 names a caller fault such as "no
    configured sender address", 503 means no working relay, 502 a relay that
    failed, 404/405 a hive without the route. Each is logged with the hive's
    own words, because "email not sent" alone sends an operator looking in
    the wrong place.
    """
    url = os.environ.get("NSIGHT_DATAHIVE_URL")
    token = os.environ.get("NSIGHT_DATAHIVE_TOKEN")
    if not url or not token:
        return False
    try:
        resp = httpx.post(url.rstrip("/") + HIVE_SEND_PATH,
                          json={"to": to, "subject": subject, "body": html},
                          headers={"Authorization": f"Bearer {token}"},
                          timeout=30)
    except httpx.HTTPError as exc:
        log.warning("email to '%s' via the hive: could not reach it: %s", to, exc)
        return False
    if resp.status_code == 200:
        return True
    log.warning("email to '%s' via the hive refused (%s): %s",
                to, resp.status_code, resp.text[:300])
    return False


def deliver(stored_email_settings: dict | None, to: str, subject: str, text: str,
            html: str, *, hive: HiveSender = send_via_hive,
            sender: Sender = send_via_smtp) -> bool:
    """Send one message: through the hive, else over SMTP when configured.

    *stored_email_settings* is `settings/email.json` as the caller read it.
    Never raises; False means nobody was emailed and the caller falls back
    (an invitation's copy-this-link)."""
    if hive(to, subject, html):
        return True
    config = config_from_settings(stored_email_settings)
    return config is not None and sender(config, to, subject, text)
