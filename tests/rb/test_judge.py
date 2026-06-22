"""Tests for reportbuilder.testing.judge (Claude-as-judge harness, design §12)."""
from __future__ import annotations
import io
import os
import json
from unittest.mock import MagicMock, patch

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from reportbuilder.testing.rubrics import rubric_for


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_response(payload: dict) -> MagicMock:
    """Build a fake anthropic Messages response with one text content block."""
    msg = MagicMock()
    msg.content = [MagicMock()]
    msg.content[0].text = json.dumps(payload)
    return msg


def _make_tiny_png(tmp_path) -> str:
    """Render a small bar chart to a PNG file and return its path."""
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar(["A", "B", "C"], [10, 20, 15])
    path = str(tmp_path / "chart.png")
    fig.savefig(path)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Mocked unit tests
# ---------------------------------------------------------------------------

def test_judge_image_mocked_pass(tmp_path):
    """judge_image passes through a happy-path verdict and uses correct model/temperature."""
    png_path = _make_tiny_png(tmp_path)
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response(
        {"passed": True, "reasoning": "clean", "confidence": 0.9}
    )

    with patch("reportbuilder.testing.judge._client", return_value=fake_client):
        from reportbuilder.testing.judge import judge_image
        verdict = judge_image(png_path, "some rubric", requirement_id="R3-LAYOUT")

    assert verdict.passed is True
    assert verdict.reasoning == "clean"
    assert verdict.confidence == pytest.approx(0.9)

    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-8"
    assert call_kwargs["temperature"] == 0


def test_judge_image_mocked_fail(tmp_path):
    """judge_image surfaces a fail verdict with correct reasoning text."""
    png_path = _make_tiny_png(tmp_path)
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response(
        {"passed": False, "reasoning": "labels overlap at top", "confidence": 0.8}
    )

    with patch("reportbuilder.testing.judge._client", return_value=fake_client):
        from reportbuilder.testing.judge import judge_image
        verdict = judge_image(png_path, "some rubric", requirement_id="R3-LAYOUT")

    assert verdict.passed is False
    assert "overlap" in verdict.reasoning
    assert verdict.confidence == pytest.approx(0.8)


def test_judge_image_tolerates_fenced_json(tmp_path):
    """_parse_verdict handles ```json fenced code blocks correctly."""
    png_path = _make_tiny_png(tmp_path)
    fenced_text = '```json\n{"passed": true, "reasoning": "all good", "confidence": 1.0}\n```'

    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.content = [MagicMock()]
    fake_response.content[0].text = fenced_text
    fake_client.messages.create.return_value = fake_response

    with patch("reportbuilder.testing.judge._client", return_value=fake_client):
        from reportbuilder.testing.judge import judge_image
        verdict = judge_image(png_path, "some rubric", requirement_id="R3-LAYOUT")

    assert verdict.passed is True
    assert verdict.confidence == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Live smoke test (skips without ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------

@pytest.mark.judge
def test_judge_image_live_clean_chart(tmp_path):
    """Live: render an obviously-clean bar chart and expect Claude to pass it."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    fig, ax = plt.subplots(figsize=(8, 5))
    categories = ["Strongly Agree", "Agree", "Neutral", "Disagree", "Strongly Disagree"]
    values = [45, 30, 15, 7, 3]
    bars = ax.bar(categories, values, color="#4472C4")
    ax.set_title("Agreement Distribution", pad=12)
    ax.set_ylabel("Percentage (%)")
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.5,
            f"{val}%",
            ha="center",
            va="bottom",
            fontsize=10,
        )
    plt.tight_layout()
    path = str(tmp_path / "clean_chart.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)

    from reportbuilder.testing.judge import judge_image
    verdict = judge_image(path, rubric_for("R3-LAYOUT"), requirement_id="R3-LAYOUT")
    assert verdict.passed is True
