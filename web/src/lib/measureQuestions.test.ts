import { describe, expect, it } from "vitest";
import { makeChart } from "./charts";

/** A continuous measure — an index, a score — has no answer categories, so a
 *  distribution of it is an empty slide and its mean is the finding. A slide on
 *  one therefore starts on Mean rather than on percentages. */
describe("a slide made from a measure", () => {
  it("starts on the mean", () => {
    expect(makeChart("tyoelamaindeksi", "vertical_bar", "mean").statistic).toBe("mean");
  });

  it("an ordinary question still starts on percentages", () => {
    expect(makeChart("q1", "horizontal_bar", "pct").statistic).toBe("pct");
  });

  it("says nothing and it is still percentages", () => {
    expect(makeChart("q1", "horizontal_bar").statistic).toBe("pct");
  });
});
