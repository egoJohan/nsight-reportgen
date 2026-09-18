"""A themes slide must not run off the bottom of the slide.

Taffel, "Edullisempi hinta ja uudet maut houkuttelisivat ostamaan Taffelia
useammin" — five themes, each a bold lead-in plus two or three lines of body.
The bullet box is a fixed height and the per-level sizes are fixed (16/14/13),
with nothing measuring whether the text fits, so the fifth theme was cut off
mid-sentence at the slide edge and the footer was pushed off the slide
entirely. Nothing said so: the author sees a slide that looks finished.

The title has had a measured fitter since the template work (`fit_title_size`);
the bullets never got one.
"""
from __future__ import annotations

from pptx.util import Inches

from reportbuilder.render.image.special_slide import (
    _LEVEL_PT, bullets_height, fit_bullet_scale,
)

#: The real slide's five themes, verbatim.
_REAL = [
    (0, "**Edullisempi hinta ja tarjoukset** – mainittu noin 45 %:ssa vastauksista, "
        "mikä tekee tästä selkeästi suurimman tekijän ostofrekvenssin kasvattamiseen "
        "(esim. halvempi hinta, alennukset, kampanjat ja parempi hinta-laatusuhde)."),
    (0, "**Uudet maut ja tuotekehitys** – mainittu noin 25 %:ssa vastauksista, joissa "
        "toivotaan uusia makuyhdistelmiä, tulisuutta, uutuustuotteita sekä vanhojen "
        "suosikkien (kuten tillisipsien) palauttamista valikoimaan."),
    (0, "**Tyytyväisyys nykytilaan ja brändiuskollisuus** – mainittu noin 15 %:ssa "
        "vastauksista, joissa korostuu Taffelin asema tuttuna, turvallisena ja "
        "laadukkaana brändinä, jonka tuotteita ostetaan jo nyt riittävästi ilman "
        "muutostarpeita."),
    (0, "**Terveellisemmät vaihtoehdot** – mainittu noin 10 %:ssa vastauksista, joissa "
        "ostamista lisäisi vähäsuolaisuus, terveellisemmät raaka-aineet, vegaanisuus "
        "tai soveltuvuus arkisemmaksi välipalaksi."),
    (0, "**Ei ostohalukkuutta tai muutostarvetta** – mainittu noin 10 %:ssa "
        "vastauksista, joissa vastaajat kokevat sipsit vain harvoin nautittaviksi "
        "herkuiksi, eivätkä koe tarvetta ostaa niitä nykyistä useammin."),
]

#: The box the real 10 x 5.62in slide gives them: 0.85in margins, heading above,
#: footer below.
_W = int(Inches(10) - Inches(1.6))
_H = int(Inches(5.62) - Inches(1.55) - Inches(0.55))

_SHORT = [(0, "Hinta"), (0, "Maku"), (0, "Pakkaus")]


def test_a_short_list_is_left_at_its_own_size():
    assert fit_bullet_scale(_SHORT, _W, _H, "Liberation Sans") == 1.0


def test_the_real_five_themes_do_not_fit_at_full_size():
    """The premise: without this, the slide overflows — which is what shipped."""
    assert bullets_height(_REAL, _W, "Liberation Sans", 1.0) > _H


def test_the_real_five_themes_fit_once_scaled():
    scale = fit_bullet_scale(_REAL, _W, _H, "Liberation Sans")
    assert scale < 1.0
    assert bullets_height(_REAL, _W, "Liberation Sans", scale) <= _H


def test_the_text_never_shrinks_past_legibility():
    """A slide with far too much on it stops at the floor rather than becoming
    unreadable — the author is better served by visible overflow than by 4pt."""
    huge = [(0, "Pitkä teema. " * 60)] * 12
    scale = fit_bullet_scale(huge, _W, _H, "Liberation Sans")
    assert scale * _LEVEL_PT[0] >= 9.0
