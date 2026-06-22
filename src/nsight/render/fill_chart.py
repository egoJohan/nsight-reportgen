from __future__ import annotations

from pptx.chart.data import CategoryChartData


def fill_chart(shape, *, categories: list[str], series: dict[str, list[float]]) -> None:
    """Replace a native chart's data in place, preserving its type and styling.

    Keep the number of series and categories equal to the template's so per-point
    formatting (colors, data labels) survives.
    """
    if not shape.has_chart:
        raise ValueError(f"shape {shape.name!r} is not a chart")
    data = CategoryChartData()
    data.categories = categories
    for name, values in series.items():
        data.add_series(name, tuple(values))
    shape.chart.replace_data(data)


def read_chart_series(shape) -> dict[str, list]:
    """Return {series_name: list(values)} for the chart's first plot.

    None values are preserved as-is. Raises ValueError if shape has no chart.
    """
    if not shape.has_chart:
        raise ValueError(f"shape {shape.name!r} is not a chart")
    plot = shape.chart.plots[0]
    return {s.name: list(s.values) for s in plot.series}


def read_chart_categories(shape) -> list[str]:
    """Return [str(c) for c in first plot's categories]. Raises ValueError if no chart."""
    if not shape.has_chart:
        raise ValueError(f"shape {shape.name!r} is not a chart")
    plot = shape.chart.plots[0]
    return [str(c) for c in plot.categories]


def replace_one_series(shape, *, series_name: str, values: list) -> None:
    """Replace exactly one series by name, preserving all other series and categories.

    Raises KeyError if series_name is not present in the chart.
    """
    existing_series = read_chart_series(shape)
    if series_name not in existing_series:
        raise KeyError(
            f"series {series_name!r} not found in chart; "
            f"available: {list(existing_series)}"
        )
    existing_cats = read_chart_categories(shape)
    merged = {name: (values if name == series_name else vals)
              for name, vals in existing_series.items()}
    fill_chart(shape, categories=existing_cats, series=merged)
