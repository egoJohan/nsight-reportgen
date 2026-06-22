"""Claude-as-judge harness for visual/subjective gates (design §12)."""
from __future__ import annotations
import base64
import io
import json
import os
import re
from dataclasses import dataclass
import anthropic

_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 1024

@dataclass(frozen=True)
class JudgeVerdict:
    passed: bool
    reasoning: str
    confidence: float                # 0..1

def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def _parse_verdict(text: str) -> JudgeVerdict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    payload = json.loads(m.group(0) if m else text)
    return JudgeVerdict(
        passed=bool(payload["passed"]),
        reasoning=str(payload["reasoning"]),
        confidence=float(payload["confidence"]),
    )

def _judge_png_bytes(png_b64: str, rubric: str, requirement_id: str, extra_context: str) -> JudgeVerdict:
    prompt = (
        f"Requirement under test: {requirement_id}\n\n"
        f"Rubric:\n{rubric}\n\n"
        f"{extra_context}\n\n"
        "Inspect the attached image and return ONLY a JSON object: "
        '{"passed": <bool>, "reasoning": <string>, "confidence": <number 0..1>}.'
    )
    resp = _client().messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        temperature=0,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png_b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return _parse_verdict(resp.content[0].text)

def judge_image(png_path: str, rubric: str, *, requirement_id: str, extra_context: str = "") -> JudgeVerdict:
    with open(png_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return _judge_png_bytes(b64, rubric, requirement_id, extra_context)

def judge_pdf(pdf_path: str, rubric: str, *, requirement_id: str) -> list[JudgeVerdict]:
    """Rasterize each PDF page to PNG and judge it. One verdict per page."""
    import pdfplumber
    verdicts: list[JudgeVerdict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            img = page.to_image(resolution=120)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            verdicts.append(_judge_png_bytes(b64, rubric, requirement_id, ""))
    return verdicts
