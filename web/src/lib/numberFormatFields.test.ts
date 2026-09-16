import { describe, expect, it } from "vitest";
import {
  decimalFieldLabel,
  decimalFields,
  hasTwoMeasures,
  showsPercentSign,
} from "./numberFormatFields";

const chart = (over: Partial<Parameters<typeof decimalFields>[0]> = {}) => ({
  statistic: "pct",
  chart_type: "vertical_bar",
  options: {},
  ...over,
});

describe("which decimal boxes a chart needs", () => {
  it("offers one box for a percentage chart", () => {
    expect(decimalFields(chart())).toEqual(["pct"]);
  });

  it("offers one box for a mean chart", () => {
    expect(decimalFields(chart({ statistic: "mean" }))).toEqual(["mean"]);
  });

  it("calls the single box just Decimals", () => {
    const fields = decimalFields(chart());
    expect(decimalFieldLabel(fields[0], fields)).toBe("Decimals");
  });

  it("names the single box the same whichever measure it is", () => {
    const meanFields = decimalFields(chart({ statistic: "mean" }));
    expect(decimalFieldLabel(meanFields[0], meanFields)).toBe("Decimals");
  });

  it("offers no box where decimals change nothing", () => {
    // `count` is drawn with no decimals whatever these say.
    expect(decimalFields(chart({ statistic: "count" }))).toEqual([]);
  });
});

describe("the combo, which really does have two measures", () => {
  const combo = chart({
    chart_type: "combo",
    options: { combo_secondary: "tyoelamaindeksi" },
  });

  it("offers both boxes", () => {
    expect(decimalFields(combo)).toEqual(["pct", "mean"]);
  });

  it("names them specifically, because now the difference matters", () => {
    const fields = decimalFields(combo);
    expect(decimalFieldLabel("pct", fields)).toBe("% decimals");
    expect(decimalFieldLabel("mean", fields)).toBe("Mean decimals");
  });

  it("is one measure again without a secondary variable", () => {
    expect(hasTwoMeasures(chart({ chart_type: "combo" }))).toBe(false);
    expect(decimalFields(chart({ chart_type: "combo" }))).toEqual(["pct"]);
  });

  it("does not treat another chart type as two measures", () => {
    expect(
      hasTwoMeasures(chart({ options: { combo_secondary: "x" } })),
    ).toBe(false);
  });
});

describe("the percent sign toggle", () => {
  it("is offered where a percent sign is printed", () => {
    expect(showsPercentSign(chart())).toBe(true);
  });

  it("is offered on a combo, whose bars are percentages", () => {
    expect(
      showsPercentSign(
        chart({ chart_type: "combo", options: { combo_secondary: "x" } }),
      ),
    ).toBe(true);
  });

  it("is not offered for a mean, which never carries one", () => {
    expect(showsPercentSign(chart({ statistic: "mean" }))).toBe(false);
  });
});
