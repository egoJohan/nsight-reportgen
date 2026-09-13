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
        for labels in (ax.get_xticklabels(), ax.get_yticklabels()):
            for artist in labels:
                if artist.get_visible() and artist.get_text().strip():
                    out.append(artist)
    for artist in fig.texts:
        if artist.get_visible() and artist.get_text().strip():
            out.append(artist)
    return out
