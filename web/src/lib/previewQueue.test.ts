import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as q from "./previewQueue";
import { ApiError } from "./api";
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
  // A report is OPEN. The queue does no work when none is — closing the editor
  // has to stop it, not put every unfinished slide back on the queue — so a
  // test that models the queue running has to model that too.
  q.reset("r1");
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

  it("re-queues the slide the author is looking at at the head, not behind the deck", async () => {
    const order: string[] = [];
    for (let i = 1; i <= 5; i++) put(`s${i}`);
    q.__setProducersForTest([
      producer("chart", {
        // Every pass needs to run, so the order below is the render order.
        fingerprint: (c) => `${c.slideId}:${c.chart.slide_title ?? ""}`,
        run: async (c) => {
          order.push(c.slideId);
        },
      }),
    ]);
    q.__setConcurrencyForTest(1);
    // The author selects s4 and it renders.
    q.setFocused("s4");
    q.enqueue("s4");
    await q.__drainForTest();
    // The rest of the deck is still to draw — a report that has just been
    // opened, or a template that has just changed.
    for (const id of ["s1", "s2", "s3", "s5"]) q.enqueue(id);
    // Now they type a headline into s4. Selecting it is what said they are
    // looking at it; typing into it does not say it again, so the queue has to
    // remember rather than be told twice.
    slides.set("s4", { ...(slides.get("s4") as ChartSpec), slide_title: "Typed" });
    q.enqueue("s4");
    // Not merely first in line — started. The author is looking at it, so it
    // gets a slot of its own rather than waiting for one to free.
    expect(q.snapshot().running).toContain("s4");
    expect(q.snapshot().queued).not.toContain("s4");
    await q.__drainForTest();
    // s1 was already running when the edit landed; the author's own slide is
    // next, rather than last behind every slide they are not looking at.
    expect(order).toEqual(["s4", "s1", "s4", "s2", "s3", "s5"]);
  });

  it("keeps the author's slide first when the whole deck is re-queued", async () => {
    // Switching template or font restarts the deck from the top. The slide
    // being looked at should not go back to its position in the deck.
    for (let i = 1; i <= 5; i++) put(`s${i}`);
    q.__setProducersForTest([producer("chart", { run: async () => {} })]);
    q.__setConcurrencyForTest(1);
    q.setDeck(["s1", "s2", "s3", "s4", "s5"]);
    q.setFocused("s4");
    q.restartDeck("the template changed");
    expect(q.snapshot().running).toContain("s4");
  });

  it("draws no more at once than the renderer can, while headlines overlap freely",
     async () => {
    // Two kinds of work with nothing in common but the slide they belong to.
    // Writing a headline is a round trip to a model: seconds long, spent
    // waiting, and costing the render host nothing. Drawing the picture is
    // that host's CPU. Binding both to the core count made a cold sixty-slide
    // report pay its headlines one at a time — measured at 141s of the 162s a
    // thirty-slide deck took to open.
    let titlesInFlight = 0, titlePeak = 0;
    let chartsInFlight = 0, chartPeak = 0;
    const release: Array<() => void> = [];
    let gateOpen = false;
    // Once opened it stays open, so the passes that only START after the first
    // four finish are not left holding a promise nobody resolves.
    const hold = () =>
      gateOpen ? Promise.resolve() : new Promise<void>((r) => release.push(r));

    for (let i = 1; i <= 6; i++) put(`s${i}`);
    q.__setProducersForTest([
      producer("title", {
        fingerprint: (c) => c.slideId,
        run: async () => {
          titlesInFlight += 1;
          titlePeak = Math.max(titlePeak, titlesInFlight);
          await hold();
          titlesInFlight -= 1;
        },
      }),
      producer("chart", {
        fingerprint: (c) => c.slideId,
        cpuBound: true,
        run: async () => {
          chartsInFlight += 1;
          chartPeak = Math.max(chartPeak, chartsInFlight);
          await Promise.resolve();
          chartsInFlight -= 1;
        },
      }),
    ]);
    q.setRenderConcurrency(1);      // one core answering
    q.__setConcurrencyForTest(4);   // four slide passes may be in flight
    for (let i = 1; i <= 6; i++) q.enqueue(`s${i}`);
    // Let the four passes reach their title calls before any of them returns.
    await Promise.resolve();
    await Promise.resolve();
    expect(titlePeak).toBe(4);
    gateOpen = true;
    while (release.length) release.shift()!();
    await q.__drainForTest();
    expect(chartPeak).toBe(1);
  });

  it("does not queue, or claim to be working on, a slide with nothing to do", async () => {
    put("s1");
    const run = vi.fn(async () => {});
    q.__setProducersForTest([
      // Already satisfied: stored matches what this pass would produce.
      producer("chart", { fingerprint: () => "same", storedFingerprint: () => "same", run }),
    ]);
    q.enqueue("s1");
    // Not "pending". The wizard re-enqueues a slide whenever its content
    // changes, and the biggest such change is the queue's OWN generated
    // headline landing in the draft — so a settled slide is routinely offered
    // back to the queue. Marking it pending there put "Updating…" over a
    // finished slide for as long as it took to reach the head of the queue,
    // which on a deck still drawing is a minute of a badge for no work at all.
    expect(q.statusOf("s1").chart).not.toBe("pending");
    expect(q.isBusy()).toBe(false);
    await q.__drainForTest();
    expect(run).not.toHaveBeenCalled();
  });

  it("starts the author's slide at once, even with every background slot taken",
     async () => {
    const started: string[] = [];
    for (let i = 1; i <= 6; i++) put(`s${i}`);
    const release: Array<() => void> = [];
    let open = false;
    const hold = () => (open ? Promise.resolve() : new Promise<void>((r) => release.push(r)));
    q.__setProducersForTest([
      producer("chart", {
        fingerprint: (c) => c.slideId,
        run: async (c) => {
          started.push(c.slideId);
          await hold();
        },
      }),
    ]);
    q.__setConcurrencyForTest(2);
    for (let i = 1; i <= 6; i++) q.enqueue(`s${i}`);
    // Both background slots are taken and nothing has finished.
    expect(started).toEqual(["s1", "s2"]);
    // The author clicks s6. Waiting for one of the two to finish is the whole
    // of "clicking a slide takes ten seconds": measured on a cold deck, the
    // wait grew with the background fan-out — 6.0s at one pass, 9.8s at four,
    // 19.8s at eight — because the slide being LOOKED AT queued behind slides
    // nobody was looking at. It gets a slot of its own instead.
    q.setFocused("s6");
    expect(started).toEqual(["s1", "s2", "s6"]);
    // Exactly one extra, not a free-for-all: s3 still waits its turn.
    expect(started).not.toContain("s3");
    open = true;
    while (release.length) release.shift()!();
    await q.__drainForTest();
    expect(new Set(started).size).toBe(6);
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

describe("work abandoned because the context changed", () => {
  it("re-queues a slide whose render was abandoned mid-run", async () => {
    // THE regression. `enqueue` drops a slide that is already running, and both
    // the abandon path and the tail re-check call it from INSIDE the run — so
    // an abandoned slide was never picked up again and sat unfinished for ever.
    // That is what switching templates looked like: nothing ever finished.
    put("s1");
    let runs = 0;
    q.__setProducersForTest([
      producer("chart", {
        fingerprint: () => `ctx-${q.__generationForTest()}`,
        storedFingerprint: () => null,
        run: async () => {
          runs += 1;
          if (runs === 1) {
            // The author picks a different template while this render is out.
            q.setRenderContext({
              templateRef: "tpl-2",
              reportId: "r1",
              groupingKey: "{}",
              renderTitle: false,
            });
          }
        },
      }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    expect(runs).toBe(2); // abandoned once, then done under the new context
    expect(q.isBusy()).toBe(false);
  });

  it("leaves nothing running or queued once it settles", async () => {
    ["a", "b", "c", "d"].forEach((id) => put(id));
    let first = true;
    q.__setProducersForTest([
      producer("chart", {
        fingerprint: () => `ctx-${q.__generationForTest()}`,
        storedFingerprint: () => null,
        run: async () => {
          if (first) {
            first = false;
            q.setRenderContext({
              templateRef: "tpl-9",
              reportId: "r1",
              groupingKey: "{}",
              renderTitle: false,
            });
          }
        },
      }),
    ]);
    ["a", "b", "c", "d"].forEach(q.enqueue);
    await q.__drainForTest();
    const state = q.snapshot();
    expect(state.running).toEqual([]);
    expect(state.queued).toEqual([]);
    expect(state.requeue).toEqual([]);
    // And nothing is left claiming it still has work to do.
    expect(Object.keys(state.unfinished)).toEqual([]);
  });

  it("records what it did, so a stuck queue can be diagnosed", async () => {
    put("s1");
    q.clearTrace();
    q.__setProducersForTest([producer("chart", { run: async () => {} })]);
    q.enqueue("s1");
    await q.__drainForTest();
    const events = q.getTrace().map((e) => e.event);
    expect(events).toContain("enqueue");
    expect(events).toContain("start");
    expect(events).toContain("run");
    expect(events).toContain("done");
    expect(events).toContain("settled");
  });
});

describe("work the author overtook while it was running", () => {
  it("does not write a generated title over one typed while it was in flight", async () => {
    // The window is real and not small: the title request is a round trip to a
    // model. The author sees an untitled slide, types a headline, and a few
    // seconds later it is replaced by a machine's — with no undo, because the
    // typing was never saved as anything the queue knew about.
    put("s1");
    let release!: () => void;
    const inFlight = new Promise<void>((r) => (release = r));
    q.__setProducersForTest([
      producer("title", {
        run: async () => {
          await inFlight;
          return { slide_title: "What the model wrote", slide_title_key: "fp" };
        },
        supersededBy: (before, after) =>
          (after.slide_title ?? "") !== (before.slide_title ?? "") &&
          !after.slide_title_key,
      }),
    ]);
    q.enqueue("s1");
    const drained = q.__drainForTest();
    // The author types while the request is out.
    slides.set("s1", { ...slides.get("s1")!, slide_title: "My own headline",
                       slide_title_key: null } as ChartSpec);
    release();
    await drained;

    expect(slides.get("s1")!.slide_title).toBe("My own headline");
  });

  it("still writes it when the author did not touch the slide", async () => {
    put("s1");
    q.__setProducersForTest([
      producer("title", {
        run: async () => ({ slide_title: "What the model wrote", slide_title_key: "fp" }),
        supersededBy: (before, after) =>
          (after.slide_title ?? "") !== (before.slide_title ?? "") &&
          !after.slide_title_key,
      }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();

    expect(slides.get("s1")!.slide_title).toBe("What the model wrote");
  });
});

describe("opening the same report again", () => {
  it("does not shadow the reloaded draft with the last session's patches", async () => {
    // The overlay exists so a producer reads its own writes mid-pass, and it
    // usually cleans itself up: once the draft catches up, readSlide drops the
    // key. The case where it does NOT is the one that matters — a patch written
    // moments before the editor closes, whose React state update dies with the
    // unmount and never reaches the server.
    //
    // reset() then skipped clearing it, because the report id was unchanged. So
    // reopening that report laid the dead patch back over a draft freshly
    // fetched from the server, and the slide came back showing something that
    // was never saved.
    put("s1");
    q.setPatchSink(() => {});   // the update dies on unmount
    q.__setProducersForTest([
      producer("title", { run: async () => ({ slide_title: "Never saved" }) }),
    ]);
    q.reset("r1");
    q.enqueue("s1");
    await q.__drainForTest();

    // Reopened: the wizard remounts on the SAME report with a fresh draft.
    put("s1");
    q.reset("r1");

    let sawTitle: unknown = "unset";
    q.__setProducersForTest([
      producer("title", { run: async (c) => { sawTitle = c.chart.slide_title; } }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    expect(sawTitle).toBeNull();
  });
});

describe("a producer that fails", () => {
  it("is tried once more before the slide is given up on", async () => {
    // Most failures here are transient — the backend restarting, a proxy timing
    // out. Before this the slide simply stayed broken until the author noticed
    // and edited it, which nobody does for a slide they are not looking at.
    put("s1");
    let attempts = 0;
    q.__setProducersForTest([
      producer("chart", {
        onFailure: "abort",
        run: async () => {
          attempts += 1;
          if (attempts === 1) throw new Error("connection reset");
          return { slide_title: "drew on the second go" };
        },
      }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();

    expect(attempts).toBe(2);
    expect(q.failuresOf("s1")).toEqual([]);
    expect(slides.get("s1")!.slide_title).toBe("drew on the second go");
  });

  it("gives up after that one retry rather than looping", async () => {
    put("s1");
    let attempts = 0;
    q.__setProducersForTest([
      producer("chart", {
        onFailure: "abort",
        run: async () => { attempts += 1; throw new Error("genuinely broken"); },
      }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();

    expect(attempts).toBe(2);
    expect(q.failuresOf("s1").map((f) => f.id)).toEqual(["chart"]);
  });
});

describe("closing the editor", () => {
  it("stops rendering a deck nobody has open", async () => {
    // Without this the queue carried on: model calls and renders spent on a
    // report that is no longer on screen, and patches posted into a sink whose
    // component is gone. Worse, work abandoned mid-run put itself straight back
    // on the queue, so closing a report during a re-render started it again.
    put("s1");
    put("s2");
    const ran: string[] = [];
    let release!: () => void;
    const held = new Promise<void>((r) => (release = r));
    q.__setProducersForTest([
      producer("chart", {
        run: async (c) => {
          ran.push(c.slideId);
          await held;
        },
      }),
    ]);
    q.__setConcurrencyForTest(1);
    q.enqueue("s1");
    q.enqueue("s2");
    const drained = q.__drainForTest();

    q.reset("");        // the editor closes
    release();
    await drained;

    expect(ran).toEqual(["s1"]);
    const state = q.snapshot();
    expect(state.queued).toEqual([]);
    expect(state.running).toEqual([]);
  });

  it("still redoes work when the context moves and the report is open", async () => {
    // The other side of the same guard: abandoning for a template switch must
    // still come back, or a switch mid-render leaves slides unfinished.
    put("s1");
    let attempts = 0;
    q.__setProducersForTest([
      producer("chart", {
        run: async () => {
          attempts += 1;
          if (attempts === 1) {
            q.setRenderContext({ templateRef: "other", reportId: "r1",
                                 groupingKey: "{}", renderTitle: false });
          }
        },
      }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    expect(attempts).toBeGreaterThan(1);
  });
});

describe("with no report open", () => {
  it("refuses work the case page asks for after the editor closed", async () => {
    // Renaming a question or editing word merges from the CASE page calls
    // restartDeck. That used to re-queue every slide of the report last closed:
    // an AI-title call and a full render each, posted into a component that is
    // gone.
    put("s1");
    put("s2");
    const ran: string[] = [];
    q.setDeck(["s1", "s2"]);
    q.__setProducersForTest([producer("chart", { run: async (c) => { ran.push(c.slideId); } })]);

    q.reset("");
    q.restartDeck("a question was renamed");
    q.enqueue("s1");
    await q.__drainForTest();

    expect(ran).toEqual([]);
  });

  it("reports itself idle once the session ends", async () => {
    put("s1");
    q.__setProducersForTest([producer("chart", { run: async () => {} })]);
    q.enqueue("s1");
    await q.__drainForTest();
    q.reset("");
    expect(q.isBusy()).toBe(false);
  });
});

describe("a producer that fails soft", () => {
  it("does not cost the slide the producers after it", async () => {
    // A headline nobody could write must not also cost the slide its picture.
    put("s1");
    const ran: string[] = [];
    let titleAttempts = 0;
    q.__setProducersForTest([
      producer("title", {
        onFailure: "continue",
        run: async () => {
          titleAttempts += 1;
          ran.push("title");
          if (titleAttempts === 1) throw new Error("the model was busy");
        },
      }),
      producer("chart", { run: async () => { ran.push("chart"); } }),
    ]);
    q.enqueue("s1");
    await q.__drainForTest();

    expect(ran.filter((r) => r === "chart").length).toBeGreaterThan(0);
    expect(ran.indexOf("chart")).toBeLessThan(3);
  });
});

describe("several edits before the render finishes", () => {
  /** Renders whatever the slide says now, and remembers that it did — so a
   *  second render of the SAME state shows up as a repeat, and a render of a
   *  new state does not. */
  function chartProducer(log: string[], hold?: () => Promise<void>): Producer {
    const rendered = new Set<string>();
    return producer("chart", {
      fingerprint: (c) => `${c.slideId}|${c.chart.slide_title ?? ""}`,
      storedFingerprint: (c) => (rendered.has(c.fingerprint) ? c.fingerprint : null),
      run: async (c) => {
        if (hold) await hold();
        rendered.add(c.fingerprint);
        log.push(`${c.slideId}:${c.chart.slide_title ?? "-"}`);
      },
      onFailure: "abort",
    });
  }

  function edit(id: string, over: Partial<ChartSpec>) {
    slides.set(id, { ...(slides.get(id) as ChartSpec), ...over } as ChartSpec);
  }

  it("carries every field changed before its turn came in ONE render", async () => {
    const log: string[] = [];
    put("s1");
    put("s2");
    q.__setProducersForTest([chartProducer(log)]);
    q.__setConcurrencyForTest(1);
    q.enqueue("s1");
    // s2 waits behind s1, and two edits land on it before its turn.
    q.enqueue("s2");
    edit("s2", { slide_title: "one" } as Partial<ChartSpec>);
    q.enqueue("s2");
    edit("s2", { slide_title: "two" } as Partial<ChartSpec>);
    q.enqueue("s2");
    await q.__drainForTest();
    // Not one render per edit: the slide is queued once and reads the latest
    // state when it runs.
    expect(log).toEqual(["s1:-", "s2:two"]);
  });

  it("renders the last of a burst that lands mid-render, and settles", async () => {
    const log: string[] = [];
    put("s1");
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    let first = true;
    q.__setProducersForTest([
      chartProducer(log, async () => { if (first) { first = false; await gate; } }),
    ]);
    q.__setConcurrencyForTest(1);
    q.enqueue("s1");
    // Three keystrokes' worth of edits, each with its own enqueue, all while
    // the first render is in flight.
    for (const t of ["a", "ab", "abc"]) {
      edit("s1", { slide_title: t } as Partial<ChartSpec>);
      q.enqueue("s1");
    }
    release();
    await q.__drainForTest();
    expect(log[log.length - 1]).toBe("s1:abc");
    expect(q.isBusy()).toBe(false);
  });

  it("strands nothing when edits land across a whole deck being rendered", async () => {
    const log: string[] = [];
    for (let i = 1; i <= 8; i++) put(`s${i}`);
    q.__setProducersForTest([chartProducer(log)]);
    q.__setConcurrencyForTest(4);
    for (let i = 1; i <= 8; i++) q.enqueue(`s${i}`);
    for (let i = 1; i <= 8; i++) {
      edit(`s${i}`, { slide_title: `t${i}` } as Partial<ChartSpec>);
      q.enqueue(`s${i}`);
    }
    await q.__drainForTest();
    const s = q.snapshot();
    expect({ queued: s.queued, running: s.running, requeue: s.requeue, active: s.active })
      .toEqual({ queued: [], running: [], requeue: [], active: 0 });
    // Every slide ends up drawn at the title it finally has.
    for (let i = 1; i <= 8; i++) expect(log).toContain(`s${i}:t${i}`);
  });
});

describe("a transient outage must not leave a slide blank for ever", () => {
  // The reported fault: "sometimes the preview is not rendered at all".
  //
  // This is a TIMING failure, which is why it is written against the clock
  // rather than against a count of attempts. A 502 comes back in milliseconds,
  // so a slide's first attempt and its one retry both land inside the same few
  // seconds of downtime; the slide is then marked failed for that fingerprint,
  // and nothing re-queues on a fingerprint that has not moved, so it stays
  // blank until the author edits it or reopens the report.
  //
  // Staging shows the shape exactly: 116 failed renders inside 7 seconds,
  // 16-19 per second, where a healthy deck renders about one per second. The
  // backend was down for ~6s while it was redeployed; every request that
  // reached it before and after returned 200 (227/227).
  //
  // A fix that merely retries MORE times, still immediately, would satisfy a
  // count-based test and change nothing here: the attempts would still all be
  // spent inside the outage.
  const OUTAGE_MS = 6000;

  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("draws every slide of a deck once the outage ends", async () => {
    ["s1", "s2", "s3"].forEach((id) => put(id));
    const startedAt = Date.now();
    const attemptsAt: number[] = [];
    q.__setProducersForTest([
      producer("chart", {
        run: async () => {
          const elapsed = Date.now() - startedAt;
          attemptsAt.push(elapsed);
          // Exactly what the browser sees during a redeploy: nothing is
          // listening, so the proxy answers at once.
          if (elapsed < OUTAGE_MS) throw new ApiError(502, "502 Bad Gateway");
        },
      }),
    ]);

    ["s1", "s2", "s3"].forEach((id) => q.enqueue(id));
    // A minute of wall clock, with every timer and promise the queue schedules
    // allowed to run. Far longer than the outage: if the deck is ever going to
    // recover by itself, it has had every chance.
    await vi.advanceTimersByTimeAsync(60_000);

    expect(q.statusOf("s1").chart).toBe("done");
    expect(q.statusOf("s2").chart).toBe("done");
    expect(q.statusOf("s3").chart).toBe("done");
    // And it must have kept trying ACROSS the outage, not spent everything
    // inside it — the point of the whole fix.
    expect(Math.max(...attemptsAt)).toBeGreaterThanOrEqual(OUTAGE_MS);
  });

  it("gives up on a slide the server refuses to draw, rather than spinning", async () => {
    put("s1");
    let attempts = 0;
    q.__setProducersForTest([
      producer("chart", {
        run: async () => {
          attempts += 1;
          throw new ApiError(422, "this slide cannot be drawn");
        },
      }),
    ]);
    q.enqueue("s1");
    await vi.advanceTimersByTimeAsync(60_000);

    expect(q.statusOf("s1").chart).toBe("failed");
    // A 4xx says the request is wrong; repeating it is noise the author pays for.
    expect(attempts).toBeLessThanOrEqual(2);
  });
});

describe("a slide on screen with no picture must never stay that way", () => {
  // The customer's report, as stated: "the preview never gets visible in the
  // browser". Written as an INVARIANT rather than against a mechanism, because
  // we could not establish which path they hit — and the paths that lead here
  // are indistinguishable from outside:
  //
  //   * the queue decided there was nothing to do (a producer reported its work
  //     already stored, though nothing displayable exists)
  //   * the render failed earlier and the slide was left marked failed
  //   * the picture was cached under a fingerprint the component does not read
  //   * the cache entry was evicted while the queue believed it was still there
  //
  // All four end identically: a slide on screen, no picture, nothing happening,
  // and no warning. The component already reports exactly this through
  // `noteWanted(slideId, fingerprint, hasImage=false)` — the reader knows the
  // truth, since it is the thing that would display the image. Today that is
  // written to the trace and nothing acts on it, and the reader's own query is
  // `enabled: false`, so no other part of the system will ever fetch it either.

  it("renders a slide the queue believes needs nothing, when the screen says it is blank",
    async () => {
      put("s1");
      let runs = 0;
      // A producer that insists its work is already stored — the shape of every
      // path above. Enqueueing alone takes the "nothing-to-do" branch.
      q.__setProducersForTest([
        producer("chart", {
          fingerprint: () => "fp-1",
          storedFingerprint: () => "fp-1",
          run: async () => {
            runs += 1;
          },
        }),
      ]);
      q.enqueue("s1");
      await q.__drainForTest();
      expect(runs).toBe(0); // nothing to do, as the queue sees it

      // The component mounts, computes the same fingerprint, and finds no image.
      q.noteWanted("s1", "fp-1", false);
      await q.__drainForTest();

      expect(runs).toBeGreaterThan(0);
    });

  it("leaves a visible failure rather than a silent blank when it cannot draw it",
    async () => {
      // Retries are spaced now, so this one runs on the clock.
      vi.useFakeTimers();
      put("s1");
      q.__setProducersForTest([
        producer("chart", {
          fingerprint: () => "fp-1",
          storedFingerprint: () => "fp-1",
          run: async () => {
            throw new ApiError(500, "render is broken");
          },
          onFailure: "abort",
        }),
      ]);
      // The screen keeps saying it is blank; the queue keeps failing to fix it.
      for (let i = 0; i < 10; i += 1) {
        q.noteWanted("s1", "fp-1", false);
        await vi.advanceTimersByTimeAsync(60_000);
      }
      vi.useRealTimers();
      // Bounded — it must not keep asking for ever — and the author is told,
      // rather than being left looking at an empty slide with nothing to click.
      expect(q.statusOf("s1").chart).toBe("failed");
      expect(q.failuresOf("s1")).not.toHaveLength(0);
    });
});
