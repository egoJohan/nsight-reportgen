"""Two reported slides, as the engine hands them to the renderer — from the
customer's own data (Suomalainen Työ, Q3-2026-AllCountries; staging, read-only,
2026-09-11). Kept here so the tests that guard them read the same numbers.

- `battery_by_country()`: "Olen luottavainen, että saan työstä riittävän suuren
  toimeentulon…" — six statements, each split by country, 18 bars. The bars
  were printed as "<statement> · <country>", eighteen names that did not fit,
  so every one was cut to its first words and the country was lost.
- `sector_by_country()`: "Miten arvioit työn merkityksen kehittyvän…" — country
  crossed with sector, 18 bars. Small "2 %" numbers called out above their bars
  were printed over the numbers inside the bar above.
"""
from __future__ import annotations

from reportbuilder.stats.series import Cell, SeriesResult

_AGREE = ("1 - Täysin eri mieltä", "2", "3", "4", "5", "6", "7 - Täysin samaa mieltä")
_COUNTRIES = ("Suomi", "Ruotsi", "Saksa")

#: (statement, [(base, [pct per level]) per country])
_BATTERY = [
    ("Olen luottavainen, että saan työstä riittävän suuren toimeentulon", [
        (1016, [6, 6, 10, 17, 23, 20, 18]), (1015, [5, 5, 7, 14, 24, 22, 23]),
        (1011, [7, 4, 8, 17, 23, 23, 18])]),
    ("Teen nykyisin sivutöitä ansaitakseni enemmän", [
        (1009, [31, 11, 7, 10, 14, 12, 15]), (1009, [25, 7, 8, 12, 16, 14, 18]),
        (1012, [40, 7, 6, 12, 12, 10, 13])]),
    ("Teen nykyisin sivutöitä oppiakseni uutta / parantaakseni elämänlaatua", [
        (997, [33, 11, 8, 12, 13, 12, 11]), (1008, [26, 10, 9, 16, 15, 12, 12]),
        (1014, [40, 8, 5, 12, 13, 13, 9])]),
    ("Uskon, että yhä useampi saa tulevaisuudessa toimeentulonsa monesta eri "
     "tulonlähteestä", [
        (983, [2, 3, 7, 17, 26, 23, 22]), (970, [3, 4, 8, 19, 26, 21, 19]),
        (1012, [4, 3, 9, 17, 25, 21, 21])]),
    ("Luulen, että tulevaisuuden työelämässä tehdään nykyistä enemmän "
     "yrittäjämäistä työtä ja vähemmän perinteistä palkkatyötä  "
     "(Yrittäjämäisellä työllä tarkoitamme työtä, jossa työntekijä itse vastaa "
     "työnantajan velvollisuuksista", [
        (960, [3, 5, 12, 24, 25, 18, 13]), (922, [5, 5, 12, 25, 26, 15, 12]),
        (964, [4, 5, 12, 30, 24, 14, 11])]),
    ("Pidän yrittäjyyttä henkilökohtaisesti mielenkiintoisena vaihtoehtona", [
        (1015, [17, 10, 9, 12, 16, 16, 20]), (981, [9, 6, 9, 15, 23, 19, 19]),
        (979, [6, 5, 10, 20, 24, 18, 17])]),
]

STATEMENTS = tuple(s for s, _rows in _BATTERY)


def battery_by_country() -> SeriesResult:
    """As `_battery_stacked` returns it once split by a group: bars
    "<statement> · <country>", grouped by statement."""
    cells, base, primary, bars = {}, {"Total": 3076}, {}, []
    for stmt, rows in _BATTERY:
        for country, (n, pcts) in zip(_COUNTRIES, rows):
            bar = f"{stmt} · {country}"
            bars.append(bar)
            base[bar] = n
            primary[bar] = stmt
            for lvl, p in zip(_AGREE, pcts):
                cells[(lvl, bar)] = Cell(pct=float(p), count=round(n * p / 100.0), mean=None)
    return SeriesResult(categories=_AGREE, segments=tuple(bars), cells=cells, base_n=base,
                        statistic="pct", segment_primary=primary)


_MEANING = ("1 - Siitä tulee todella paljon vähemmän merkityksellistä", "2", "3", "4", "5",
            "6", "7 - Siitä tulee todella paljon enemmän merkityksellistä")
_SECTORS = ("yksityisellä sektorilla", "valtion palveluksessa", "kunnan palveluksessa",
            "hyvinvointialueen palveluksessa", "järjestön palveluksessa", "muualla")
#: country -> [(base, [pct per level]) per sector]
_SECTOR = {
    "Suomi": [(535, [3, 4, 8, 28, 23, 20, 14]), (84, [4, 2, 7, 21, 19, 30, 17]),
              (145, [2, 3, 7, 29, 31, 14, 14]), (97, [3, 3, 9, 19, 32, 20, 14]),
              (36, [3, 3, 5, 25, 19, 28, 17]), (59, [7, 10, 5, 17, 24, 24, 13])],
    "Ruotsi": [(396, [4, 2, 7, 23, 25, 20, 19]), (135, [2, 2, 4, 21, 25, 21, 25]),
               (267, [3, 3, 6, 19, 30, 21, 18]), (55, [2, 0, 5, 20, 27, 22, 24]),
               (67, [0, 2, 13, 15, 33, 16, 21]), (40, [8, 0, 7, 12, 20, 25, 28])],
    "Saksa": [(554, [3, 3, 5, 20, 27, 27, 15]), (85, [5, 1, 6, 16, 32, 21, 19]),
              (69, [6, 3, 7, 23, 25, 23, 13]), (149, [2, 3, 5, 13, 22, 38, 17]),
              (46, [0, 4, 15, 11, 30, 20, 20]), (95, [5, 2, 11, 12, 24, 29, 17])],
}


def sector_by_country() -> SeriesResult:
    """Country crossed with sector, grouped by country — "Total column" off, as saved."""
    cells, base, primary, bars = {}, {"Total": 2914}, {}, []
    for country, rows in _SECTOR.items():
        for sector, (n, pcts) in zip(_SECTORS, rows):
            bar = f"{country} · {sector}"
            bars.append(bar)
            base[bar] = n
            primary[bar] = country
            for lvl, p in zip(_MEANING, pcts):
                cells[(lvl, bar)] = Cell(pct=float(p), count=round(n * p / 100.0), mean=None)
    return SeriesResult(categories=_MEANING, segments=tuple(bars), cells=cells, base_n=base,
                        statistic="pct", segment_primary=primary, show_total=False)
