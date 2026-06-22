# Build slides from WORD and OPINION data — each a DIFFERENT style

## Words data: `chart_lab/words_data.json` = {meta:{question,base "n=863",wave}, words:[{word,
count,sentiment ∈ kielteinen/myönteinen/neutraali} ×10]}. EXACT counts.
Produce:
1. **Word cloud** — the 10 words sized by count, coloured by sentiment (install the free
   `wordcloud` lib if helpful, or render with matplotlib). Clean, on-brand.
2. **Treemap** — the 10 words as nested rectangles sized by count, coloured by sentiment
   (use `squarify` + matplotlib — install it).

## Opinion data: `chart_lab/perception_idx17.json` = {"categories":["Yksityiset
palveluntarjoajat","Julkinen palveluntarjoaja"], "series":{"Erittäin huono":[priv,pub],"Huono":
[..],"Hyvä":[..],"Erittäin hyvä":[..],"En osaa sanoa":[..]}}. EXACT.
Produce:
3. **Diverging / tornado bar** — for each group, negatives extend LEFT of a centre line and
   positives extend RIGHT (En osaa sanoa shown separately or muted) — a butterfly/diverging
   layout that makes the net balance instant.

Each slide: Finnish key-message title, caption + n, nSight house style, Liberation Sans/DejaVu
(NO Arial), nothing overlapping. Output to one pptx `work/agent_var_wordsop.pptx`, reusable
script `chart_lab/agent_var_wordsop.py`. Self-check by rendering.
