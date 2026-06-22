"""Non-technical flowchart (Finnish): kuvauksesta valmiiseen PowerPointiin.
Renders an nSight-themed flow diagram to PNG + SVG. No jargon, for a non-technical reader.
"""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Wedge

THEME = json.loads(Path("theme_nsight.json").read_text())
BG = THEME["background"]
ACCENT = THEME["accent"]
ACCENT_DARK = THEME["accent_dark"]
INK = THEME["ink"]
MUTED = THEME["muted"]
FONT = THEME["font"]
plt.rcParams["font.family"] = FONT

# Steps: (number, title, subtitle, needs_human)
STEPS = [
    ("1", "Kuvaus",
     "Kerrot omin sanoin, millainen esitys halutaan, mihin tutkimukseen se perustuu ja\n"
     "mitkä ovat tärkeimmät teemat. Tämä on ainoa vaihe, jossa annat lähtötiedot.",
     True),
    ("2", "Tiedon haku",
     "Järjestelmä hakee oikeat tutkimustulokset tietovarastosta itse. Oikeat kysymykset\n"
     "ja vastaajaryhmät poimitaan automaattisesti, ilman käsityötä.",
     False),
    ("3", "Kaavioiden valinta",
     "Jokaiselle dialle valitaan sopivin kaaviotyyppi sen mukaan, millaista tietoa esitetään\n"
     "– esimerkiksi vertailu, kehitys ajassa tai vastausten jakauma.",
     False),
    ("4", "Kaavioiden piirto",
     "Kaaviot piirretään täsmälleen tutkimuksen luvuilla. Luvut tulevat aina suoraan datasta\n"
     "– niitä ei koskaan keksitä eikä muuteta käsin.",
     False),
    ("5", "Diojen kokoaminen",
     "Jokaiseen diaan kootaan pääviesti, kaavio, taustakysymys ja vastaajamäärä – kaikki\n"
     "yhtenäisellä nSightin ilmeellä.",
     False),
    ("6", "Laaduntarkistus",
     "Ihminen katsoo lopputuloksen. Tässä vaiheessa saat keskustelemalla kertoa, mitä pitää\n"
     "muuttaa. Muutokset tehdään ja vaihe toistetaan, kunnes laatu on hyväksytty.",
     True),
    ("7", "Valmis PowerPoint",
     "Hyväksytyt diat yhdistetään yhdeksi viimeistellyksi esitykseksi, joka on valmis\n"
     "toimitettavaksi asiakkaalle.",
     False),
]
HUMAN = "#E29B2E"  # warm accent marks the steps that need a person


def draw_person(cx, cy, scale, color, z=6):
    """Tiny person silhouette: head + shoulders."""
    ax.add_patch(Circle((cx, cy + 0.085 * scale), 0.072 * scale,
                         color=color, zorder=z))
    ax.add_patch(Wedge((cx, cy - 0.055 * scale), 0.14 * scale, 0, 180,
                       color=color, zorder=z))

N = len(STEPS)
# Box geometry first, so the canvas can be sized to fit exactly (no clipping).
box_left = 1.45
box_w = 9.4
box_h = 1.5
gap = 0.5
title_space = 1.35   # just the legend up top; no main heading
bottom_margin = 0.5
content_h = title_space + N * box_h + (N - 1) * gap + bottom_margin

canvas_w = 12.6  # extra room on the right for the loop-back arrow
fig_w = 11.6
fig_h = fig_w * content_h / canvas_w
fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, canvas_w)
ax.set_ylim(0, content_h)
ax.axis("off")

TOP = content_h

# Legend: the human marker (no main heading)
leg_y = TOP - 0.6
draw_person(box_left + 0.2, leg_y, 1.7, HUMAN)
ax.text(box_left + 0.6, leg_y, "= vaihe, jossa tarvitaan ihmistä",
        fontsize=12.5, color=INK, ha="left", va="center")

# Box placement
first_top = TOP - title_space
num_cx = 1.15   # centre x of the number badge column

