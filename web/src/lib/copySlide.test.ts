import { describe, expect, it } from "vitest";
import { copySlideInDeck } from "./charts";
import type { ChartSpec } from "./api";

/** Reported: "there is no copy or redraw buttons on special slides."
 *
 *  Copying one is not the same act as copying a chart slide. A special slide
 *  belongs to a GROUP — regenerating the conclusions replaces every page in the
 *  group with freshly written ones — so a copy that kept the group would be
 *  swept away the next time the original was regenerated, which is not a copy.
 */
const chart = (over: Partial<ChartSpec> = {}) =>
  ({
    question_ref: "q1",
    chart_type: "horizontal_bar",
    slide_id: "s1",
    ...over,
  }) as ChartSpec;

const special = (over: Partial<ChartSpec> = {}) =>
  ({
    question_ref: "sp_special_conclusion_abc",
    chart_type: "special_conclusion",
    slide_id: "s2",
    slide_title: "Conclusions",
    options: { bullets: ["one", "two"], group: "sp_special_conclusion_abc" },
    ...over,
  }) as ChartSpec;

describe("copying a slide", () => {
  it("puts the copy directly below the original", () => {
    const out = copySlideInDeck([chart(), special()], 0, "new");
    expect(out.map((c) => c.slide_id)).toEqual(["s1", "new", "s2"]);
  });

  it("keeps a chart slide's question and configuration", () => {
    const out = copySlideInDeck([chart({ statistic: "mean" } as Partial<ChartSpec>)], 0, "new");
    expect(out[1].question_ref).toBe("q1");
    expect(out[1].statistic).toBe("mean");
    expect(out[1].slide_id).toBe("new");
  });

  it("gives a special slide's copy its own identity and group", () => {
    const out = copySlideInDeck([special()], 0, "new");
    const [orig, copy] = out;
    expect(copy.question_ref).not.toBe(orig.question_ref);
    expect(copy.options?.group).toBe(copy.question_ref);
    expect(copy.options?.group).not.toBe(orig.options?.group);
  });

  it("carries the special slide's words across", () => {
    const [, copy] = copySlideInDeck([special()], 0, "new");
    expect(copy.slide_title).toBe("Conclusions");
    expect(copy.options?.bullets).toEqual(["one", "two"]);
  });

  it("does nothing when the index is not a slide", () => {
    expect(copySlideInDeck([chart()], 7, "new")).toHaveLength(1);
  });
});
