"""LIVE end-to-end: deterministic numbers (from datahive-stored SPSS) -> egoHive Gemini
agent writes the Finnish key message -> deck rendered.

Run: uv run python scripts/generate_live.py
Requires the running egoHive instance + work/egohive_creds.json (see scripts/egohive_smoke.py).
"""
from __future__ import annotations

from nsight import config
from nsight.agent.egohive_client import EgoHiveError, egohive_narrate
from nsight.fidelity.extract import extract_deck
from nsight.generate import generate_deck


def egohive_narrator(job, numbers: dict) -> str:
    # Flatten {chart: {brand: pct}} to the single chart's brand->pct for a focused prompt.
    flat = numbers
    if len(numbers) == 1:
        flat = next(iter(numbers.values()))
    topic = job.title or job.id
    msg = egohive_narrate(topic, flat)
    print(f"  [Gemini via egoHive] {job.id}: {msg}")
    return msg


def main() -> None:
    print("Generating deck with LIVE egoHive Gemini key messages...\n")
    out = generate_deck(
        sav=config.ATTENDO_SAV,
        brief_path=config.BRIEFS_DIR / "attendo.md",
        template=config.ATTENDO_TEMPLATE,
        out=config.GENERATED_PPTX,
        narrator=egohive_narrator,
    )
    print(f"\nDeck written: {out}")

    # Show the key message that actually landed on slide 14 (Text Placeholder 5)
    deck = extract_deck(out)
    texts = deck.slides[14].texts
    print("\nText on slide 14 (incl. the Gemini-written key message):")
    for t in texts:
        print("  -", t[:160])


if __name__ == "__main__":
    try:
        main()
    except EgoHiveError as e:
        print(f"egoHive unavailable: {e}\n(Falls back to offline narrator in generate_deck "
              f"if you pass narrator=None.)")
