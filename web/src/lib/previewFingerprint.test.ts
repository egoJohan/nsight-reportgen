import { describe, expect, it } from "vitest";
import { IMAGE_FINGERPRINT_IGNORED, imageFingerprint } from "./previewFingerprint";
import { titleDataKey } from "./charts";
import type { ChartSpec } from "./api";

const CTX = { templateRef: "", reportId: "r1", groupingKey: "{}", renderTitle: false };

function chart(over: Partial<ChartSpec> = {}): ChartSpec {
  return {
    question_ref: "q1",
    chart_type: "bar",
    statistic: "pct",
    classifying_var: null,
    number_format: {},
    sort: { basis: "data_order", descending: true },
    template_slot: "s1",
    elements: {},
    scatter_xy: null,
    show_not_answered: false,
    show_empty_categories: true,
    not_answered_codes: null,
    category_label_overrides: [],
    slide_title: "A title",
    slide_description: null,
    footer_note: null,
    slide_id: "sl-1",
    ...over,
  } as unknown as ChartSpec;
}

describe("imageFingerprint", () => {
  it("moves when the chart type changes", () => {
    expect(imageFingerprint(chart(), CTX)).not.toBe(
      imageFingerprint(chart({ chart_type: "pie" }), CTX)
    );
  });

  it("moves when a field nobody registered changes — the deny-list property", () => {
    // The whole point of hashing by exclusion: a field added later still
    // invalidates the image. axis_x_title is exactly such a field, and under the
    // old 25-entry allow-list editing one showed the previous picture.
    const withAxis = { ...chart(), axis_x_title: "Ikäryhmä" } as ChartSpec;
    expect(imageFingerprint(chart(), CTX)).not.toBe(imageFingerprint(withAxis, CTX));
  });

  it("moves when the title changes, because the title is baked into the PNG", () => {
    expect(imageFingerprint(chart(), CTX)).not.toBe(
      imageFingerprint(chart({ slide_title: "Another" }), CTX)
    );
  });

  it("does NOT move on a reorder", () => {
    // normalizeSlots rewrites template_slot for every chart on any reorder, so
    // hashing it would re-render all sixty slides when the author drags one.
    expect(imageFingerprint(chart(), CTX)).toBe(
      imageFingerprint(chart({ template_slot: "s9" }), CTX)
    );
  });

  it("does NOT move on identity or bookkeeping fields", () => {
    const other = chart({
      slide_id: "sl-99",
      compare_group: "sukupuoli",
      excluded: true,
      slide_title_key: "some-key",
    } as Partial<ChartSpec>);
    expect(imageFingerprint(chart(), CTX)).toBe(imageFingerprint(other, CTX));
  });

  it("does NOT move when the same fields arrive in a different order", () => {
    // A chart rebuilt by a spread has identical values in a different key order,
    // and the fingerprint is a string — so it sorts before hashing.
    const base = chart();
    const reordered = Object.fromEntries(
      Object.entries(base).reverse()
    ) as unknown as ChartSpec;
    expect(imageFingerprint(base, CTX)).toBe(imageFingerprint(reordered, CTX));
  });

  it("moves with the render context", () => {
    expect(imageFingerprint(chart(), CTX)).not.toBe(
      imageFingerprint(chart(), { ...CTX, templateRef: "tpl-2" })
    );
    expect(imageFingerprint(chart(), CTX)).not.toBe(
      imageFingerprint(chart(), { ...CTX, groupingKey: '{"groups":[]}' })
    );
    expect(imageFingerprint(chart(), CTX)).not.toBe(
      imageFingerprint(chart(), { ...CTX, renderTitle: true })
    );
  });

  it("ignores exactly five fields, and no more", () => {
    expect([...IMAGE_FINGERPRINT_IGNORED].sort()).toEqual([
      "compare_group",
      "excluded",
      "slide_id",
      "slide_title_key",
      "template_slot",
    ]);
  });
});

describe("titleDataKey stays blind to presentation", () => {
  const q = { text: "Q", variables: ["v1"] };

  it("is unmoved by chart type, sort, axis titles and row summary", () => {
    // Each of these re-renders the slide and must NOT spend an LLM call
    // rewriting a headline that still says the same true thing about the data.
    const base = titleDataKey(chart(), q);
    expect(titleDataKey(chart({ chart_type: "pie" }), q)).toBe(base);
    expect(
      titleDataKey(chart({ sort: { basis: "bottom2_sum", descending: true } } as Partial<ChartSpec>), q)
    ).toBe(base);
    expect(titleDataKey({ ...chart(), axis_x_title: "Ikäryhmä" } as ChartSpec, q)).toBe(base);
    expect(
      titleDataKey(chart({ row_summary_fn: "bottom2_sum" } as Partial<ChartSpec>), q)
    ).toBe(base);
    expect(titleDataKey(chart({ template_slot: "s9" }), q)).toBe(base);
  });

  it("DOES move when the data behind the title changes", () => {
    const base = titleDataKey(chart(), q);
    expect(titleDataKey(chart({ classifying_var: "sukupuoli" }), q)).not.toBe(base);
    expect(titleDataKey(chart({ statistic: "mean" }), q)).not.toBe(base);
    expect(titleDataKey(chart(), { text: "A different question", variables: ["v1"] })).not.toBe(base);
  });

  it("DOES move when the slide is drawn on different groups", () => {
    // The pair of slides this feature exists for — the same battery through
    // design 1 and through design 2 — is made by duplicating the slide and
    // changing the tick. The copy's headline was written about the first
    // group's numbers; leaving it keeps a sentence that is now false, stated
    // as a finding.
    const base = titleDataKey(chart(), q);
    const one = titleDataKey(chart({ classifying_values: ["Design 1"] }), q);
    const two = titleDataKey(chart({ classifying_values: ["Design 2"] }), q);
    expect(one).not.toBe(base);
    expect(two).not.toBe(one);
  });
});

describe("the template a slide is drawn on", () => {
  it("changes the fingerprint when the resolved template changes", () => {
    // The bug: a customer with no template, a report inheriting it, previews
    // drawn on the default. Uploading a template to the customer changed what
    // every inheriting report resolves to — and the report's OWN template_ref
    // was "" before and "" after, so nothing busted and the old pictures
    // stayed. The context now carries the RESOLVED id, so this differs.
    const before = imageFingerprint(chart(), { ...CTX, templateRef: "" });
    const after = imageFingerprint(chart(), { ...CTX, templateRef: "tpl-holiday" });
    expect(before).not.toEqual(after);
  });

  it("is stable when nothing about the template changed", () => {
    expect(imageFingerprint(chart(), { ...CTX, templateRef: "tpl-a" })).toEqual(
      imageFingerprint(chart(), { ...CTX, templateRef: "tpl-a" })
    );
  });

  it("tells two templates apart", () => {
    expect(imageFingerprint(chart(), { ...CTX, templateRef: "tpl-a" })).not.toEqual(
      imageFingerprint(chart(), { ...CTX, templateRef: "tpl-b" })
    );
  });
});
