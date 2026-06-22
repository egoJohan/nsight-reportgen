"""Task 4.2 — Extract prior-wave aided-awareness from the Attendo template deck.

Reads the slide-14 ("Content Placeholder 9") aided-awareness chart, which holds 4
wave series. For each wave series and each brand category, stores the whole-percent
value into WaveHistory(config.WAVES_JSON) under metric "aided_awareness", key=brand,
wave=series name. Proportions (0..1) are converted to whole percents; None values
(a brand absent in an early wave) are skipped.
"""

from __future__ import annotations

from nsight import config
from nsight.fidelity.extract import extract_deck
from nsight.waves import WaveHistory

SLIDE_IDX = 14
CHART_NAME = "Content Placeholder 9"
METRIC = "aided_awareness"


def main() -> None:
    deck = extract_deck(config.ATTENDO_TEMPLATE)
    slide = deck.slides[SLIDE_IDX]
    chart = next(c for c in slide.charts if c.name == CHART_NAME)

    history = WaveHistory(config.WAVES_JSON)

    summary: dict[str, int] = {}
    for wave, values in chart.series.items():
        stored = 0
        for brand, value in zip(chart.categories, values):
            if value is None:
                continue
            history.set(wave, METRIC, brand, round(value * 100))
            stored += 1
        summary[wave] = stored

    print(f"Wrote aided-awareness to {config.WAVES_JSON}")
    print(f"Waves found ({len(summary)}):")
    for wave, count in summary.items():
        attendo = history.get(wave, METRIC, "Attendo")
        print(f"  {wave!r}: {count} brands  (Attendo={attendo})")


if __name__ == "__main__":
    main()
