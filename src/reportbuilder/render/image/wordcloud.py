"""Image-mode word-cloud builder — nSight house style (Task J.2).

Builder: ``build_image_wordcloud``.

Renders the most-frequent answer words larger using the ``wordcloud`` library.
Word frequencies come from the SeriesResult built by ``stats.engine._wordcloud``
(categories = words, each cell's ``count`` = the word frequency).

House style:
- TRANSPARENT: the slide's own background shows through, like every other chart.
- Word colours ramped from the TEMPLATE's accent — darkest for the most frequent
  word, lighter tints down the tail (``color_func`` keyed on frequency rank).
  House teal is what a template that states no colour produces, not a fixed
  decision imposed on one that does.
- A usable TTF font: the registered house font (Liberation Sans) when locatable,
  else matplotlib's bundled DejaVuSans.ttf.
- ``random_state=42`` so the layout is deterministic across runs.
- No matplotlib axes/title (the slide chrome adds the title + n footer, REQ-D-04).

The cloud is drawn onto a matplotlib figure sized to the slot (reusing ``_mpl``)
then placed via the standard image placement so it composes under the slide
chrome like any other chart. Returns None.
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager as _fm  # noqa: E402

from wordcloud import WordCloud  # noqa: E402

from reportbuilder.render.image._mpl import (
    new_figure, place_picture, render_png, chart_accent,
)
from reportbuilder.render.house_style import (
    register_fonts, ramp_from, _LIBERATION_PATHS,
)

#: How many tints the cloud ramps through, darkest (most frequent) to lightest.
_CLOUD_STEPS = 6


def _cloud_ramp(accent: str) -> list[str]:
    """Darkest → lightest tints of the deck's own colour.

    `ramp_from` is the same construction every other chart's series ramp uses —
    the accent blended toward white — so a word cloud belongs to the same deck
    as the bars beside it. It runs light→dark, and prominence reads the other
    way round here: the most frequent word wants the strongest colour.
    """
    return list(reversed(ramp_from(accent, steps=_CLOUD_STEPS)))


def _resolve_font_path() -> str:
    """Return a usable TTF path: the house font if locatable, else DejaVuSans.

    ``wordcloud`` needs a concrete font file path (it does not use matplotlib's
    rcParams), so resolve the registered house font first and fall back to
    matplotlib's bundled DejaVu Sans, which is always present.
    """
    for fp in _LIBERATION_PATHS:
        if os.path.exists(fp):
            return fp
    return _fm.findfont("DejaVu Sans")


def build_image_wordcloud(ctx) -> None:
    """Render a frequency word cloud for a free-text question (Task J.2).

    Reads ``{word: count}`` frequencies from ``ctx.series`` (categories + count
    cells), builds a deterministic ``WordCloud`` in house style, and places it on
    the slide. Raises ``ValueError`` when there are no words to render.
    """
    register_fonts()
    cats = list(ctx.series.categories)
    freqs: dict[str, float] = {}
    for c in cats:
        cnt = ctx.series.cell(c, "Total").count
        if cnt and float(cnt) > 0:
            freqs[c] = float(cnt)

    if not freqs:
        raise ValueError("No words to render in word cloud")

    # Rank words by frequency (desc) so colour intensity tracks prominence.
    ranked = sorted(freqs, key=lambda w: (-freqs[w], w))
    rank = {w: i for i, w in enumerate(ranked)}
    n = len(ranked)

    ramp = _cloud_ramp(chart_accent(ctx))

    def _color_func(word, *args, **kwargs):  # noqa: ANN001
        r = rank.get(word, 0)
        idx = 0 if n <= 1 else int(round(r / (n - 1) * (len(ramp) - 1)))
        return ramp[idx]

    # Pixel canvas matched to the slot aspect ratio so words fill the slot without
    # being stretched when placed.
    aspect = (ctx.slot.width / ctx.slot.height) if ctx.slot.height else 1.6
    width_px = 1600
    height_px = max(400, int(round(width_px / aspect)))

    # No background at all. `render_png` saves with transparent=True, but that
    # blanks the matplotlib figure/axes patches and NOT an imshow'd array — so a
    # colour painted here would survive as a rectangle under every word,
    # whatever the slide beneath it looks like. RGBA + background_color=None is
    # what makes `to_array` carry an alpha channel for the gaps to be gaps.
    wc = WordCloud(
        mode="RGBA",
        background_color=None,
        color_func=_color_func,
        font_path=_resolve_font_path(),
        random_state=42,            # deterministic layout
        prefer_horizontal=0.9,
        max_words=len(freqs),
        width=width_px,
        height=height_px,
        margin=4,
        relative_scaling=0.5,       # size tracks frequency strongly
    )
    wc.generate_from_frequencies(freqs)

    fig, ax = new_figure(ctx)
    ax.imshow(wc.to_array(), interpolation="bilinear")
    ax.axis("off")
    for spine in ax.spines.values():
        spine.set_visible(False)

    png = render_png(fig)
    place_picture(ctx, png)
