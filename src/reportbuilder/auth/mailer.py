"""Sending nSight's own mail: invitation links (spec §6), and an access
request nudging whoever can decide it (auth/access_request_mail.py).

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
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable

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
