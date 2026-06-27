"""Image-mode word-cloud builder — nSight house style (Task J.2).

Builder: ``build_image_wordcloud``.

Renders the most-frequent answer words larger using the ``wordcloud`` library.
Word frequencies come from the SeriesResult built by ``stats.engine._wordcloud``
(categories = words, each cell's ``count`` = the word frequency).

House style:
- Cream figure + cloud background (CREAM).
- Teal-ramp word colours: the most frequent words render in the darkest teal,
  rarer words in lighter tints (``color_func`` keyed on each word's frequency rank).
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

from reportbuilder.render.image._mpl import new_figure, place_picture, render_png
from reportbuilder.render.house_style import register_fonts, CREAM, _LIBERATION_PATHS

# Teal ramp ordered darkest → lightest. The top-frequency word gets the darkest
# (most prominent) teal; the long tail fades to lighter tints.
_TEAL_CLOUD: list[str] = [
    "#13615E",   # darkest — highest frequency
    "#235F5B",
    "#3E938C",
    "#5E9C9A",
    "#7DB8A6",
    "#9CC6C4",
]


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

    def _color_func(word, *args, **kwargs):  # noqa: ANN001
        r = rank.get(word, 0)
        idx = 0 if n <= 1 else int(round(r / (n - 1) * (len(_TEAL_CLOUD) - 1)))
        return _TEAL_CLOUD[idx]

    # Pixel canvas matched to the slot aspect ratio so words fill the slot without
    # being stretched when placed.
    aspect = (ctx.slot.width / ctx.slot.height) if ctx.slot.height else 1.6
    width_px = 1600
    height_px = max(400, int(round(width_px / aspect)))

    wc = WordCloud(
        background_color=CREAM,
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
