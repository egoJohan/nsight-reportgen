/** A slide with nothing to chart is reported to the editor, not to the client.
 *
 *  The picture used to carry "No data to show" in its middle — in English, on a
 *  slide that goes out with the deck. It is blank now, so the only person who
 *  can be told is the author, and the only thing that can tell them is the
 *  response: `X-Chart-Empty: 1`.
 *
 *  Absence means "nothing wrong with this one". A preview served from a cache
 *  written before the header existed is absent too, and that is the safe way
 *  round: a missed warning costs one look at the picture; a warning invented
 *  for a chart that has data costs trust in all of them. (Johan, 2026-09-16)
 */
import { describe, expect, it, vi } from "vitest";
import { api } from "./api";

function respondPng(headers: Record<string, string>) {
  globalThis.fetch = vi.fn(async () =>
    new Response(new Blob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])]), {
      status: 200,
      headers: { "content-type": "image/png", ...headers },
    })) as unknown as typeof fetch;
}

const CHART = { question_ref: "q1", chart_type: "bar" } as never;

describe("previewChart: the empty-chart signal", () => {
  it("reports a blank chart", async () => {
    respondPng({ "X-Chart-Empty": "1" });
    const r = await api.materials.previewChart("m1", CHART);
    expect(r.empty).toBe(true);
  });

  it("reports an ordinary chart as not blank", async () => {
    respondPng({});
    const r = await api.materials.previewChart("m1", CHART);
    expect(r.empty).toBe(false);
  });

  it("does not read any other value as blank", async () => {
    respondPng({ "X-Chart-Empty": "0" });
    const r = await api.materials.previewChart("m1", CHART);
    expect(r.empty).toBe(false);
  });

  it("reports how many categories went unlabelled", async () => {
    respondPng({ "X-Chart-Unlabelled": "25" });
    const r = await api.materials.previewChart("m1", CHART);
    expect(r.unlabelled).toBe(25);
  });

  it("reports none when the header is absent", async () => {
    respondPng({});
    const r = await api.materials.previewChart("m1", CHART);
    expect(r.unlabelled).toBe(0);
  });

  it("does not turn a nonsense header into a warning", async () => {
    respondPng({ "X-Chart-Unlabelled": "lots" });
    const r = await api.materials.previewChart("m1", CHART);
    expect(r.unlabelled).toBe(0);
  });
});
