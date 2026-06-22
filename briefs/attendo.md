# Attendo Bränditutkimus — slide brief

One ```slide block per deck job. Numbers are computed deterministically from the
survey data; the narrator only writes prose key messages.

## Aided awareness (autettu tunnettuus)

```slide
id: aided_awareness
slide_idx: 14
metric: aided_awareness
segment: kaikki
title: Autettu tunnettuus
chart:
  name: Content Placeholder 9
  series_name: Marraskuu 2025
key_message:
  name: Text Placeholder 5
```

## General opinion (yleinen käsitys) — private vs public

```slide
id: general_opinion
slide_idx: 17
metric: general_opinion
segment: kaikki
title: Yleinen käsitys
chart:
  name: Content Placeholder 11
  private_category: Yksityiset palveluntarjoajat
  public_category: Julkinen palveluntarjoaja
```

## Spontaneous awareness (spontaani tunnettuus)

```slide
id: spontaneous_awareness
slide_idx: 13
metric: spontaneous_awareness
segment: kaikki
title: Spontaani tunnettuus
chart:
  name: Kaavio 7
  tom_series: Top of mind
  any_series: Kaikki
```

## Brand-image spontaneous words (mielikuva, TOP 10)

Current wave (Marras 25) word list on deck slide 25 (slide_idx 24). The deck holds
each wave in its own rounded-rectangle text box; the current wave is
"Rectangle: Rounded Corners 7" with a 3-paragraph header (TOP 10 / Marras 25 /
blank) followed by 10 "Word (count)" paragraphs (start=3).

```slide
id: image_words
slide_idx: 24
metric: image_words
segment: kaikki
title: Mielikuva Attendosta (TOP 10)
words:
  name: 'Rectangle: Rounded Corners 7'
  start: 3
  top_n: 10
```

<!--
M-1 (aided awareness by segment, slide_idx 15, chart "Content Placeholder 9",
occurrence 0, series per segment) is NOT included: the deck's segment bases
(experience 608 / no-experience 245 / recommenders 234 / professionals 257) and
per-segment values cannot be reproduced from this .sav with any available
variable definition. See attendo_bindings.DECK_SEGMENT_BASES and segments.py.
-->
