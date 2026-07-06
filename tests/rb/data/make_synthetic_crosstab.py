"""Generate a small, fully-synthetic .sav for cross-tab percentage-direction tests.

No real company/brand names or client data — invented respondents only. Structure
mirrors the customer's gender × psychographic-segment case (report UusiRaportti /
Klusteri): a demographic (gender), an analyst-derived 7-way segment, an age
bracket demographic, and a 1–7 opinion scale with a 99 "En osaa sanoa" code.

Run: python tests/rb/data/make_synthetic_crosstab.py  → writes synthetic_crosstab.sav
"""
from __future__ import annotations
import pathlib
import numpy as np
import pandas as pd
import pyreadstat

OUT = pathlib.Path(__file__).parent / "sav" / "synthetic_crosstab.sav"


def build() -> tuple[pd.DataFrame, dict, dict, dict]:
    rng = np.random.default_rng(42)  # deterministic
    n = 1000
    # Gender ~ balanced, tiny "Muu". 1=Mies, 2=Nainen, 3=Muu
    gender = rng.choice([1, 2, 3], size=n, p=[0.49, 0.50, 0.01])
    # Age bracket demographic. 1..4
    age = rng.choice([1, 2, 3, 4], size=n, p=[0.28, 0.30, 0.26, 0.16])
    # Segment 1..7, correlated with gender so the two %-directions tell DIFFERENT
    # stories (segment 4 skews female, segment 3 skews male).
    seg = np.empty(n, dtype=int)
    base = np.array([0.13, 0.14, 0.14, 0.27, 0.10, 0.09, 0.12])
    for i in range(n):
        p = base.copy()
        if gender[i] == 1:      # Mies → more segment 3
            p = p * np.array([1.1, 1.0, 1.5, 0.8, 1.0, 0.9, 0.9])
        elif gender[i] == 2:    # Nainen → more segment 4
            p = p * np.array([0.9, 1.0, 0.6, 1.2, 1.0, 1.1, 1.1])
        p = p / p.sum()
        seg[i] = rng.choice(np.arange(1, 8), p=p)
    # 1–7 opinion scale with a 99 "En osaa sanoa"
    op = rng.choice([1, 2, 3, 4, 5, 6, 7, 99], size=n,
                    p=[0.05, 0.08, 0.12, 0.20, 0.22, 0.18, 0.12, 0.03])

    df = pd.DataFrame({
        "sukupuoli": gender, "ikaryhma": age, "segmentti": seg, "vaittama1": op,
    })
    col_labels = {
        "sukupuoli": "Sukupuoli",
        "ikaryhma": "Ikäryhmä",
        "segmentti": "Segmentti (arvoklusteri)",
        "vaittama1": "Työ on minulle tärkeää",
    }
    value_labels = {
        "sukupuoli": {1: "Mies", 2: "Nainen", 3: "Muu"},
        "ikaryhma": {1: "18–29", 2: "30–44", 3: "45–59", 4: "60+"},
        "segmentti": {
            1: "Aktiiviset kokeilijat", 2: "Turvallisuushakuiset",
            3: "Perinteiset vastuulliset", 4: "Muutosmyönteiset",
            5: "Vetäytyneet", 6: "Yhteisölliset", 7: "Itsenäiset suorittajat",
        },
        "vaittama1": {
            1: "1 - Täysin eri mieltä", 7: "7 - Täysin samaa mieltä",
            99: "En osaa sanoa",
        },
    }
    # Declare 99 as user-missing on the opinion item (like the real data's EOS).
    missing_ranges = {"vaittama1": [{"lo": 99, "hi": 99}]}
    return df, col_labels, value_labels, missing_ranges


def main() -> None:
    df, col_labels, value_labels, missing_ranges = build()
    pyreadstat.write_sav(
        df, str(OUT),
        column_labels=col_labels,
        variable_value_labels=value_labels,
        missing_ranges=missing_ranges,
    )
    print(f"wrote {OUT}  ({len(df)} rows)")


if __name__ == "__main__":
    main()
