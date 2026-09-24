"""Sending nSight's own mail (spec §6): config from datahive, and a
transport that must never raise -- see the module docstring.
"""
import smtplib

import pytest

from reportbuilder.auth import mailer


def test_no_config_at_all_is_none():
    assert mailer.config_from_settings({}) is None
    assert mailer.config_from_settings(None) is None


def test_missing_from_addr_is_none():
    assert mailer.config_from_settings({"host": "smtp.example.com"}) is None


def test_a_full_config_parses():
    cfg = mailer.config_from_settings({
        "host": "smtp.example.com", "port": 2525, "username": "u", "password": "p",
        "from_addr": "nsight@example.com", "use_tls": False})
    assert cfg == mailer.EmailConfig(host="smtp.example.com", port=2525, username="u",
                                     password="p", from_addr="nsight@example.com",
                                     use_tls=False)


def test_port_and_tls_default():
    cfg = mailer.config_from_settings({"host": "smtp.example.com", "from_addr": "a@b.c"})
    assert cfg.port == 587 and cfg.use_tls is True


class _FakeSMTP:
    """Records what would have been sent. Opens no socket."""
    instances: list = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.started_tls = False
        self.logged_in = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, username, password):
        self.logged_in = (username, password)

    def send_message(self, msg):
        self.sent = msg


@pytest.fixture(autouse=True)
def _reset_fake():
    _FakeSMTP.instances.clear()
    yield


def test_send_via_smtp_talks_to_the_configured_server(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    cfg = mailer.EmailConfig(host="smtp.example.com", port=587, username="u", password="p",
                             from_addr="nsight@example.com", use_tls=True)
    ok = mailer.send_via_smtp(cfg, "to@example.com", "Subject line", "Body text")
    assert ok is True
    [smtp] = _FakeSMTP.instances
    assert smtp.started_tls is True
    assert smtp.logged_in == ("u", "p")
    assert smtp.sent["To"] == "to@example.com"
    assert smtp.sent["Subject"] == "Subject line"


def test_send_via_smtp_skips_login_with_no_username(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    cfg = mailer.EmailConfig(host="h", port=25, username="", password="",
                             from_addr="a@b.c", use_tls=False)
    mailer.send_via_smtp(cfg, "to@example.com", "S", "B")
    [smtp] = _FakeSMTP.instances
    assert smtp.logged_in is None and smtp.started_tls is False


def test_send_via_smtp_never_raises_on_failure(monkeypatch):
    class _Boom:
        def __init__(self, *a, **k):
            raise OSError("connection refused")
    monkeypatch.setattr(smtplib, "SMTP", _Boom)
    cfg = mailer.EmailConfig(host="h", port=25, username="", password="",
                             from_addr="a@b.c", use_tls=False)
    assert mailer.send_via_smtp(cfg, "to@example.com", "S", "B") is False


# ---- the hive sends first (2026-09-25) ----------------------------------------

class _Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


def _hive_env(monkeypatch):
    monkeypatch.setenv("NSIGHT_DATAHIVE_URL", "https://hive.example/")
    monkeypatch.setenv("NSIGHT_DATAHIVE_TOKEN", "tok")


def test_send_via_hive_posts_to_the_hives_send_route(monkeypatch):
    _hive_env(monkeypatch)
    seen = {}

    def post(url, json, headers, timeout):
        seen.update(url=url, json=json, headers=headers)
        return _Resp(200)

    monkeypatch.setattr(mailer.httpx, "post", post)
    assert mailer.send_via_hive("a@b.c", "Hello", "<p>hi</p>") is True
    assert seen["url"] == "https://hive.example/api/v1/email/hive/send"
    assert seen["json"] == {"to": "a@b.c", "subject": "Hello", "body": "<p>hi</p>"}
    assert seen["headers"] == {"Authorization": "Bearer tok"}


@pytest.mark.parametrize("status", [400, 403, 404, 405, 502, 503])
def test_send_via_hive_is_false_on_every_refusal(monkeypatch, status):
    """400 no sender address, 503 no relay, 502 relay failed, 404/405 a hive
    without the route (the local one today)."""
    _hive_env(monkeypatch)
    monkeypatch.setattr(mailer.httpx, "post", lambda *a, **k: _Resp(status, "why"))
    assert mailer.send_via_hive("a@b.c", "s", "b") is False


def test_send_via_hive_never_raises_when_unreachable(monkeypatch):
    _hive_env(monkeypatch)

    def post(*a, **k):
        raise mailer.httpx.ConnectError("refused")

    monkeypatch.setattr(mailer.httpx, "post", post)
    assert mailer.send_via_hive("a@b.c", "s", "b") is False


def test_send_via_hive_without_a_hive_sends_nothing(monkeypatch):
    monkeypatch.delenv("NSIGHT_DATAHIVE_URL", raising=False)

    def post(*a, **k):
        raise AssertionError("must not be called")

    monkeypatch.setattr(mailer.httpx, "post", post)
    assert mailer.send_via_hive("a@b.c", "s", "b") is False


_SMTP = {"host": "smtp.example.com", "from_addr": "nsight@example.com"}


def test_deliver_uses_the_hive_and_not_smtp_when_the_hive_sends():
    smtp_calls = []
    ok = mailer.deliver(_SMTP, "a@b.c", "s", "text", "<p>html</p>",
                        hive=lambda to, subject, html: html == "<p>html</p>",
                        sender=lambda *a: smtp_calls.append(a) or True)
    assert ok is True and smtp_calls == []


def test_deliver_falls_back_to_smtp_with_the_text_body():
    smtp_calls = []
    ok = mailer.deliver(_SMTP, "a@b.c", "s", "text", "<p>html</p>",
                        hive=lambda *a: False,
                        sender=lambda cfg, to, subject, body: smtp_calls.append(body) or True)
    assert ok is True and smtp_calls == ["text"]


def test_deliver_with_neither_is_false():
    ok = mailer.deliver(None, "a@b.c", "s", "text", "html",
                        hive=lambda *a: False,
                        sender=lambda *a: pytest.fail("no SMTP is configured"))
    assert ok is False
