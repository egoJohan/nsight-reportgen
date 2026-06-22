from __future__ import annotations

from dataclasses import dataclass, field

from nsight.fidelity.extract import DeckData


@dataclass
class FidelityReport:
    chart_score: float
    charts_matched: int
    charts_total: int
    mismatches: list[str] = field(default_factory=list)


def _as_pct(v: float) -> float:
    return round(v * 100) if abs(v) <= 1.0 else round(v)


def compare_decks(generated: DeckData, original: DeckData) -> FidelityReport:
    matched = 0
    total = 0
    mismatches: list[str] = []
    for og_slide in original.slides:
        gen_slide = next((s for s in generated.slides if s.idx == og_slide.idx), None)
        for k, og_chart in enumerate(og_slide.charts):
            gen_chart = gen_slide.charts[k] if gen_slide and k < len(gen_slide.charts) else None
            for sname, ovals in og_chart.series.items():
                for j, oval in enumerate(ovals):
                    total += 1
                    gval = None
                    if gen_chart and sname in gen_chart.series and j < len(gen_chart.series[sname]):
                        gval = gen_chart.series[sname][j]
                    # Both None → match
                    if oval is None and gval is None:
                        matched += 1
                    # Exactly one is None → mismatch
                    elif oval is None or gval is None:
                        mismatches.append(
                            f"slide {og_slide.idx} chart {og_chart.name} [{sname}][{j}]: "
                            f"got {gval}, want {oval}")
                    # Both have values → compare by rounded percent
                    elif _as_pct(gval) == _as_pct(oval):
                        matched += 1
                    else:
                        mismatches.append(
                            f"slide {og_slide.idx} chart {og_chart.name} [{sname}][{j}]: "
                            f"got {gval}, want {oval}")
    score = (matched / total * 100.0) if total else 0.0
    return FidelityReport(chart_score=round(score, 1), charts_matched=matched,
                          charts_total=total, mismatches=mismatches)
