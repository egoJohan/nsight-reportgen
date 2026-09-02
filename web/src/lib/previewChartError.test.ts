/** A failed preview must say what the server said, AND what it answered.
 *
 *  The queue decides whether to wait a failure out by its status: 5xx, 408 and
 *  429 are "not now", everything else will fail the same however long we wait.
 *  This call threw a bare Error carrying only the message, so a 503 from the
 *  render host — the very case the spaced retries exist for — was read as
 *  permanent and given a single immediate retry. Measured against the running
 *  app: 31 slides, 63 attempts, all inside ten seconds, then silence.
 */
import { describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

function respond(status: number, body: unknown) {
  globalThis.fetch = vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    })) as unknown as typeof fetch;
}

const CHART = { question_ref: "q1", chart_type: "bar" } as never;

describe("previewChart failures", () => {
  it("carries the status, so a 503 can be waited out", async () => {
    respond(503, { detail: "render host is away" });
    await expect(api.materials.previewChart("m1", CHART)).rejects.toMatchObject({
      status: 503,
    });
  });

  it("still says what the server said", async () => {
    respond(503, { detail: "render host is away" });
    await expect(api.materials.previewChart("m1", CHART)).rejects.toThrow(
      "render host is away"
    );
  });

  it("carries a 4xx status too, so it is NOT waited out", async () => {
    respond(422, { detail: "this slide cannot be drawn" });
    const err = await api.materials.previewChart("m1", CHART).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
  });
});
