from __future__ import annotations

import copy


def set_text(shape, value: str) -> None:
    """Replace a text box's content with `value`, preserving the first run's font."""
    if not shape.has_text_frame:
        raise ValueError(f"shape {shape.name!r} has no text frame")
    tf = shape.text_frame
    para = tf.paragraphs[0]
    if para.runs:
        para.runs[0].text = value
        for extra in para.runs[1:]:
            extra.text = ""
    else:
        para.text = value
    for p in list(tf.paragraphs[1:]):
        p._p.getparent().remove(p._p)


def set_lines(shape, lines: list[str], *, start: int = 0) -> None:
    """Write one paragraph per line, replacing paragraphs from index `start` onward.

    Paragraphs before `start` (e.g. a "TOP 10" header) are preserved untouched. The
    paragraph currently at `start` is used as the formatting template: its paragraph
    properties (`<a:pPr>`, e.g. centered alignment) and the first run's properties
    (`<a:rPr>`, e.g. font size) are cloned onto every emitted line so the rendered
    list looks identical to the deck's original word list.
    """
    if not shape.has_text_frame:
        raise ValueError(f"shape {shape.name!r} has no text frame")
    tf = shape.text_frame
    paras = list(tf.paragraphs)
    if start >= len(paras):
        raise IndexError(
            f"start={start} but shape {shape.name!r} only has {len(paras)} paragraphs"
        )

    template_p = paras[start]
    # Snapshot the formatting XML from the template paragraph before we delete it.
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    p_pr = template_p._p.find(f"{ns}pPr")
    pr_template = copy.deepcopy(p_pr) if p_pr is not None else None
    first_run = template_p.runs[0] if template_p.runs else None
    r_pr = None
    if first_run is not None:
        r_pr_el = first_run._r.find(f"{ns}rPr")
        r_pr = copy.deepcopy(r_pr_el) if r_pr_el is not None else None

    # Remove all paragraphs from `start` onward.
    for p in paras[start:]:
        p._p.getparent().remove(p._p)

    for line in lines:
        new_p = tf.add_paragraph()
        if pr_template is not None:
            new_p._p.insert(0, copy.deepcopy(pr_template))
        run = new_p.add_run()
        if r_pr is not None:
            # Replace the auto-created rPr with the cloned formatting.
            existing = run._r.find(f"{ns}rPr")
            if existing is not None:
                run._r.remove(existing)
            run._r.insert(0, copy.deepcopy(r_pr))
        run.text = line
