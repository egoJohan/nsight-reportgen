"""Integration tests for attendo_interim_spec() — Task 5.2 (REQ-C-27a / C-27b marker)."""
from __future__ import annotations
import pytest

from reportbuilder import config
from reportbuilder.render.style_spec import attendo_interim_spec


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def spec():
    if not config.ATTENDO_TEMPLATE.exists():
        pytest.skip(f"Attendo template not found: {config.ATTENDO_TEMPLATE}")
    return attendo_interim_spec()


def test_attendo_spec_dimensions(spec):
    """Real Attendo deck must be standard 16:9 (12192000×6858000 EMU) with ≥1 slot."""
    assert spec.slide_width == 12192000
    assert spec.slide_height == 6858000
    assert len(spec.slots()) >= 1


def test_attendo_spec_blocked_marker(spec):
    """REQ-C-27b is blocked: matches_client_spec must be False, spec_source marked."""
    assert spec.matches_client_spec is False
    assert spec.spec_source == "attendo-interim-proxy"
