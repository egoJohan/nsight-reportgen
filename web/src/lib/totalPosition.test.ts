import { describe, expect, it } from "vitest";

import { drawsTotal } from "./totalPosition";

// (show_total, chart_type, statistic, percent_base, drawn) — the SAME table as
// tests/suite/unit/render/test_total_position.py::_DRAWS_TOTAL, which pins it to
// the engine's resolve_show_total. The editor offers "Total position" only while
// a Total is drawn, and decides that with this copy of the engine's rule.
const TABLE: [string, string, string, string, boolean][] = [
  ["on", "vertical_bar", "pct", "classifier", true],
  ["off", "stacked_horizontal_bar", "pct", "total", false],
  ["auto", "stacked_horizontal_bar", "pct", "classifier", true],
  ["auto", "stacked_vertical_bar", "pct", "question", true],
  ["auto", "vertical_bar", "pct", "classifier", false],
  ["auto", "horizontal_bar", "pct", "auto", false],
  ["auto", "vertical_bar", "pct", "total", true],
  ["auto", "line", "mean", "classifier", true],
  ["auto", "radar", "count", "question", true],
];

describe("drawsTotal", () => {
  it.each(TABLE)(
    "show_total=%s on %s (%s, %s) → %s",
    (show_total, chart_type, statistic, percent_base, drawn) => {
      expect(drawsTotal({
        classifying_var: "sp", show_total, chart_type, statistic, percent_base,
      })).toBe(drawn);
    },
  );

  it("has nothing to place without a classifying variable", () => {
    // The engine draws a Total there — it is the only series — but a chart of
    // one series has nowhere else to put it.
    expect(drawsTotal({
      classifying_var: null, show_total: "on", chart_type: "vertical_bar",
      statistic: "pct", percent_base: "total",
    })).toBe(false);
  });

  it("has no Total to place when a second variable is crossed with the first", () => {
    // Crossed combos ("Naiset · 18-39") carry no Total, even with it set to Show.
    for (const xtab_layout of [undefined, "auto", "grouped", "small_multiples"]) {
      expect(drawsTotal({
        classifying_var: "sp", classifying_var_2: "ika",
        options: xtab_layout ? { xtab_layout } : {},
        show_total: "on", chart_type: "stacked_horizontal_bar", statistic: "pct",
      })).toBe(false);
    }
  });

  it("keeps it for separate panels, each of which has its own Total", () => {
    expect(drawsTotal({
      classifying_var: "sp", classifying_var_2: "ika", options: { xtab_layout: "separate" },
      show_total: "on", chart_type: "stacked_horizontal_bar", statistic: "pct",
    })).toBe(true);
  });

  it("reads a report saved before show_total existed as automatic", () => {
    expect(drawsTotal({
      classifying_var: "sp", chart_type: "stacked_horizontal_bar", statistic: "pct",
    })).toBe(true);
  });
});
