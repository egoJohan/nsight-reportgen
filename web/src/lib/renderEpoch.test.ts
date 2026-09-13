import { describe, expect, it } from "vitest";

import { imageFingerprint } from "./previewFingerprint";
import { nextRenderEpoch } from "./renderEpoch";

// An editor left open across a deploy went on showing pictures the old server
// drew: it keys a picture on what the chart asks for, and nothing about who drew
// it. /health now says which pictures the server draws (`render_identity`), and a
// change of it moves the epoch every picture key carries.

describe("nextRenderEpoch", () => {
  it("does not count the first answer after a page load as a change", () => {
    // Otherwise every slide would be drawn twice on opening a report.
    expect(nextRenderEpoch({ epoch: 0 }, "abc")).toEqual({ epoch: 0, identity: "abc" });
  });

  it("stays put while the server draws the same way", () => {
    expect(nextRenderEpoch({ epoch: 0, identity: "abc" }, "abc"))
      .toEqual({ epoch: 0, identity: "abc" });
  });

  it("moves on when the server was replaced", () => {
    expect(nextRenderEpoch({ epoch: 0, identity: "abc" }, "def"))
      .toEqual({ epoch: 1, identity: "def" });
    expect(nextRenderEpoch({ epoch: 1, identity: "def" }, "ghi"))
      .toEqual({ epoch: 2, identity: "ghi" });
  });

  it("ignores a check that did not answer", () => {
    // A server mid-restart, or one too old to say: nothing is known to have changed.
    expect(nextRenderEpoch({ epoch: 1, identity: "def" }, undefined))
      .toEqual({ epoch: 1, identity: "def" });
    expect(nextRenderEpoch({ epoch: 1, identity: "def" }, ""))
      .toEqual({ epoch: 1, identity: "def" });
  });
});

describe("imageFingerprint", () => {
  const chart = { chart_type: "stacked_horizontal_bar", question_ref: "q" } as never;
  const ctx = { templateRef: "t", reportId: "r", groupingKey: "{}", renderTitle: false };

  it("is a different picture once the server draws differently", () => {
    expect(imageFingerprint(chart, { ...ctx, renderEpoch: 1 }))
      .not.toEqual(imageFingerprint(chart, { ...ctx, renderEpoch: 0 }));
  });

  it("is the same picture while it does not", () => {
    expect(imageFingerprint(chart, { ...ctx, renderEpoch: 0 }))
      .toEqual(imageFingerprint(chart, { ...ctx }));
  });
});
