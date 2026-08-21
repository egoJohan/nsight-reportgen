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
