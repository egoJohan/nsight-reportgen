import { beforeEach, describe, expect, it, vi } from "vitest";
import * as q from "./previewQueue";
import type { ChartSpec } from "./api";
import type { Producer } from "./previewQueue";

const slides = new Map<string, ChartSpec>();

function put(id: string, over: Partial<ChartSpec> = {}) {
  slides.set(id, {
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
    slide_title: null,
    slide_description: null,
    footer_note: null,
    slide_id: id,
    ...over,
  } as unknown as ChartSpec);
}

/** A producer that always needs to run, recording the chart it saw. */
function producer(id: q.ProducerId, over: Partial<Producer> = {}): Producer {
  return {
    id,
    fingerprint: () => id,
    storedFingerprint: () => null,
    run: async () => {},
    onFailure: "continue",
    ...over,
  } as Producer;
}

beforeEach(() => {
  slides.clear();
  q.__resetForTest();
  q.setSlideSource((id) => slides.get(id) ?? null);
  // The wizard applies patches to the draft; here the draft IS `slides`.
  q.setPatchSink((id, patch) => {
    const cur = slides.get(id);
    if (cur) slides.set(id, { ...cur, ...patch } as ChartSpec);
  });
  q.setRenderContext({ templateRef: "", reportId: "r1", groupingKey: "{}", renderTitle: false });
});

describe("the sequential run", () => {
  it("runs producers in registry order, and the image sees the title just written", async () => {
    const seen: string[] = [];
    put("s1");
    q.__setProducersForTest([
      producer("title", {
        run: async () => {
          seen.push("title");
          return { slide_title: "Made by AI" };
        },
      }),
      producer("chart", {
        run: async (c) => {
          seen.push(`chart:${c.chart.slide_title}`);
        },
        onFailure: "abort",
      }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    // Patches flush to React in batches, so reading React state here would show
    // the OLD title: the image would be fingerprinted against it, rendered, and
    // then found stale — for ever. Producers read their own writes.
    expect(seen).toEqual(["title", "chart:Made by AI"]);
  });

  it("skips a producer whose fingerprint matches what is stored", async () => {
    put("s1");
    const run = vi.fn(async () => {});
    q.__setProducersForTest([
      producer("chart", { fingerprint: () => "same", storedFingerprint: () => "same", run }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    expect(run).not.toHaveBeenCalled();
  });

  it("drops a slide deleted while it was queued", async () => {
    // Concurrency 1, so "gone" is still WAITING while "first" runs — pump()
    // starts the head of the queue synchronously, so a single enqueue would
    // already be running by the time the delete lands.
    put("first");
    put("gone");
    const seen: string[] = [];
    q.__setProducersForTest([
      producer("chart", {
        run: async (c) => {
          seen.push(c.slideId);
          if (c.slideId === "first") slides.delete("gone");
        },
      }),
    ]);
    q.__setConcurrencyForTest(1);
    q.enqueue("first");
    q.enqueue("gone");
    await q.__drainForTest();
    expect(seen).toEqual(["first"]);
  });

  it("re-enqueues a slide edited while it was running", async () => {
    put("s1");
    let calls = 0;
    q.__setProducersForTest([
      producer("chart", {
        // Needed while the title is empty; the run fills it in, so the second
        // pass finds nothing to do and the loop terminates.
        fingerprint: (c) => String(c.chart.slide_title ?? ""),
        storedFingerprint: (c) => (c.chart.slide_title ? c.fingerprint : null),
        run: async () => {
          calls += 1;
          return calls === 1 ? { slide_title: "filled" } : {};
        },
      }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    expect(calls).toBe(1);
    expect(slides.get("s1")?.slide_title).toBe("filled");
  });
});

describe("failure", () => {
  it("still renders the image when the title fails", async () => {
    put("s1");
    const chartRun = vi.fn(async () => {});
    q.__setProducersForTest([
      producer("title", {
        run: async () => {
          throw new Error("egoHive is down");
        },
        onFailure: "continue",
      }),
      producer("chart", { run: chartRun, onFailure: "abort" }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    expect(chartRun).toHaveBeenCalled();
    expect(q.statusOf("s1").title).toBe("failed");
  });

  it("records the failure so it can be retried and shown", async () => {
    put("s1");
    q.__setProducersForTest([
      producer("title", {
        run: async () => {
          throw new Error("egoHive is down");
        },
      }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    const failures = q.failuresOf("s1");
    expect(failures).toHaveLength(1);
    expect((failures[0].error as Error).message).toBe("egoHive is down");
    // NOT marked done, so the work is still outstanding rather than forgotten.
    expect(q.statusOf("s1").title).not.toBe("done");
  });

  it("stops the slide when an aborting producer fails", async () => {
    put("s1");
    const after = vi.fn(async () => {});
    q.__setProducersForTest([
      producer("chart", {
        run: async () => {
          throw new Error("render failed");
        },
        onFailure: "abort",
      }),
      producer("bullets", { run: after }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    expect(after).not.toHaveBeenCalled();
  });
});

describe("the queue", () => {
  it("promotes the slide the author selected", async () => {
    const done: string[] = [];
    ["a", "b", "c"].forEach((id) => put(id));
    q.__setProducersForTest([
      producer("chart", {
        run: async (c) => {
          done.push(c.slideId);
        },
      }),
    ]);
    q.__setConcurrencyForTest(1);
    ["a", "b", "c"].forEach(q.enqueue);
    q.promote("c");
    await q.__drainForTest();
    // "a" is already running when the promotion lands; "c" jumps the rest.
    expect(done[1]).toBe("c");
  });

  it("does not queue the same slide twice", async () => {
    put("s1");
    const run = vi.fn(async () => {});
    q.__setProducersForTest([producer("chart", { run })]);
    q.__setConcurrencyForTest(1);
    q.enqueue("s1");
    q.enqueue("s1");
    q.enqueue("s1");
    await q.__drainForTest();
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("is busy while work is outstanding and idle once it is done", async () => {
    put("s1");
    q.__setProducersForTest([producer("chart", { run: async () => {} })]);
    q.enqueue("s1");
    expect(q.isBusy()).toBe(true);
    await q.__drainForTest();
    expect(q.isBusy()).toBe(false);
  });

  it("forgets another report's statuses on reset", async () => {
    put("s1");
    q.__setProducersForTest([producer("chart", { run: async () => {} })]);
    q.enqueue("s1");
    await q.__drainForTest();
    expect(q.statusOf("s1").chart).toBe("done");
    q.reset("a-different-report");
    expect(q.statusOf("s1").chart).toBeUndefined();
  });

  it("tells subscribers when something changes", async () => {
    put("s1");
    const seen = vi.fn();
    const off = q.subscribe(seen);
    q.__setProducersForTest([producer("chart", { run: async () => {} })]);
    q.enqueue("s1");
    await q.__drainForTest();
    expect(seen).toHaveBeenCalled();
    off();
  });
});
