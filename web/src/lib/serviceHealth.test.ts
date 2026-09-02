/** When one feature is down, the app must not claim the service is.
 *
 *  Measured against the real thing on 2026-09-02: the hive container had lost
 *  DNS after the machine changed subnet, so its SSRF guard could not resolve
 *  the model's host and every `/api/v1/llm/ask` answered 502 — which reached
 *  the browser as 503 on `/ai/slide-title`. Everything else was healthy.
 *
 *  What the author saw was not an error page. It was a flicker: the 503 raised
 *  the outage screen, the readiness poll found the service perfectly well and
 *  cleared it, the next slide's headline raised it again. Two seconds up, gone,
 *  back — thirty-one slides deep. "Very briefly so I cannot see what it shows."
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { installFetchProbe, outage, reportReachable } from "./serviceHealth";

// The probe wraps `window.fetch` and reads `location`. This project has no DOM
// test environment, so the test supplies the two things it actually touches —
// without them `installFetchProbe` returns immediately and every assertion here
// would pass by doing nothing.
const ORIGIN = "http://localhost";
(globalThis as unknown as { location: unknown }).location = {
  origin: ORIGIN,
  pathname: "/cases",
  search: "",
};

/** A server where /readyz says what `ready` says, and everything else fails
 *  with `status`. */
function server(status: number, ready: boolean) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(typeof input === "string" ? input : (input as Request).url ?? input);
    if (url.includes("/readyz")) {
      return new Response(JSON.stringify({ ok: ready }), {
        status: ready ? 200 : 503,
        headers: { "content-type": "application/json" },
      });
    }
    return new Response("{}", { status });
  }) as unknown as typeof fetch;
}

function install(status: number, ready: boolean) {
  const f = server(status, ready);
  (globalThis as unknown as { window: unknown }).window = {
    fetch: f,
    location: (globalThis as unknown as { location: unknown }).location,
  };
  globalThis.fetch = f;
  installFetchProbe();
  // installFetchProbe replaces window.fetch with its wrapper; call THAT.
  return (globalThis as unknown as { window: { fetch: typeof fetch } }).window.fetch;
}

beforeEach(() => {
  reportReachable();
});

describe("one feature failing while the service is healthy", () => {
  it("does not raise the outage screen for a 503 the service itself denies", async () => {
    const f = install(503, true);

    await f(`${ORIGIN}/materials/m1/ai/slide-title`, { method: "POST" });
    await vi.waitFor(() => expect(outage()).toBe(null));
  });

  it("does not raise it for a 500 either, when the service is well", async () => {
    const f = install(500, true);

    await f(`${ORIGIN}/cases/c1/materials`, { method: "POST" });
    await vi.waitFor(() => expect(outage()).toBe(null));
  });
});

describe("the service itself being down", () => {
  it("raises the maintenance screen when readiness agrees the service is away", async () => {
    const f = install(503, false);

    await f(`${ORIGIN}/cases`);
    await vi.waitFor(() => expect(outage()).toBe("maintenance"));
  });

  it("raises the error screen for a 500 when readiness also fails", async () => {
    const f = install(500, false);

    await f(`${ORIGIN}/cases`);
    await vi.waitFor(() => expect(outage()).toBe("error"));
  });
});
