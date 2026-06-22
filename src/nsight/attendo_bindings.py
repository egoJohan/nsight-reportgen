"""Empirical bindings tying the Attendo SPSS data to the deck's reported figures.

Discovered for Task 1.4. The aided-awareness ("autettu tunnettuus") question is a
multi-select grid: one variable per brand, coded 0=Unchecked / 1=Checked. The deck
reports the share of respondents who checked each brand, UNWEIGHTED, over the full
base of n=1001 (no weight variable exists in the .sav).

Ground-truth numbers come from slide index 14 (deck slide 15), chart
"Content Placeholder 9", series "Marraskuu 2025" (the current wave). Values in the
chart are proportions 0..1; here expressed as whole percents.
"""

from __future__ import annotations

# Aided-awareness question: "Mitä seuraavista hoivapalveluiden tarjoajista
# tunnet vähintään nimeltä?" (var18 grid). One variable per brand.
# NOTE: variable order is NOT the brand order shown in the deck — Rinnekodit and
# Validia in particular are out of sequence, so the mapping is by label, not index.
AIDED_AWARENESS_VARS: dict[str, str] = {
    "Attendo": "var18O45",
    "Esperi": "var18O46",
    "Rinnekodit": "var18O51",
    "Validia": "var18O52",
    "Onnikodit": "var18O48",
    "Mainio-kodit": "var18O47",
    "Ykköskodit": "var18O49",
    "Humana": "var18O50",
    "En mitään näistä": "var18O53",
}

# Multi-select coding: {0.0: 'Unchecked', 1.0: 'Checked'}. "Knows" == Checked == 1.
AIDED_AWARENESS_POSITIVE: list[float] = [1.0]

# No weight variable exists in the dataset; the deck is reported unweighted.
WEIGHT_VAR: str | None = None

# Deck ground truth (slide idx 14, series "Marraskuu 2025"), as whole percents.
DECK_AIDED_AWARENESS: dict[str, int] = {
    "Attendo": 86,
    "Esperi": 75,
    "Rinnekodit": 42,
    "Validia": 33,
    "Onnikodit": 26,
    "Mainio-kodit": 22,
    "Ykköskodit": 15,
    "Humana": 13,
    "En mitään näistä": 5,
}

# ---------------------------------------------------------------------------
# Brand-image spontaneous words (Task 4.4).
#
# Question "Millä kolmella sanalla kuvailisit mielikuvaasi Attendosta?" — three
# open-ended (string) variables, one per word slot. Base = "kaikki vastaajat"
# (everyone who answered; deck reports n=863, our data has 817 answering).
# ---------------------------------------------------------------------------
IMAGE_WORD_VARS: list[str] = ["var37O67", "var37O68", "var37O69"]

# Collapse obvious inflectional / spelling variants to the canonical lemma the
# deck's manual coding used. Keys are normalized (lowercased, stripped) tokens.
IMAGE_SYNONYMS: dict[str, str] = {
    # kiire-family — deck lists this as a single "Kiire/kiireinen" entry.
    "kiireinen": "kiire",
    "kiiree": "kiire",
    "kiireellinen": "kiire",
    "kiireinen työtahti": "kiire",
    # huolehtiva-family.
    "huolehtii": "huolehtiva",
    "huolehtia": "huolehtiva",
    "huolehtivainen": "huolehtiva",
    # kallis spelling slip.
    "kallia": "kallis",
}

# ---------------------------------------------------------------------------
# M-1: Segment bindings + deck bases.
#
# Real-variable segment definitions live in segments.py. The deck's current-wave
# segment bases (slide idx 15, first chart "Content Placeholder 9") are recorded
# here as ground truth. NOTE: the closest real-variable bindings do NOT reproduce
# these bases (computed: experienced 19|20|21 -> n=772; no-experience 22 -> n=229;
# professionals 21 -> n=216; recommenders 158O706 -> n=249). The deck's segment
# definitions rely on survey routing / a derived population not recoverable from
# this .sav, so the segment-split chart is intentionally NOT golden-tested.
# ---------------------------------------------------------------------------
DECK_SEGMENT_BASES: dict[str, int] = {
    "kokemusta_omaavat": 608,
    "kokemattomat": 245,
    "suosittelijat": 234,
    "ammattilaiset": 257,
}

