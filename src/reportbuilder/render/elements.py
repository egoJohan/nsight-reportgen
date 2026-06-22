"""Chart element profile: apply title/axes/legend/data-labels and N/filter annotations.

REQ-C-24a..i, C-25 (Task 5.3).
"""
from __future__ import annotations

from pptx.util import Inches, Pt
from pptx.enum.chart import XL_LABEL_POSITION, XL_LEGEND_POSITION

from reportbuilder.model.report import NumberFormat
from reportbuilder.render.base import RenderContext


# ---------------------------------------------------------------------------
# Number format
# ---------------------------------------------------------------------------

def number_format_code(fmt: NumberFormat, statistic: str) -> str:
    """Return an Excel-style number format string for use in pptx data labels."""
    if statistic == "pct":
        return "0" + ("." + "0" * fmt.pct_decimals if fmt.pct_decimals else "") + '"%"'
    if statistic == "mean":
        return "0" + ("." + "0" * fmt.mean_decimals if fmt.mean_decimals else "")
    return "0"


# ---------------------------------------------------------------------------
# Element application
# ---------------------------------------------------------------------------

def apply_elements(chart, ctx: RenderContext, title: str = "") -> None:
    """Apply chart element profile (title, data labels, legend, axis names) to *chart*.

    Each element is gated by the corresponding flag in ctx.spec.elements.
    Chart-type-specific failures (e.g. pie lacks value_axis) are silently skipped.
    """
    elements = ctx.spec.elements

    # --- Title ---
    if elements.title:
        chart.has_title = True
        tf = chart.chart_title.text_frame
        tf.text = title
        font_name, font_size = ctx.style.font_for("title")
        run = tf.paragraphs[0].runs[0]
        run.font.name = font_name
        run.font.size = Pt(font_size)

    # --- Data labels ---
    if elements.data_labels:
        plot = chart.plots[0]
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.number_format = number_format_code(ctx.fmt, ctx.spec.statistic)
        dl.number_format_is_linked = False
        try:
            dl.position = XL_LABEL_POSITION.OUTSIDE_END
        except (ValueError, AttributeError):
            pass
        font_name, font_size = ctx.style.font_for("data_labels")
        dl.font.name = font_name
        dl.font.size = Pt(font_size)

    # --- Legend ---
    if elements.legend:
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        font_name, font_size = ctx.style.font_for("legend")
        chart.legend.font.name = font_name
        chart.legend.font.size = Pt(font_size)

    # --- Axis names / tick labels ---
    if elements.axis_names:
        try:
            va = chart.value_axis
            va.has_title = True
            # Leave axis_title text empty (per spec)
            vfont_name, vfont_size = ctx.style.font_for("axis_values")
            va.tick_labels.font.name = vfont_name
            va.tick_labels.font.size = Pt(vfont_size)

            cfont_name, cfont_size = ctx.style.font_for("category_names")
            chart.category_axis.tick_labels.font.name = cfont_name
            chart.category_axis.tick_labels.font.size = Pt(cfont_size)
        except AttributeError:
            pass


# ---------------------------------------------------------------------------
# Annotation helpers
# ---------------------------------------------------------------------------

def add_n_annotation(ctx: RenderContext) -> None:
    """Add a slide textbox near the slot bottom showing N=<Total>.

    Only added when ctx.spec.elements.n is True.
    """
    if not ctx.spec.elements.n:
        return

    slot = ctx.slot
    # Position: horizontally aligned to slot left, vertically just below slot bottom
    left = slot.left
    top = slot.top + slot.height - int(Inches(0.35))
    width = int(Inches(2.0))
    height = int(Inches(0.3))

    txBox = ctx.slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    base_n = ctx.series.base_n["Total"]
    tf.text = f"N={base_n}"

    font_name, font_size = ctx.style.font_for("n_annotation")
    run = tf.paragraphs[0].runs[0]
    run.font.name = font_name
    run.font.size = Pt(font_size)


def add_filter_annotation(ctx: RenderContext) -> None:
    """Add a slide textbox naming the classifying variable.

    Only added when ctx.spec.elements.filter_var is True AND
    ctx.spec.classifying_var is not None.
    """
    if not ctx.spec.elements.filter_var:
        return
    if not ctx.spec.classifying_var:
        return

    slot = ctx.slot
    # Position: below the N annotation (or at slot bottom if no N)
    left = slot.left + int(Inches(2.1))
    top = slot.top + slot.height - int(Inches(0.35))
    width = int(Inches(3.0))
    height = int(Inches(0.3))

    txBox = ctx.slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.text = ctx.spec.classifying_var

    font_name, font_size = ctx.style.font_for("filter_var")
    run = tf.paragraphs[0].runs[0]
    run.font.name = font_name
    run.font.size = Pt(font_size)
