import { describe, expect, it } from "vitest";
import type { ChartSpec } from "./api";
import { legendNamesKey, legendRows, withSeriesOverride } from "./legendLabels";

describe("legendRows", () => {
  it("lists the groups", () => {
    expect(legendRows(["Mies", "Nainen"], ["Kyllä", "Ei"])).toEqual(["Mies", "Nainen"]);
  });
  it("leaves out a name the answers list already offers", () => {
    expect(legendRows(["Kyllä", "Muu"], ["Kyllä", "Ei"])).toEqual(["Muu"]);
  });
  it("is empty when the slide draws no groups", () => {
    expect(legendRows([], ["Kyllä"])).toEqual([]);
  });
});

describe("withSeriesOverride", () => {
  it("stores a rename", () => {
    expect(withSeriesOverride([], "Mies", "Miehet")).toEqual([["Mies", "Miehet"]]);
  });
  it("replaces an earlier rename of the same name", () => {
    expect(withSeriesOverride([["Mies", "M"]], "Mies", "Miehet")).toEqual([["Mies", "Miehet"]]);
  });
  it("removes it when cleared or set back to the name itself", () => {
    expect(withSeriesOverride([["Mies", "M"]], "Mies", "  ")).toEqual([]);
    expect(withSeriesOverride([["Mies", "M"]], "Mies", "Mies")).toEqual([]);
  });
  it("keeps the other renames", () => {
    expect(withSeriesOverride([["Nainen", "Naiset"]], "Mies", "Miehet"))
      .toEqual([["Nainen", "Naiset"], ["Mies", "Miehet"]]);
  });
  it("treats a slide saved before the setting as having none", () => {
    expect(withSeriesOverride(undefined, "Mies", "Miehet")).toEqual([["Mies", "Miehet"]]);
  });
});

describe("legendNamesKey", () => {
  const chart = {
    question_ref: "q", chart_type: "combo", classifying_var: "sex",
    options: { combo_secondary: "idx" }, slide_title: "A",
    series_label_overrides: [], category_label_overrides: [],
  } as unknown as ChartSpec;

  it("does not change when only a name or the headline changes", () => {
    const renamed = { ...chart, slide_title: "B",
      series_label_overrides: [["Mies", "Miehet"]],
      category_label_overrides: [["Kyllä", "K"]] } as unknown as ChartSpec;
    expect(legendNamesKey(renamed)).toBe(legendNamesKey(chart));
  });
  it("changes with anything that decides the groups", () => {
    expect(legendNamesKey({ ...chart, classifying_var: "age" })).not.toBe(legendNamesKey(chart));
    expect(legendNamesKey({ ...chart, options: { combo_secondary: "x" } }))
      .not.toBe(legendNamesKey(chart));
    expect(legendNamesKey({ ...chart, classifying_values: ["Mies"] } as ChartSpec))
      .not.toBe(legendNamesKey(chart));
  });
});