box_centers = []  # (cx, cy) of each box for arrow routing
y = first_top
for i, (num, title, sub, needs_human) in enumerate(STEPS):
    box_top = y
    box_bottom = box_top - box_h
    cy = (box_top + box_bottom) / 2
    box_centers.append((box_left + box_w / 2, cy, box_top, box_bottom))

    # last box highlighted (filled accent)
    is_last = (i == N - 1)
    face = ACCENT_DARK if is_last else "#FFFFFF"
    edge = HUMAN if needs_human else (ACCENT_DARK if is_last else ACCENT)
    lw = 3.0 if needs_human else 1.8
    title_col = "#FFFFFF" if is_last else ACCENT_DARK
    sub_col = "#E8EEEC" if is_last else INK

    box = FancyBboxPatch((box_left, box_bottom), box_w, box_h,
                         boxstyle="round,pad=0.02,rounding_size=0.18",
                         linewidth=lw, edgecolor=edge, facecolor=face, zorder=3)
    ax.add_patch(box)

    # number badge — warm colour when a person is needed
    badge_col = HUMAN if needs_human else ACCENT
    badge = Circle((num_cx, cy), 0.42, color=badge_col, zorder=4)
    ax.add_patch(badge)
    ax.text(num_cx, cy, num, fontsize=18, fontweight="bold", color="#FFFFFF",
            ha="center", va="center", zorder=5)

    # title row
    ax.text(box_left + 0.45, box_top - 0.42, title, fontsize=16.5,
            fontweight="bold", color=title_col, ha="left", va="center", zorder=5)

    # "Tarvitaan ihmistä" pill on the title row, right side
    if needs_human:
        pill_w, pill_h = 2.55, 0.52
        pill_x = box_left + box_w - pill_w - 0.3
        pill_y = box_top - 0.42
        pill = FancyBboxPatch((pill_x, pill_y - pill_h / 2), pill_w, pill_h,
                              boxstyle="round,pad=0.01,rounding_size=0.26",
                              linewidth=0, facecolor=HUMAN, zorder=5)
        ax.add_patch(pill)
        draw_person(pill_x + 0.34, pill_y, 1.5, "#FFFFFF", z=6)
        ax.text(pill_x + 0.62, pill_y, "Tarvitaan ihmistä", fontsize=11,
                fontweight="bold", color="#FFFFFF", ha="left", va="center", zorder=6)

    ax.text(box_left + 0.45, box_top - 0.92, sub, fontsize=11.5,
            color=sub_col, ha="left", va="top", zorder=5, linespacing=1.4)

    y = box_bottom - gap

# Down arrows between boxes
for i in range(N - 1):
    _, _, _, bottom = box_centers[i]
    _, _, top_next, _ = box_centers[i + 1]
    cx = box_left + box_w / 2
    arr = FancyArrowPatch((cx, bottom), (cx, top_next),
                          arrowstyle="-|>", mutation_scale=22,
                          linewidth=2.2, color=ACCENT, zorder=2)
    ax.add_patch(arr)

# Loop-back arrow: step 6 -> step 4 (korjaus, toistetaan), routed outside on the right
loop_col = THEME["palette"][1]
_, _, top6, bot6 = box_centers[5]
_, _, top4, bot4 = box_centers[3]
right_x = box_left + box_w
loop_x = right_x + 0.7
mid6 = (top6 + bot6) / 2 + 0.25
mid4 = (top4 + bot4) / 2 + 0.25
dash = (0, (5, 3))
# out from box 6, up the side, back into box 4 (arrowhead)
ax.plot([right_x, loop_x], [mid6, mid6], color=loop_col, lw=2.0, ls=dash, zorder=2)
ax.plot([loop_x, loop_x], [mid6, mid4], color=loop_col, lw=2.0, ls=dash, zorder=2)
back = FancyArrowPatch((loop_x, mid4), (right_x, mid4),
                       arrowstyle="-|>", mutation_scale=20,
                       linewidth=2.0, linestyle=dash, color=loop_col, zorder=2)
ax.add_patch(back)
ax.text(loop_x + 0.12, (mid6 + mid4) / 2, "korjaa\nja toista",
        fontsize=10.5, color=loop_col, ha="left", va="center",
        fontstyle="italic", linespacing=1.3)

plt.tight_layout()
out_dir = Path("../work")
out_dir.mkdir(exist_ok=True)
# Cream-background versions
fig.savefig(out_dir / "esityksen_synty_flow.png", facecolor=BG,
            bbox_inches="tight", pad_inches=0.25)
fig.savefig(out_dir / "esityksen_synty_flow.svg", facecolor=BG,
            bbox_inches="tight", pad_inches=0.25)
# Transparent-background PNG
fig.savefig(out_dir / "esityksen_synty_flow_transparent.png", transparent=True,
            bbox_inches="tight", pad_inches=0.25)
for f in ["esityksen_synty_flow.png", "esityksen_synty_flow.svg",
          "esityksen_synty_flow_transparent.png"]:
    print("wrote", (out_dir / f).resolve())
