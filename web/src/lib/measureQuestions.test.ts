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

/** Creating a report pre-selects the study's questions. A measure is not one of
 *  them: the file that prompted this carries thirteen rescaled recodes beside
 *  its six indices, and starting every new report with all twenty on it is the
 *  clutter the browser's hold-back exists to prevent. They are one click away
 *  in Select, where the author chooses. */
describe("what a new report starts with", () => {
  const q = (qid: string, offered: boolean) => ({
    qid,
    suggested_chart_type: "vertical_bar",
    suggested_statistic: offered ? "pct" : "mean",
    offered_by_default: offered,
  });

  it("takes the study's questions and leaves the measures out", () => {
    const picked = [q("q1", true), q("idx", false), q("q2", true)]
      .filter((x) => x.offered_by_default !== false)
      .map((x) => makeChart(x.qid, x.suggested_chart_type, x.suggested_statistic));
    expect(picked.map((c) => c.question_ref)).toEqual(["q1", "q2"]);
  });

  it("and a measure added by hand still starts on the mean", () => {
    const m = q("idx", false);
    expect(makeChart(m.qid, m.suggested_chart_type, m.suggested_statistic).statistic)
      .toBe("mean");
  });
});
