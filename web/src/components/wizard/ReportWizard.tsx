import { useQueryClient } from "@tanstack/react-query";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckIcon,
  ChevronLeftIcon,
  FileXIcon,
  LockIcon,
  Loader2Icon,
  PencilIcon,
  SaveIcon,
  XIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn, formatReportDate } from "@/lib/utils";
import { api, ApiError } from "@/lib/api";
import { classifyLockFailure } from "@/lib/reportLock";
import type { ChartSpec, Question, ReportDoc } from "@/lib/api";
import TemplateSelect from "@/components/TemplateSelect";
import {
  useReport,
  useUpdateReport,
  useRegroupedQuestions,
  useResolvedCase,
  useCaseTemplate,
  useTemplateActions,
  fetchChartPreviewInto,
  qk,
} from "@/lib/queries";
import * as previewQueue from "@/lib/previewQueue";
import { installProducers, setProducerEnv } from "@/lib/previewProducers";
import { useWorkspace } from "@/lib/workspace";
import {
  buildDemographicsGrids,
  buildSpecialPages,
  isSpecialSlide,
  isThemes,
  makeChart,
  makeComparisonSlide,
  makeSpecialSlide,
  newSlideId,
  normalizeSlots,
} from "@/lib/charts";
import StepSelect from "./StepSelect";
import StepConfigure from "./StepConfigure";
import StepDownload from "./StepDownload";
import { PAGE_TITLE, PANEL_TITLE } from "@/lib/surfaces";

