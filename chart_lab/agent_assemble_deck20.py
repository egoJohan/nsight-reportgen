"""Assemble the ordered 20-slide attendo_agent_deck20.pptx from source decks.

Reuses the slide-merge machinery from agent_assemble_deck.py (deep-copy each
source slide part + its rel graph + media into a blank 16:9 deck), only the
ORDER list and output path differ.

Run: uv run python chart_lab/agent_assemble_deck20.py
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation

from agent_assemble_deck import build, WORK

OUT = WORK / "attendo_agent_deck20.pptx"

# Ordered list of (source file stem, 1-based slide number) to copy.
ORDER = [
    ("agent_dense_awareness", 1),  # 1  grouped multi-wave bar + change column
    ("agent_var_awareness", 6),    # 2  vertical columns
    ("agent_var_awareness", 3),    # 3  lollipop
    ("agent_var_awareness", 5),    # 4  bar + average reference line
    ("agent_slide_trend", 1),      # 5  multi-line trend
    ("agent_var_awareness", 1),    # 6  slope chart
    ("agent_var_awareness", 2),    # 7  dumbbell
    ("agent_var_awareness", 4),    # 8  bump / rank chart
    ("agent_dense_opinion", 1),    # 9  stacked + positive trend + change
    ("agent_var_wordsop", 3),      # 10 tornado / diverging
    ("agent_slide_radar", 1),      # 11 radar small multiples
    ("agent_var_image", 1),        # 12 heatmap
    ("agent_var_image", 2),        # 13 clustered dot plot
    ("agent_var_image", 3),        # 14 net-image diverging bar
    ("agent_var_image", 4),        # 15 grouped 3-brand bar
    ("agent_dense_brandimage", 1), # 16 brand-image 14 attrs × 4 waves + change
    ("agent_brand_images", 4),     # 17 brand-image bar — Onnikodit
    ("agent_dense_words", 1),      # 18 TOP-10 × 4 waves
    ("agent_var_wordsop", 1),      # 19 word cloud
    ("agent_var_wordsop", 2),      # 20 treemap
]


if __name__ == "__main__":
    p = build(order=ORDER, out_path=OUT)
    final = Presentation(p)
    print(f"Wrote {p} with {len(final.slides._sldIdLst)} slides")