# ---------------------------------------------------------------------------
# M-2: General opinion ("Mikä on yleinen käsityksesi...", slide idx 17).
#
# Single-select 1..4 + DK: var20 = private providers, var21 = public provider.
# Codes: 10054 Erittäin huono, 10055 Huono, 10056 Hyvä, 10057 Erittäin hyvä,
# 10058 En osaa sanoa. Positive = Hyvä + Erittäin hyvä; negative = the two huono;
# neutral = En osaa sanoa. Base = all respondents (n=1001). UNWEIGHTED.
# Chart "Content Placeholder 11", categories private/public, 5 opinion series.
# ---------------------------------------------------------------------------
OPINION_PRIVATE_VAR = "var20"
OPINION_PUBLIC_VAR = "var21"
OPINION_POSITIVE: list[float] = [10056.0, 10057.0]
OPINION_NEGATIVE: list[float] = [10054.0, 10055.0]
OPINION_NEUTRAL: list[float] = [10058.0]
# Chart series order/codes (Erittäin huono, Huono, Hyvä, Erittäin hyvä, En osaa sanoa).
OPINION_SERIES_CODES: dict[str, float] = {
    "Erittäin huono": 10054.0,
    "Huono": 10055.0,
    "Hyvä": 10056.0,
    "Erittäin hyvä": 10057.0,
    "En osaa sanoa": 10058.0,
}
# Deck ground truth (slide idx 17), positive % shown in TextBox.
DECK_OPINION_POSITIVE: dict[str, int] = {"private": 58, "public": 58}
# Deck chart series proportions (current wave), for the chart fidelity test.
DECK_OPINION_DIST: dict[str, dict[str, float]] = {
    "private": {"Erittäin huono": 0.05, "Huono": 0.26, "Hyvä": 0.47,
                "Erittäin hyvä": 0.10, "En osaa sanoa": 0.12},
    "public": {"Erittäin huono": 0.06, "Huono": 0.26, "Hyvä": 0.51,
               "Erittäin hyvä": 0.07, "En osaa sanoa": 0.10},
}

# ---------------------------------------------------------------------------
# M-3: Spontaneous awareness / top-of-mind (slide idx 13, chart "Kaavio 7").
#
# Open-list "Listaa kaikki jotka muistat": var17O35 (1st) .. var17O44 (10th).
# Any-mention = brand appears in ANY position; top-of-mind = first position.
# Patterns are case-insensitive substrings absorbing spelling variants the deck's
# manual coding collapsed (e.g. 'esper' -> Esperi/Espericare/Esperia). Base n=1001.
# Chart series: "Top of mind" (first), "Kaikki" (any mention).
# ---------------------------------------------------------------------------
SPONTANEOUS_MENTION_VARS: list[str] = [f"var17O{i}" for i in range(35, 45)]
SPONTANEOUS_FIRST_VAR = "var17O35"
SPONTANEOUS_PATTERNS: dict[str, list[str]] = {
    "Attendo": ["attendo"],
    "Esperi": ["esper"],
    "Mehiläinen": ["mehil"],
    "Pihlajalinna": ["pihlaja"],
    "Onnikodit": ["onni"],
    "Saga": ["saga"],
    "Terveystalo": ["terveystalo"],
    "Validia": ["validia"],
    "Rinnekodit": ["rinnekod", "rinnekot", "rinne koti"],
    "Mainiokodit": ["mainiok", "mainio kod", "mainio-kod"],
    "Coronaria": ["coronaria", "koronaria"],
    "Humana": ["humana"],
}
# Deck ground truth (slide idx 13, chart "Kaavio 7"): (any-mention %, top-of-mind %).
DECK_SPONTANEOUS: dict[str, tuple[int, int]] = {
    "Attendo": (37, 26),
    "Esperi": (21, 11),
    "Mehiläinen": (17, 9),
    "Pihlajalinna": (6, 2),
    "Onnikodit": (4, 1),
    "Saga": (3, 1),
    "Terveystalo": (3, 1),
    "Validia": (2, 2),
    "Rinnekodit": (2, 0),
    "Mainiokodit": (1, 0),
    "Coronaria": (1, 0),
    "Humana": (1, 0),
}

# Deck ground truth: slide idx 24 (deck slide 25), current wave "Marras 25"
# (Marraskuu 2025) TOP-10, lowercased lemmas. Raw counts from the deck shown in
# comments. "Kiire/kiireinen (66)" -> "kiire".
DECK_IMAGE_TOP10: list[str] = [
    "kallis",       # 185
    "huono",        # 75
    "kiire",        # 66  (deck: "Kiire/kiireinen")
    "luotettava",   # 61
    "hyvä",         # 60
    "ahne",         # 57
    "iso",          # 36
    "tunnettu",     # 32
    "välittävä",    # 32
    "huolehtiva",   # 27
]