/** Move an item within an array, returning a new array. */
function move<T>(arr: T[], from: number, to: number): T[] {
  if (to < 0 || to >= arr.length || from === to) return arr;
  const next = arr.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

/** Replace every chart belonging to a special-slide `group` (its anchor ref or
 *  any member tagged options.group === group) with `pages`, inserting
 *  `extraAfter` immediately after them. Returns null if the group is gone (the
 *  slide was removed mid-generation). */
function replaceSpecialGroup(
  charts: ChartSpec[],
  group: string,
  pages: ChartSpec[],
  extraAfter: ChartSpec[] = []
): ChartSpec[] | null {
  let inserted = false;
  const out: ChartSpec[] = [];
  for (const c of charts) {
    const inGroup = c.question_ref === group || c.options?.group === group;
    if (inGroup) {
      if (!inserted) {
        out.push(...pages, ...extraAfter);
        inserted = true;
      }
    } else {
      out.push(c);
    }
  }
  return inserted ? out : null;
}

const STEPS = [
  { id: "select", label: "Select" },
  { id: "configure", label: "Design" },
  { id: "download", label: "Preview" },
];

// Index of the Design step — the Preview grid jumps here when a slide is clicked.
const CONFIGURE_STEP = STEPS.findIndex((s) => s.id === "configure");

function Stepper({
  current,
  onJump,
  chartCount,
}: {
  current: number;
  onJump: (i: number) => void;
  chartCount: number;
}) {
  return (
    <div className="flex items-center">
      {STEPS.map((s, i) => {
        const done = i < current;
        const active = i === current;
        const future = i > current;
        // All steps reachable; Download (last step) requires at least one chart.
        const reachable = i < STEPS.length - 1 || chartCount > 0;
        return (
          <div key={s.id} className="flex items-center">
            <button
              disabled={!reachable}
              onClick={() => reachable && onJump(i)}
              className={cn(
                "flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
                reachable && "hover:bg-muted",
                !reachable && "cursor-default"
              )}
            >
              <span
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-medium tabular-nums transition-colors",
                  active && "bg-primary text-primary-foreground",
                  done && "bg-primary/15 text-primary",
                  future && "bg-muted text-muted-foreground"
                )}
              >
                {done ? <CheckIcon className="size-3.5" /> : i + 1}
              </span>
              <span
                className={cn(
                  "font-medium",
                  active && "text-foreground",
                  !active && "text-muted-foreground"
                )}
              >
                {s.label}
              </span>
            </button>
            {i < STEPS.length - 1 && (
              <div className="mx-1 h-px w-6 bg-border" />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function ReportWizard({
  caseId,
  reportId,
  materialId,
  onClose,
  onMissing,
}: {
  caseId: string;
  reportId: string;
  materialId: string;
  onClose: () => void;
  onMissing?: () => void;
}) {
  const { data: loaded, isLoading, isError } = useReport(caseId, reportId);
  // Which pohja this report renders with, and what it would inherit without a
  // choice of its own — so the dropdown names the one actually in use.
  const { data: resolvedCase } = useResolvedCase(caseId);
  const { data: caseTemplate } = useCaseTemplate(resolvedCase?.customer_id, caseId);
  const bindReport = useTemplateActions(resolvedCase?.customer_id).bindReport;
  const updateReport = useUpdateReport(caseId);
  const { workspace, renameReport } = useWorkspace(caseId);
  const createdAt = workspace.reports.find((r) => r.id === reportId)?.createdAt;
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");

  const [draft, setDraft] = useState<ReportDoc | null>(null);
  const [step, setStep] = useState(0);
  // Which slide the Design + Preview steps are focused on (source of truth here so
  // the Preview grid can click a slide and jump to Design showing it).
  const [active, setActive] = useState<string | null>(null);
  // Keep `active` valid as the deck changes: default to the first slide, and drop a
  // stale ref (its slide was removed or a group absorbed its variable).
  useEffect(() => {
    const cs = draft?.charts;
    if (!cs || cs.length === 0) return;
    if (!active || !cs.some((c) => c.slide_id === active)) {
      setActive(cs[0].slide_id ?? null);
    }
  }, [draft, active]);
  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  // Per-chart pending flags (keyed by question_ref) so the Configure preview
  // can show "Generating title…" / "Shortening labels…" placeholders over the
  // regions that are still being produced. Set true when a chart's AI call
  // starts, false when it resolves/fails.
  const [aiPending, setAiPending] = useState<
    Record<
      string,
      { titlePending: boolean; labelsPending: boolean; bulletsPending?: boolean }
    >
  >({});


  // Initialise the working draft once the report loads.
  useEffect(() => {
    if (loaded && !draft) {
      setDraft({
        name: loaded.name,
        render_mode: "image",
        template_ref: loaded.template_ref ?? "",
        // The backend deliberately leaves slide_id empty (backfilling there would
        // break its exact round-trip), so the EDITOR assigns one on load. Charts
        // written before slide_id existed get one here.
        charts: (loaded.charts ?? []).map((c) =>
          c.slide_id ? c : { ...c, slide_id: newSlideId() }
        ),
        grouping: loaded.grouping ?? { groups: [], singles: [] },
      });
    }
  }, [loaded, draft]);

  // What the server already holds, as we last sent or received it. A save is a
  // full-document PUT of a 60-chart report, so "did anything actually change?"
  // is worth answering before making the round trip.
  const savedPayload = useRef<string | null>(null);

  // The baseline for "has anything changed?": what the server just gave us,
  // normalised the way a save would send it. Without this the first save of a
  // session always goes through, even when the visit changed nothing.
  useEffect(() => {
    if (!draft || savedPayload.current !== null) return;
    savedPayload.current = JSON.stringify({
      ...draft,
      charts: normalizeSlots(draft.charts),
    });
  }, [draft]);

  // "Is this question in the report?" — ANY slide showing it counts, comparison
  // slides included. Counting only primaries left a question that has comparison
  // slides looking un-added, which emptied the Compare groups question list.
  const addedRefs = useMemo(
    () => new Set((draft?.charts ?? []).map((c) => c.question_ref)),
    [draft]
  );

  const mutate = useCallback(
    (fn: (d: ReportDoc) => ReportDoc) => {
      setDraft((prev) => {
        if (!prev) return prev;
        const next = fn(prev);
        // A pass that rebuilt the document without changing anything is not an
        // edit. `save()` checks the same thing again against what the server
        // holds; this just keeps the Save button's own state honest.
        if (next !== prev) setDirty(true);
        return next;
      });
    },
    []
  );

  // Drop charts whose question no longer exists (e.g. its variable was absorbed
  // into a group, or a group was split away) so Design never shows a dangling
  // ref like "var7" that errors on preview. Special slides (Overview/Conclusion/
  // Demographics) have no backing question ref, so they're always kept.
  const pruneToValidRefs = useCallback(
    (valid: Set<string>) => {
      mutate((d) => {
        // Keep anything whose ref is SYNTHETIC ("sp_…") as well as anything the
        // type registry recognises. A special slide whose type this build does not
        // know yet (a stale module after a hot reload) would otherwise be pruned
        // away the moment it is added, which looked like the slide "disappearing".
        const kept = d.charts.filter(
          (c) =>
            isSpecialSlide(c) ||
            c.question_ref.startsWith("sp_") ||
            valid.has(c.question_ref)
        );
        return kept.length === d.charts.length ? d : { ...d, charts: kept };
      });
    },
    [mutate]
  );

  // Rank each question by its position in the REGROUPED list — the exact order Select
  // shows — so a newly added slide lands where Select has it. Using the regrouped list
  // (not the base questions) means GROUPED questions (battery/multi/comparison) get a
  // rank too; keyed only by the base qids, their "battery-…" qid was undefined → Infinity
  // → the slide sorted to the BOTTOM in Design. (The user can still drag to reorder.)
  const { data: orderedQuestions } = useRegroupedQuestions(
    materialId,
    draft?.grouping ?? { groups: [], singles: [] }
  );
  const qRank = useMemo(() => {
    const m = new Map<string, number>();
    (orderedQuestions ?? []).forEach((q, i) => m.set(q.qid, i));
    return m;
  }, [orderedQuestions]);
  // Same regrouped list, keyed for titleDataKey: a battery/multi's synthetic
  // question can be renamed or re-scoped by a grouping edit without its qid
  // changing, so a title's data key needs the RESOLVED text/variables, not just
  // the stable question_ref.
  const questionByRef = useMemo(() => {
    const m = new Map<string, Question>();
    (orderedQuestions ?? []).forEach((q) => m.set(q.qid, q));
    return m;
  }, [orderedQuestions]);

  // Enabling/disabling a question directly edits the report: add its chart when
  // absent (inserted in SAV order), remove it when present (no separate "Add
  // selected" step).
  const toggleQuestion = useCallback(
    (q: Question) => {
      mutate((d) => {
        const exists = d.charts.some((c) => c.question_ref === q.qid);
        if (exists) {
          return {
            ...d,
            charts: normalizeSlots(
              // Unticking a question removes EVERY slide showing it, comparison
              // slides included. Sparing them orphans slides for a question the
              // list says is not in the report — and leaves the deck in a state
              // the user cannot get back out of from Step 1.
              d.charts.filter((c) => c.question_ref !== q.qid)
            ),
          };
        }
        // Insert the new chart in SAV order: after any front special slides and
        // earlier-ranked question slides, before higher-ranked ones and a
        // trailing conclusion slide.
        const newRank = qRank.get(q.qid) ?? Number.POSITIVE_INFINITY;
        const charts = [...d.charts];
        let pos = charts.length;
        for (let i = 0; i < charts.length; i++) {
          const c = charts[i];
          if (isSpecialSlide(c)) {
            if (c.chart_type === "special_conclusion") {
              pos = i;
              break;
            }
            continue; // front special slide → insert after it
          }
          const r = qRank.get(c.question_ref) ?? Number.POSITIVE_INFINITY;
          if (r > newRank) {
            pos = i;
            break;
          }
        }
        charts.splice(pos, 0, makeChart(q.qid, q.suggested_chart_type));
        return { ...d, charts: normalizeSlots(charts) };
      });
    },
    [mutate, qRank]
  );

  // Batch add/remove charts for many questions at once (Select-phase "Select all /
  // Deselect all"). One mutate so it's a single undo step and never toggles each ref.
  const selectMany = useCallback(
    (questions: Question[], select: boolean) => {
      const qids = new Set(questions.map((q) => q.qid));
      mutate((d) => {
        if (!select) {
          // Drop these questions' charts; special slides (overview/conclusion) stay.
          return {
            ...d,
            charts: normalizeSlots(
              d.charts.filter(
                (c) => isSpecialSlide(c) || !qids.has(c.question_ref)
              )
            ),
          };
        }
        const present = new Set(
          d.charts
            .filter((c) => !isSpecialSlide(c) && !c.compare_group)
            .map((c) => c.question_ref)
        );
        const additions = questions
          .filter((q) => !present.has(q.qid))
          .map((q) => makeChart(q.qid, q.suggested_chart_type));
        if (additions.length === 0) return d;
        // Rebuild: front special slides, then all question charts in SAV rank order,
        // then a trailing conclusion slide — matching single-toggle insertion.
        const front: ChartSpec[] = [];
        const conclusion: ChartSpec[] = [];
        const qCharts: ChartSpec[] = [];
        for (const c of d.charts) {
          if (isSpecialSlide(c)) {
            (c.chart_type === "special_conclusion" ? conclusion : front).push(c);
          } else qCharts.push(c);
        }
        const rank = (c: ChartSpec) =>
          qRank.get(c.question_ref) ?? Number.POSITIVE_INFINITY;
        const ordered = [...qCharts, ...additions].sort((a, b) => rank(a) - rank(b));
        return { ...d, charts: normalizeSlots([...front, ...ordered, ...conclusion]) };
      });
    },
    [mutate, qRank]
  );

  const updateChart = useCallback(
    (index: number, patch: Partial<ChartSpec>) => {
      mutate((d) => ({
        ...d,
        charts: d.charts.map((c, i) => (i === index ? { ...c, ...patch } : c)),
      }));
    },
    [mutate]
  );

  // Update ONE chart, found by its slide_id (indices can shift while async
  // AI work is in flight, so the auto-formatter addresses charts by id, not
  // position). question_ref is NOT unique enough for this: a "Compare
  // groups" slide shares its question_ref with the question's total-level
  // slide (see newSlideId's comment in lib/charts.ts), so matching on
  // question_ref here used to patch BOTH slides with whichever one's AI
  // title happened to resolve last.
  const updateChartById = useCallback(
    (slideId: string, patch: Partial<ChartSpec>) => {
      mutate((d) => ({
        ...d,
        charts: d.charts.map((c) =>
          c.slide_id === slideId ? { ...c, ...patch } : c
        ),
      }));
    },
    [mutate]
  );

  // Delete ONE slide by its position in the full chart list. Distinct from
  // unticking a question (which removes every slide showing it) — a question may
  // hold both a total-level slide and one split by another variable.
  const removeChart = useCallback(
    (index: number) => {
      mutate((d) => ({
        ...d,
        charts: normalizeSlots(d.charts.filter((_, i) => i !== index)),
      }));
    },
    [mutate]
  );

  // Tick/untick a slide that has no catalog row of its own (a special slide).
  // Unticking keeps the chart — and its bullets — and only leaves it out of the deck.
  const toggleChartExcluded = useCallback(
    (index: number) => {
      mutate((d) => ({
        ...d,
        charts: d.charts.map((c, i) =>
          i === index ? { ...c, excluded: !c.excluded } : c
        ),
      }));
    },
    [mutate]
  );

  // The deck as it will render: Design, the preview grid and the export all skip
  // slides that were unticked in Select.
  const includedCharts = useMemo(
    () => (draft?.charts ?? []).filter((c) => !c.excluded),
    [draft]
  );

  // Design is given the INCLUDED list, but its callbacks address charts by index
  // and the mutations run against the FULL draft. Without this translation,
  // excluding any slide makes Design edit and reorder the WRONG chart.
  const includedToFull = useMemo(() => {
    const out: number[] = [];
    (draft?.charts ?? []).forEach((c, i) => {
      if (!c.excluded) out.push(i);
    });
    return out;
  }, [draft]);

  const reorderCharts = useCallback(
    (from: number, to: number) => {
      mutate((d) => ({
        ...d,
        charts: normalizeSlots(move(d.charts, from, to)),
      }));
    },
    [mutate]
  );

  // Keep a ref to the latest draft for save() without stale closures.
  const draftRef = useRef<ReportDoc | null>(null);
  draftRef.current = draft;

  // ── The editing lock ─────────────────────────────────────────────────────
  // One person edits a report at a time. A save replaces the whole document,
  // so without this a second editor's save erases everything the first did —
  // including slides they never opened — and both saves succeed silently.
  //
  // Two different timeouts, for two different failures:
  //
  //   LIVENESS  the server expires a lock ~2 minutes after the editor stops
  //             checking in. This is for a crash, a closed laptop, a dropped
  //             network — none of which run any cleanup. It has to be short,
  //             or one crash strands a report.
  //
  //   INACTIVITY  this editor stops checking in after hours without a click or
  //             a keystroke. A renewal timer runs whether or not anyone is
  //             there, so without this a report left open in a tab is locked
  //             for ever: opened before lunch, still yours at five.
  //
  // Nothing is announced when a lock lapses. The tab keeps whatever is on
  // screen, and the truth is found out on the next interaction: if nobody took
  // the report, touching it takes the lock back silently; if somebody did, that
  // is when — and only when — the author is told.
  // Four hours in normal use. `?idleSeconds=N` shortens it so the behaviour can
  // actually be exercised — waiting four hours is not a test.
  // The server drops a lock nobody has renewed after this long
  // (Repository.LOCK_TTL_SECONDS). Past it we cannot claim to hold one.
  const LOCK_TTL_MS = 120_000;
  const INACTIVITY_LIMIT_MS =
    Number(new URLSearchParams(window.location.search).get("idleSeconds")) * 1000 ||
    4 * 60 * 60_000;

  // This editor's own identity. Two tabs of the SAME person both hold the
  // report, and closing one must not take it from the other — without this,
  // closing a second window released the lock outright and the remaining tab
  // only got it back on its next renewal, thirty seconds during which anyone
  // could have taken the report from someone who never left.
  const tabId = useRef(
    (globalThis.crypto?.randomUUID?.() ?? `tab-${Math.random().toString(36).slice(2)}`)
  );
  const [lockedBy, setLockedBy] = useState<string | null>(null);
  const [hasLock, setHasLock] = useState(false);
  //: Somebody else has it — stop asking, and stop letting interactions ask.
  const lostRef = useRef(false);
  const hasLockRef = useRef(false);
  hasLockRef.current = hasLock;
  //: When lock requests started failing for a reason that is NOT a refusal.
  //  Null whenever the last one succeeded.
  const unreachableSince = useRef<number | null>(null);
  const lastActivity = useRef(Date.now());

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;

    const release = () => void api.reports.unlock(caseId, reportId, tabId.current);

    /** Take or renew the lock. Returns whether we hold it. */
    const take = async (): Promise<boolean> => {
      try {
        await api.reports.lock(caseId, reportId, tabId.current);
        if (!alive) return false;
        unreachableSince.current = null;
        setHasLock(true);
        setLockedBy(null);
        return true;
      } catch (e) {
        if (!alive) return false;
        // Only a 409 is somebody else holding it. A network drop or a 500 is a
        // failure to FIND OUT, and treating those as a refusal closed the
        // editor and discarded whatever was on screen unsaved.
        if (classifyLockFailure(e) === "taken") {
          setHasLock(false);
          lostRef.current = true;
          setLockedBy(
            e instanceof Error ? e.message : "Someone else is editing this report."
          );
          return false;
        }
        // Keep the report open and keep asking. The server holds the lock for
        // us for a couple of minutes yet, and the next beat is in thirty
        // seconds; if it really was taken, that beat says so with a 409.
        unreachableSince.current ??= Date.now();
        return false;
      }
    };

    const beat = async () => {
      if (!alive) return;
      // Idle for hours: stop checking in and let the lock lapse on its own.
      // Deliberately NOT released — releasing would be a decision, and this is
      // an absence of one. If nobody wants the report, the next click here
      // takes it straight back.
      if (Date.now() - lastActivity.current > INACTIVITY_LIMIT_MS) {
        setHasLock(false);
        timer = window.setTimeout(beat, 60_000); // keep watching for a return
        return;
      }
      await take();
      // Long enough unable to renew and the server's own TTL has run out, so we
      // genuinely no longer hold it — say so, rather than showing an editing
      // badge for a lock we lost. Saving stays open: only a 409 refuses that.
      if (unreachableSince.current &&
          Date.now() - unreachableSince.current > LOCK_TTL_MS) {
        setHasLock(false);
      }
      timer = window.setTimeout(beat, 30_000);
    };

    void beat();

    // Any interaction is a claim on the report. When we already hold it this
    // only marks the tab as alive; when the lock has lapsed, it takes it back —
    // or discovers that somebody else now has it.
    let asking = false;
    const seen = () => {
      lastActivity.current = Date.now();
      // Ask once. Without this every keystroke fires its own request, so
      // returning to a report somebody took answers with a burst of 409s
      // instead of one.
      if (hasLockRef.current || asking || lostRef.current) return;
      asking = true;
      void take().finally(() => {
        asking = false;
      });
    };
    for (const ev of ["pointerdown", "keydown", "wheel"] as const) {
      window.addEventListener(ev, seen, { passive: true });
    }

    // Coming back to a backgrounded tab. Browsers throttle a hidden tab's
    // timers hard — Chrome stops running them altogether after a few minutes —
    // so the thirty-second renewal may not have fired for far longer than the
    // server's two-minute TTL, and the lock is gone without anything here
    // noticing. Renew the moment the tab is looked at again, rather than
    // waiting for the first click, by which time the author is already typing
    // into a report somebody else may now hold.
    const woke = () => {
      if (document.visibilityState !== "visible" || lostRef.current) return;
      lastActivity.current = Date.now();
      void take();
    };
    document.addEventListener("visibilitychange", woke);

    // Handing it back, because closing IS a decision: on unmount, and on the
    // tab going away — `pagehide` fires where `beforeunload` does not, and
    // `keepalive` lets the request outlive the page.
    window.addEventListener("pagehide", release);
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
      for (const ev of ["pointerdown", "keydown", "wheel"] as const) {
        window.removeEventListener(ev, seen);
      }
      document.removeEventListener("visibilitychange", woke);
      window.removeEventListener("pagehide", release);
      release();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, reportId]);

  // Someone else took the report while this tab sat idle. Say so, and go back
  // to the case — there is nothing useful to do here, and leaving an editor
  // open whose every save is refused only invites work that cannot be kept.
  useEffect(() => {
    if (lockedBy && draft) {
      toast.error(lockedBy);
      // Refresh the case's list on the way out, or it shows the report exactly
      // as it looked before — no lock, no holder — which contradicts what we
      // just told her and invites her to click straight back in.
      qcRef.current.invalidateQueries({ queryKey: qk.caseReports(caseId) });
      onClose();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lockedBy]);

  // ── The preview queue ────────────────────────────────────────────────────
  // One queue owns every kind of work a slide needs: its headline, its theme
  // bullets, and its picture — in that order, in one sequential pass per slide.
  // The wizard's only job here is to say how the queue reads the draft and
  // where its patches go; it never reaches into the queue, and the queue never
  // imports React.
  const qc = useQueryClient();
  const qcRef = useRef(qc);
  qcRef.current = qc;
  const questionByRefRef = useRef(questionByRef);
  questionByRefRef.current = questionByRef;

  // A new editing session: throw away the last one's statuses and patches. This
  // must NOT re-run when a callback identity changes, or it would wipe work in
  // progress — hence its own effect, keyed on the report alone.
  //
  // The cleanup matters as much as the setup: without it the queue carried on
  // rendering slides for a report nobody has open, spending model calls and
  // render time on them, and posting patches into a sink whose component is
  // gone. Closing the editor ends its work.
  useEffect(() => {
    installProducers();
    previewQueue.reset(reportId);
    return () => previewQueue.reset("");
  }, [reportId]);

  // The seams, re-registered whenever the callbacks they close over change.
  useEffect(() => {
    previewQueue.setSlideSource(
      (id) => draftRef.current?.charts.find((c) => c.slide_id === id) ?? null
    );
    previewQueue.setDeck((draftRef.current?.charts ?? []).map((c) => c.slide_id ?? ""));
    previewQueue.setPatchSink((id, patch) => updateChartById(id, patch));
  }, [reportId, updateChartById]);

  // The render context and the producers' environment change with the template
  // and the grouping, so they are refreshed rather than registered once.
  const groupingKey = JSON.stringify(draft?.grouping ?? {});
  useEffect(() => {
    const ctx = {
      templateRef: draft?.template_ref ?? "",
      reportId,
      groupingKey,
      renderTitle: false,
    };
    previewQueue.setRenderContext(ctx);
    setProducerEnv({
      materialId,
      questionFor: (ref) => questionByRefRef.current.get(ref),
      grouping: () => draftRef.current?.grouping,
      hasImage: (fingerprint) =>
        qc.getQueryData(["chart-preview", materialId, fingerprint]) !== undefined,
      // The fingerprint the QUEUE computed, not one recomputed from `ctx` —
      // which is captured here and is one statement stale the moment a template
      // change refills the queue and starts rendering synchronously.
      // Everything that identifies the picture comes from the queue's own
      // context, passed in — nothing is read from this closure, which is one
      // statement stale the moment a template change refills the queue.
      fetchImage: (chart, fingerprint, runCtx) =>
        fetchChartPreviewInto(qc, materialId, chart, fingerprint, {
          renderTitle: false,
          reportId: runCtx.reportId,
          grouping: draftRef.current?.grouping,
          templateRef: runCtx.templateRef,
        }),
    });
  }, [materialId, reportId, draft?.template_ref, groupingKey, qc]);

  // Warm the whole deck, and pick up slides added later. `enqueue` dedupes and
  // each producer decides for itself whether it is needed, so re-enqueueing a
  // settled deck costs nothing.
  // Every slide whose CONTENT changed goes back on the queue — not just slides
  // that were added. Watching the id list alone was not enough: editing a chart
  // type or a headline leaves the ids identical, and because components only
  // read the cache now, nothing would ever draw the new version. The author's
  // edit saved and the picture never moved.
  // The wizard tells the queue three things, and nothing else:
  //
  //   the deck      — which slides exist, so a context change can re-queue them
  //   the context   — the template and grouping every slide is drawn in
  //   what changed  — a slide whose own content the author edited
  //
  // A template change is NOT in that last category: it changes no chart. The
  // queue handles it in one place (see setRenderContext), which is what this
  // used to do here, badly, across an effect and a debounce.
  // Memoised on the charts themselves. It serialises the whole deck, and it was
  // being rebuilt on every render of this component — sixty specs stringified
  // per keystroke, per hover, per status tick — to produce the same string it
  // produced last time. The charts array changes identity exactly when a chart
  // changes, which is precisely when this should be recomputed.
  const charts = draft?.charts;
  const chartsSignature = useMemo(
    () => (charts ?? []).map((c) => `${c.slide_id ?? ""}=${JSON.stringify(c)}`)
      .join("\u0000"),
    [charts]
  );
  const resolvedCount = questionByRef.size;
  const lastSeen = useRef<Map<string, string>>(new Map());
  useEffect(() => {
    // Not before the questions have resolved. A headline is written ABOUT the
    // question as the current grouping resolves it, so starting earlier means
    // the first few slides — exactly as many as the queue runs at once — find
    // nothing to write about and are recorded as needing nothing. That is how
    // the first four slides of a sixty-slide report came out untitled.
    if (!resolvedCount) return;
    // Debounced, so holding a key down does not queue a render per keystroke.
    const h = setTimeout(() => {
      const charts = draftRef.current?.charts ?? [];
      previewQueue.setDeck(charts.map((c) => c.slide_id ?? ""));
      const next = new Map<string, string>();
      for (const c of charts) {
        if (c.slide_id) next.set(c.slide_id, JSON.stringify(c));
      }
      for (const [id, sig] of next) {
        if (lastSeen.current.get(id) !== sig) previewQueue.enqueue(id);
      }
      lastSeen.current = next;
    }, 350);
    return () => clearTimeout(h);
  }, [chartsSignature, resolvedCount]);

  // "Is the queue doing anything?" — the one signal the save rule needs.
  const queueBusy = useSyncExternalStore(previewQueue.subscribe, previewQueue.isBusy);

  const save = useCallback(async (): Promise<boolean> => {
    const d = draftRef.current;
    if (!d) return false;
    // Do not write into somebody else's report. This is only about the case we
    // have been TOLD about (409): it keeps an autosave from firing every 1.5s
    // to no purpose, and lets the banner do the telling instead of a toast.
    // A lock we merely could not confirm is not a reason to withhold a save —
    // the server is the authority and refuses if it must, and refusing to
    // write here would strand the author's work in the tab.
    if (lostRef.current) return false;
    const payload: ReportDoc = { ...d, charts: normalizeSlots(d.charts) };
    const serialized = JSON.stringify(payload);
    if (serialized === savedPayload.current) {
      // Nothing to write. Passes that touch every chart — pruning refs, the AI
      // title batch, auto-formatting — mark the draft dirty even when they
      // produce the values already there, and leaving the step then wrote the
      // document back unchanged.
      setDirty(false);
      return true;
    }
    try {
      await updateReport.mutateAsync({ reportId, report: payload });
      savedPayload.current = serialized;
      setDirty(false);
      setSavedAt(Date.now());
      return true;
    } catch (e) {
      // A refused save is the other way we learn the report changed hands —
      // and the only one when the lock beat is what is failing.
      if (e instanceof ApiError && e.status === 409) {
        lostRef.current = true;
        setHasLock(false);
        setLockedBy(e.message);
        return false;
      }
      toast.error(
        `Save failed: ${e instanceof Error ? e.message : "unknown error"}`
      );
      return false;
    }
  }, [updateReport, reportId]);

  // Persist unsaved edits if the report is closed (e.g. via the top-bar close)
  // without going through a commit-then-navigate path. Refs keep the unmount
  // cleanup stable so it runs only on unmount.
  const saveRef = useRef(save);
  saveRef.current = save;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  // When the current run of unsaved changes began — the clock the cap above
  // reads. Cleared whenever the draft is clean again.
  const dirtySince = useRef<number | null>(null);
  if (!dirty) dirtySince.current = null;
  else if (dirtySince.current === null) dirtySince.current = Date.now();
  useEffect(() => {
    return () => {
      if (dirtyRef.current) void saveRef.current();
    };
  }, []);

  // Autosave: a browser reload does NOT run the unmount cleanup above, so every
  // edit made since the last manual Save used to be thrown away by a refresh —
  // an added special slide, a retyped title, a changed chart type. Save shortly
  // after the edits settle instead. The Save button stays (it also commits
  // immediately); `dirty` still drives the Save button's state, so it goes
  // back to "Saved" on its own once the autosave lands.
  const AUTOSAVE_DELAY_MS = 1500;
  const MAX_AI_SAVE_HOLD_MS = 90_000;
  useEffect(() => {
    // Hold off entirely while the queue is still producing. It lands 60 titles
    // and 60 renders over about a minute, in bursts with pauses between them,
    // and each pause longer than the delay above used to be its own save: 17
    // writes of a 60-chart document during the exact minute the author is
    // trying to click something. Waiting for the queue to go idle turns the
    // whole generation phase into ONE save — the effect re-runs when it clears, with the draft still
    // dirty, and saves then. Nothing is at risk in the meantime: closing the
    // report saves through the unmount cleanup above, and a producer that fails
    // still leaves the queue idle.
    //
    // The wait is CAPPED. Suppressing a save is only ever a courtesy to the
    // generation phase; if a pending flag were somehow stranded, an uncapped
    // gate would mean the author's typing is never written at all — a far worse
    // bug than the one it fixes. After MAX_AI_SAVE_HOLD_MS of being dirty we
    // save regardless of what the AI passes think they are still doing.
    const held = dirtySince.current !== null
      && Date.now() - dirtySince.current > MAX_AI_SAVE_HOLD_MS;
    if (!dirty || (queueBusy && !held)) return;
    const h = setTimeout(() => {
      if (dirtyRef.current) void saveRef.current();
    }, AUTOSAVE_DELAY_MS);
    return () => clearTimeout(h);
  }, [dirty, draft, queueBusy]);

  // Slide titles, theme bullets and the rendered picture are ALL produced by
  // the preview queue registered above — one sequential pass per slide, in
  // that order. The wizard used to run its own bounded-concurrency title
  // queue here, independent of the render queue, which is why a slide
  // rendered once without its headline and then again with it.

  // ── Special (non-chart) slides: Overview / Conclusion / Demographics ──────
  const SPECIAL_HEADINGS: Record<string, string> = {
    special_overview: "Study background",
    special_conclusion: "Conclusions",
    special_demographics: "Respondents",
    // Blank: placeholder heading. An entirely empty slide renders as a blank
    // cream page and reads as "nothing was added" — give the author something
    // visible to overwrite.
    special_blank: "Title",
  };
  const errMsg = (e: unknown) => (e instanceof Error ? e.message : "unknown error");
  const reportQuestionRefs = useCallback(
    () =>
      (draftRef.current?.charts ?? [])
        .filter((c) => !isSpecialSlide(c))
        .map((c) => c.question_ref),
    []
  );
  const setBulletsPending = useCallback((ref: string, pending: boolean) => {
    setAiPending((prev) => ({
      ...prev,
      [ref]: {
        titlePending: prev[ref]?.titlePending ?? false,
        labelsPending: prev[ref]?.labelsPending ?? false,
        bulletsPending: pending,
      },
    }));
  }, []);
  const fetchBullets = useCallback(
    async (type: string, refs: string[]): Promise<string[]> => {
      if (type === "special_overview")
        return (await api.materials.aiOverview(materialId, { question_refs: refs })).bullets;
      return (await api.materials.aiConclusion(materialId, { question_refs: refs })).bullets;
    },
    [materialId]
  );

  // Lay out generated bullets across one-or-more pages (the first page keeps the
  // group's anchor ref so the current selection stays valid), replacing any
  // existing pages of this special-slide `group`. `extraAfter` (demographic
  // charts) is inserted right after the pages.
  const applySpecialPages = useCallback(
    (
      group: string,
      type: string,
      heading: string,
      bullets: string[],
      extraAfter: ChartSpec[] = []
    ) => {
      mutate((d) => {
        const pages = buildSpecialPages(type, heading, bullets, group).map((p, i) =>
          i === 0 ? { ...p, question_ref: group } : p
        );
        const next = replaceSpecialGroup(d.charts, group, pages, extraAfter);
        return next ? { ...d, charts: normalizeSlots(next) } : d;
      });
    },
    [mutate]
  );

  // Demographics: a (possibly multi-page) facts slide followed by demographics
  // grid slides (several compact charts per page). Replaces the whole group.
  const applyDemographics = useCallback(
    (
      group: string,
      heading: string,
      bullets: string[],
      cells: { question_ref: string; chart_type: string }[]
    ) => {
      mutate((d) => {
        const factPages = buildSpecialPages(
          "special_demographics",
          heading,
          bullets,
          group
        ).map((p, i) => (i === 0 ? { ...p, question_ref: group } : p));
        const gridPages = buildDemographicsGrids(cells ?? [], group);
        const next = replaceSpecialGroup(d.charts, group, [...factPages, ...gridPages]);
        return next ? { ...d, charts: normalizeSlots(next) } : d;
      });
    },
    [mutate]
  );

  // Add a special slide (synchronously, returning its anchor ref so the caller
  // can select it) and generate its bullets in the background — spanning pages
  // when the content overflows one slide.
  // Generate a "Compare groups" section: one slide per chosen question, split by
  // `classifyingVar`. APPENDED after the last slide — a comparison section is a
  // closing section, and addSpecialSlide's front-of-deck placement would bury the
  // report's opening. (spec 2026-08-02-compare-groups-section §1)
  const addComparisonSection = useCallback(
    (classifyingVar: string, qids: string[]) => {
      mutate((d) => {
        // Source each new slide from the question's PRIMARY chart so it inherits
        // the author's chart type, label overrides and formatting.
        const primary = new Map(
          d.charts.filter((c) => !c.compare_group).map((c) => [c.question_ref, c])
        );
        const made = qids
          .map((qid) => primary.get(qid))
          .filter((c): c is ChartSpec => !!c)
          .map((c) => makeComparisonSlide(c, classifyingVar));
        if (made.length === 0) return d;
        return { ...d, charts: normalizeSlots([...d.charts, ...made]) };
      });
    },
    [mutate]
  );

  const addSpecialSlide = useCallback(
    (type: string, afterRef?: string | null): string => {
      const heading = SPECIAL_HEADINGS[type];
      const placeholder = makeSpecialSlide(type, {
        slide_title: heading,
        // A blank slide is never filled in by AI, so it needs starter content or
        // it renders empty. Markdown: "*" starts a bullet, two spaces nest one.
        ...(type === "special_blank"
          ? { bullets: ["* Write your content here", "  * An indented sub-point"] }
          : {}),
      });
      const group = placeholder.question_ref;
      const anchor = {
        ...placeholder,
        options: { ...placeholder.options, group },
      };
      // Insert right AFTER the active slide (so it lands where you're working);
      // with no active slide, go to the front of the deck.
      mutate((d) => {
        const charts = [...d.charts];
        const at = afterRef
          ? charts.findIndex((c) => c.question_ref === afterRef)
          : -1;
        if (at >= 0) charts.splice(at + 1, 0, anchor);
        else charts.unshift(anchor);
        return { ...d, charts: normalizeSlots(charts) };
      });
      // An empty slide is AUTHOR-written: no AI call, nothing pending. Firing one
      // would also spend quota on a slide whose whole point is to be hand-written.
      if (type === "special_blank") return group;
      setBulletsPending(group, true);
      void (async () => {
        try {
          if (type === "special_demographics") {
            const { bullets, charts } = await api.materials.aiDemographics(
              materialId,
              { question_refs: reportQuestionRefs() }
            );
            applyDemographics(group, heading, bullets, charts);
          } else {
            const bullets = await fetchBullets(type, reportQuestionRefs());
            applySpecialPages(group, type, heading, bullets);
          }
        } catch (e) {
          toast.error(`Could not generate slide: ${errMsg(e)}`);
        } finally {
          setBulletsPending(group, false);
        }
      })();
      return group;
    },
    [materialId, mutate, reportQuestionRefs, fetchBullets, setBulletsPending, applySpecialPages]
  );

  // Regenerate a special slide's bullets, re-paginating its whole page group.
  const regenerateSpecial = useCallback(
    async (chart: ChartSpec) => {
      const type = chart.chart_type;
      // Themes charts (open-ended) just refresh their bullets in place.
      if (isThemes(chart)) {
        const ref = chart.question_ref;
        const slideId = chart.slide_id ?? ref;
        setBulletsPending(slideId, true);
        try {
          const { bullets } = await api.materials.aiThemes(materialId, {
            question_ref: ref,
          });
          updateChartById(slideId, { options: { ...(chart.options ?? {}), bullets } });
        } catch (e) {
          toast.error(`Could not regenerate themes: ${errMsg(e)}`);
        } finally {
          setBulletsPending(slideId, false);
        }
        return;
      }
      const group =
        (typeof chart.options?.group === "string" ? chart.options.group : null) ??
        chart.question_ref;
      const heading = (chart.slide_title || SPECIAL_HEADINGS[type] || "").replace(
        /\s*\(\d+\/\d+\)\s*$/,
        ""
      );
      setBulletsPending(group, true);
      try {
        if (type === "special_demographics") {
          const { bullets, charts } = await api.materials.aiDemographics(
            materialId,
            { question_refs: reportQuestionRefs() }
          );
          applyDemographics(group, heading, bullets, charts);
        } else {
          const bullets = await fetchBullets(type, reportQuestionRefs());
          applySpecialPages(group, type, heading, bullets);
        }
      } catch (e) {
        toast.error(`Could not regenerate slide: ${errMsg(e)}`);
      } finally {
        setBulletsPending(group, false);
      }
    },
    [
      materialId,
      reportQuestionRefs,
      fetchBullets,
      setBulletsPending,
      applySpecialPages,
      updateChartById,
    ]
  );

  // Moving between steps does NOT save.
  //
  // It used to: every transition awaited a full-document PUT first, so clicking
  // "Preview" on a 60-chart report sat there doing nothing an author could see
  // until the write came back — the phase buttons felt broken, which is exactly
  // what they were told. Nothing is at risk in dropping it: the wizard stays
  // mounted across steps, so the draft is still there; autosave persists edits
  // 1.5s after they settle; closing the report saves on unmount; and the one
  // place that genuinely needs the SERVER's copy to be current — generating the
  // deck, which the backend builds from the stored report — saves for itself
  // before rendering (see StepDownload's handleGenerate).
  function goNext() {
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  }

  function goPrev() {
    setStep((s) => Math.max(0, s - 1));
  }

  // Inline report rename: update the draft (persisted on save), the workspace
  // listing, and flush to the backend.
  function commitName() {
    const next = nameDraft.trim();
    setEditingName(false);
    if (!next || next === draft?.name) return;
    mutate((d) => ({ ...d, name: next }));
    renameReport(reportId, next);
  }

  // Self-heal a stale/deleted report id out of the workspace, once.
  const missingFired = useRef(false);
  useEffect(() => {
    if (isError && !missingFired.current) {
      missingFired.current = true;
      onMissing?.();
    }
  }, [isError, onMissing]);

  // Stale report id (404 after a backend restart / deletion elsewhere): show
  // an escapable error panel instead of trapping the user on a spinner.
  // Somebody else had it when we arrived. The list normally stops you before
  // this, so reaching here means they took it in the moment between — say so
  // and go back, rather than showing an editor whose saves would be refused.
  //
  // Only when we never got in. Losing the lock LATER shows a banner instead
  // (see below): replacing a screen that holds unsaved work with an apology
  // is how you turn a lock into data loss.
  if (lockedBy && !draft) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-muted">
          <LockIcon className="size-7 text-muted-foreground" />
        </div>
        <h3 className={PANEL_TITLE}>Someone else is editing this report</h3>
        <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">
          {lockedBy} It opens again when they close it — or shortly after, if
          they simply walked away.
        </p>
        <Button variant="outline" className="mt-5" onClick={onClose}>
          <ChevronLeftIcon className="size-4" />
          Back to reports
        </Button>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-muted">
          <FileXIcon className="size-7 text-muted-foreground" />
        </div>
        <h3 className={PANEL_TITLE}>
          Report unavailable
        </h3>
        <p className="mt-2 max-w-xs text-sm leading-relaxed text-muted-foreground">
          This report couldn't be loaded. It may have been removed.
        </p>
        <Button variant="outline" className="mt-5" onClick={onClose}>
          <ChevronLeftIcon className="size-4" />
          Back to reports
        </Button>
      </div>
    );
  }

  if (isLoading || !draft) {
    return (
      <div className="flex items-center justify-center py-32 text-muted-foreground">
        <Loader2Icon className="size-5 animate-spin" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-5 flex items-center justify-between gap-4">
        <div className="min-w-0">
          {editingName ? (
            <div className="flex items-center gap-2">
              <Input
                autoFocus
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitName();
                  if (e.key === "Escape") setEditingName(false);
                }}
                className="max-w-sm text-base font-semibold"
              />
              <Button variant="outline" size="icon" onClick={commitName}>
                <CheckIcon className="size-4" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                onClick={() => setEditingName(false)}
              >
                <XIcon className="size-4" />
              </Button>
            </div>
          ) : (
            <div className="group flex items-center gap-2">
              <h1 className={`${PAGE_TITLE} truncate`}>{draft.name}</h1>
              <Button
                size="icon-sm"
                variant="ghost"
                className="text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
                onClick={() => {
                  setNameDraft(draft.name);
                  setEditingName(true);
                }}
                title="Rename report"
              >
                <PencilIcon className="size-4" />
              </Button>
            </div>
          )}
          {formatReportDate(createdAt) && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              Created {formatReportDate(createdAt)}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {/* Left of Save: which pohja this report comes out on. Visible on
              every step, because it changes what Design previews AND what the
              export produces. */}
          <TemplateSelect
            customerId={resolvedCase?.customer_id}
            value={draft?.template_ref ?? ""}
            inheritedId={caseTemplate?.template_id}
            onChange={(templateId) => {
              bindReport.mutate({ caseId, reportId, templateId });
              // Kept in the draft too: the deck is built from the report's own
              // template_ref, and the Design previews read it from there.
              mutate((d) => ({ ...d, template_ref: templateId ?? "" }));
            }}
          />
          {/* The button IS the status. "Unsaved changes" and "Saved" used to sit
              beside it as their own text, which put three things in a row that
              all said something about saving. The word changes, the icon
              changes and the colour changes; the SIZE does not. The width is
              pinned because the label cycles Save -> Saving -> Saved, and left
              to itself the button would twitch narrower and wider on every
              save — with the toolbar's whole right edge moving with it. */}
          <Button
            variant="outline"
            size="sm"
            onClick={save}
            disabled={updateReport.isPending || (!dirty && !!savedAt)}
            className={
              // w-24 clears "Saving" plus its spinner, the widest state.
              "w-24 " +
              (!dirty && savedAt
                ? "border-emerald-600/40 text-emerald-600 disabled:opacity-100"
                : "")
            }
            title={
              dirty
                ? "Unsaved changes"
                : savedAt
                  ? `Saved ${formatReportDate(new Date(savedAt).toISOString()) ?? ""}`.trim()
                  : "Save"
            }
          >
            {updateReport.isPending ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : !dirty && savedAt ? (
              <CheckIcon className="size-4" />
            ) : (
              <SaveIcon className="size-4" />
            )}
            {updateReport.isPending ? "Saving" : !dirty && savedAt ? "Saved" : "Save"}
          </Button>
        </div>
      </div>

      {/* Stepper + prev/next nav, with the phase instruction centered below */}
      <div className="mb-6 rounded-xl border bg-card px-3 py-2">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0"
            onClick={goPrev}
            disabled={step === 0}
          >
            <ArrowLeftIcon className="size-4" />
            Prev
          </Button>
          <div className="flex flex-1 justify-center">
            <Stepper
              current={step}
              onJump={(i) => setStep(i)}
              chartCount={draft.charts.length}
            />
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0"
            onClick={goNext}
            disabled={step >= STEPS.length - 1}
          >
            Next
            <ArrowRightIcon className="size-4" />
          </Button>
        </div>
      </div>

      {/* Step body */}
      <div className="min-h-[400px]">
        {step === 0 && (
          <StepSelect
            materialId={materialId}
            charts={draft.charts}
            addedRefs={addedRefs}
            onToggle={toggleQuestion}
            onSelectMany={selectMany}
            onAddSpecial={addSpecialSlide}
            onAddComparison={addComparisonSection}
            onToggleExcluded={toggleChartExcluded}
            onRemoveChart={removeChart}
            grouping={draft.grouping ?? { groups: [], singles: [] }}
            onGroupingChange={(g) => mutate((d) => ({ ...d, grouping: g }))}
            onPruneRefs={pruneToValidRefs}
          />
        )}
        {step === 1 && (
          <StepConfigure
            materialId={materialId}
            reportId={reportId}
            templateRef={draft.template_ref}
            charts={includedCharts}
            grouping={draft.grouping ?? { groups: [], singles: [] }}
            aiPending={aiPending}
            active={active}
            setActive={setActive}
            onReorder={(from, to) =>
              reorderCharts(includedToFull[from] ?? from, includedToFull[to] ?? to)
            }
            onUpdateChart={(i, patch) => updateChart(includedToFull[i] ?? i, patch)}
            onRegenerateSpecial={regenerateSpecial}
          />
        )}
        {step === 2 && (
          <StepDownload
            caseId={caseId}
            reportId={reportId}
            materialId={materialId}
            draft={draft}
            active={active}
            setActive={setActive}
            onGoToDesign={() => setStep(CONFIGURE_STEP)}
            save={save}
          />
        )}
      </div>
    </div>
  );
}
