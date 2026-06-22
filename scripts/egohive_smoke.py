#!/usr/bin/env python3
"""Smoke test: get a REAL Gemini Finnish key message out of egoHive.

Calls egohive_narrate() against the running egoHive instance using the
credentials in work/egohive_creds.json and prints the assistant's reply.

Usage:
    python scripts/egohive_smoke.py
"""

import sys
from pathlib import Path

# Make src/ importable when run directly from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nsight.agent.egohive_client import EgoHiveError, egohive_narrate


def main() -> int:
    topic = "Autettu tunnettuus"
    numbers = {"Attendo": 86, "Esperi": 75}
    print(f"Topic:   {topic}")
    print(f"Numbers: {numbers}")
    print("Calling egoHive (real Gemini)...\n")
    try:
        reply = egohive_narrate(topic, numbers)
    except EgoHiveError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print("Gemini reply:")
    print(reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
