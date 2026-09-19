"""What counts as a drawn text on a figure.

One definition, shared: the overlap oracle and the legibility oracle both have
to answer "which texts are actually on this picture", and two oracles
disagreeing about that is the seam every contradiction starts from.

This is deliberately NOT `label_fit._obstacles`. That function lists what a
category name must not be printed over, so it skips the tick labels of the axis
being fitted (`if (id(ax), axis) in named: continue`) and excludes legends by
design — exactly the texts these oracles exist to judge.
"""
from __future__ import annotations


def drawn_texts(fig) -> list:
    """Every text on the figure that is really there, in drawing order.

    `ax.axison` is False after `ax.axis("off")` while the tick labels still
    report `get_visible() == True` with real text. A word cloud draws an
    `imshow`'d raster and turns its axis off (`render/image/wordcloud.py:127`),
    so a census trusting visibility alone invents obstacles nobody can see:
    mutation-checked, dropping this guard makes a single axis-off figure
    contribute **14** of them across its two tick-label sets.
    """
    out: list = []
    for ax in fig.axes:
        for artist in ax.texts:
            if artist.get_visible() and artist.get_text().strip():
                out.append(artist)
        if ax.get_title().strip():
            out.append(ax.title)
        if not ax.axison:
            continue
        # An axis can be switched off on its own while its axes stays on: a
        # twin axes (`twinx`) hides its x axis, whose tick labels still report
        # themselves visible and sit exactly on the parent's — every combo
        # "collided" with itself, name for name. (visual QA, 2026-09-19)
        for axis, labels in ((ax.xaxis, ax.get_xticklabels()),
                             (ax.yaxis, ax.get_yticklabels())):
            if not axis.get_visible():
                continue
            for artist in labels:
                if artist.get_visible() and artist.get_text().strip():
                    out.append(artist)
    for artist in fig.texts:
        if artist.get_visible() and artist.get_text().strip():
            out.append(artist)
    # Legends are text on the picture like any other. Left out, the census was
    # blind to the one collision that made a small-multiples slide unreadable:
    # four panels' legends printed through each other. (visual QA, 2026-09-19)
    legends = [ax.get_legend() for ax in fig.axes] + list(fig.legends)
    for legend in legends:
        if legend is None or not legend.get_visible():
            continue
        for artist in legend.get_texts():
            if artist.get_visible() and artist.get_text().strip():
                out.append(artist)
    return out
