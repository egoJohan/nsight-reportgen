import { describe, expect, it } from "vitest";
import { CONTROL_SETTLE_MS, TEXT_SETTLE_MS, settleDelay } from "./editSettle";

const base = {
  slide_id: "a",
  chart_type: "vertical_bar",
  slide_title: "Otsikko",
  elements: { legend: true },
  options: { bullets: ["yksi"], xtab_layout: "auto" },
};

const prev = (...charts: Record<string, unknown>[]) =>
  new Map(charts.map((c) => [String(c.slide_id), c]));

describe("settleDelay", () => {
  it("waits out a sentence while a title is being typed", () => {
    expect(settleDelay(prev(base), [{ ...base, slide_title: "Otsikko on" }]))
      .toBe(TEXT_SETTLE_MS);
  });

  it("counts typed bullets as text", () => {
    expect(settleDelay(prev(base), [{ ...base, options: { ...base.options, bullets: ["yksi", "ka"] } }]))
      .toBe(TEXT_SETTLE_MS);
  });

  it("does not make a dropdown wait for a sentence", () => {
    expect(settleDelay(prev(base), [{ ...base, chart_type: "pie" }])).toBe(CONTROL_SETTLE_MS);
  });

  it("treats a toggle as a control", () => {
    expect(settleDelay(prev(base), [{ ...base, elements: { legend: false } }]))
      .toBe(CONTROL_SETTLE_MS);
  });

  it("treats a changed option other than text as a control", () => {
    expect(settleDelay(prev(base), [{ ...base, options: { ...base.options, xtab_layout: "separate" } }]))
      .toBe(CONTROL_SETTLE_MS);
  });

  it("is quick when a control and text change together", () => {
    expect(settleDelay(prev(base), [{ ...base, slide_title: "Uusi", chart_type: "line" }]))
      .toBe(CONTROL_SETTLE_MS);
  });

  it("is quick for a slide added or removed", () => {
    expect(settleDelay(prev(base), [base, { ...base, slide_id: "b" }])).toBe(CONTROL_SETTLE_MS);
    expect(settleDelay(prev(base, { ...base, slide_id: "b" }), [base])).toBe(CONTROL_SETTLE_MS);
  });
});
