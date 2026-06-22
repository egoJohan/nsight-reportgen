from __future__ import annotations


def fill_table(shape, cells: dict[tuple[int, int], str]) -> None:
    """Write text into specific (row, col) cells of a table, preserving formatting.

    Sets the text of the cell's first run when present (keeps font), else paragraph text.
    """
    if not shape.has_table:
        raise ValueError(f"shape {shape.name!r} is not a table")
    table = shape.table
    for (r, c), value in cells.items():
        cell = table.cell(r, c)
        para = cell.text_frame.paragraphs[0]
        if para.runs:
            para.runs[0].text = value
            for extra in para.runs[1:]:
                extra.text = ""
        else:
            para.text = value
