import { useEffect, useMemo, useRef, useState } from "react";
import { CheckIcon, CheckCheckIcon, SearchIcon, AlertCircleIcon, Layers2Icon, BarChart3Icon, XIcon, MoreVerticalIcon, InfoIcon, GripVerticalIcon, Trash2Icon, PlusIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { Question, GroupingOverride, BatterySuggestion, ChartSpec } from "@/lib/api";
import { useRegroupedQuestions, useBatterySuggestions } from "@/lib/queries";
import { useDragReorder } from "@/lib/useDragReorder";
import { isSpecialSlide, slideSubtitle } from "@/lib/charts";
import ManageGroupingDialog from "@/components/ManageGroupingDialog";
import QuestionDetailsDialog from "@/components/QuestionDetailsDialog";
import { AddSpecialDialog } from "@/components/wizard/AddSpecialDialog";
import { slideTitle } from "@/components/wizard/SlideNavigator";

// ── The report's deck: its slides in order, drag-reorderable + removable ──────
// This is the report's OWN ordering (the charts array). Reordering/removing here
// touches only this report — never the material's canonical question order.
function DeckList({
  charts,
  questionMap,
  onReorder,
  onRemove,
  onInfo,
  highlightQids,
  highlightRef,
}: {
  charts: ChartSpec[];
  questionMap: Map<string, Question>;
  onReorder: (from: number, to: number) => void;
  onRemove: (index: number) => void;
  onInfo: (chart: ChartSpec) => void;
  // Newly-created group (battery/multi) qids to flash after grouping, and a ref on
  // the flashed row so it scrolls into view.
  highlightQids: Set<string>;
  highlightRef: React.RefObject<HTMLDivElement | null>;
}) {
  const { dragIndex, overIndex, containerRef, itemProps } = useDragReorder(onReorder);
  return (
    <div ref={containerRef as React.RefObject<HTMLDivElement>} className="space-y-1.5">
      {charts.map((c, i) => {
        const special = isSpecialSlide(c);
        const justCreated = highlightQids.has(c.question_ref);
        const subtitle = slideSubtitle(c, questionMap);
        return (
          <div
            key={`${c.question_ref}-${i}`}
            ref={justCreated ? highlightRef : undefined}
            {...itemProps(i)}
            className={cn(
              "group flex items-center gap-2 rounded-lg border bg-card py-2 pr-2 pl-1.5 transition-colors",
              justCreated && "border-primary bg-primary/10 ring-2 ring-primary",
              dragIndex === i && "opacity-40",
              dragIndex !== null && overIndex === i && dragIndex !== i && "ring-2 ring-primary"
            )}
          >
            <span
              className="shrink-0 cursor-grab text-muted-foreground/50 hover:text-muted-foreground"
              title="Drag to reorder — affects this report only"
            >
              <GripVerticalIcon className="size-4" />
            </span>
            <span className="w-5 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
              {i + 1}
            </span>
            <span className="min-w-0 flex-1">
              <span className="line-clamp-1 text-sm">{slideTitle(c, questionMap)}</span>
              <span className="mt-0.5 block text-xs text-muted-foreground">
                {subtitle}
              </span>
            </span>
            {/* Special slides also get an explicit delete (bin) as the leftmost
                action — they aren't re-addable from the pool below like questions. */}
            {special && (
              <button
                type="button"
                title="Delete this special slide"
                onClick={() => onRemove(i)}
                className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
              >
                <Trash2Icon className="size-4" />
              </button>
            )}
            {/* Every deck row — question OR special — carries the same controls:
                details (info) and a selected-checkbox that deselects/removes it. */}
            <button
              type="button"
              title={special ? "Slide details" : "Question details"}
              onClick={() => onInfo(c)}
              className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <InfoIcon className="size-4" />
            </button>
            <button
              type="button"
              title="Selected — click to remove from this report"
              onClick={() => onRemove(i)}
              className="flex size-7 shrink-0 items-center justify-center"
            >
              <span className="flex size-5 items-center justify-center rounded-md border border-primary bg-primary text-primary-foreground">
                <CheckIcon className="size-3.5" />
              </span>
            </button>
          </div>
        );
      })}
    </div>
  );
}

// Human labels for the special-slide types (for the deck-row info dialog).
const SPECIAL_KIND: Record<string, string> = {
  special_overview: "Overview",
  special_conclusion: "Conclusion",
  special_demographics: "Demographics",
};

// Lightweight details for a special (non-question) slide — special slides have no
// backing question, so QuestionDetailsDialog doesn't apply.
function SpecialSlideInfoDialog({
  chart,
  questionMap,
  onOpenChange,
}: {
  chart: ChartSpec | null;
  questionMap: Map<string, Question>;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={!!chart} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-left text-base leading-snug">
            {chart ? slideTitle(chart, questionMap) : ""}
          </DialogTitle>
          <DialogDescription className="text-left">
            {chart ? (SPECIAL_KIND[chart.chart_type] ?? "Special slide") : ""}
          </DialogDescription>
        </DialogHeader>
        <p className="text-sm leading-relaxed text-muted-foreground">
          A special slide. Its heading and bullet content are generated by AI and
          edited in the <span className="font-medium">Design</span> step. Use the
          checkbox to remove it from this report, or drag to reorder.
        </p>
      </DialogContent>
    </Dialog>
  );
}

// A question whose only compatible chart type is the word cloud (an open-ended
// free-text question). It's chartable — just rendered as a cloud, not a bar.
function isWordcloudOnly(q: Question): boolean {
  return (
    q.compatible_chart_types?.length === 1 &&
    q.compatible_chart_types[0] === "wordcloud"
  );
}

function KindBadge({ q }: { q: Question }) {
  if (q.kind === "battery") {
    return (
      <Badge variant="secondary" className="whitespace-nowrap border-violet-200 bg-violet-50 font-normal text-violet-700">
        Battery · {q.variables.length}
      </Badge>
    );
  }
  if (q.kind === "multi") {
    return (
      <Badge variant="secondary" className="whitespace-nowrap font-normal">
        Multi · {q.variables.length}
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="whitespace-nowrap font-normal">
      Single
    </Badge>
  );
}

export default function StepSelect({
  materialId,
  charts,
  addedRefs,
  onToggle,
  onSelectMany,
  onReorder,
  onRemoveChart,
  onAddSpecial,
  grouping,
  onGroupingChange,
  onPruneRefs,
}: {
  materialId: string;
  // The report's slides, in order — the deck this step arranges.
  charts: ChartSpec[];
  addedRefs: Set<string>;
  onToggle: (question: Question) => void;
  onSelectMany: (questions: Question[], select: boolean) => void;
  // Deck operations — all affect only this report, never the material.
  onReorder: (from: number, to: number) => void;
  onRemoveChart: (index: number) => void;
  onAddSpecial: (type: string, afterRef?: string | null) => string | void;
  grouping: GroupingOverride;
  onGroupingChange: (override: GroupingOverride) => void;
  onPruneRefs: (validQids: Set<string>) => void;
}) {
  const { data: questions, isLoading, isError } = useRegroupedQuestions(
    materialId,
    grouping
  );
  const { data: suggestions } = useBatterySuggestions(materialId, grouping);
  const [search, setSearch] = useState("");
  const [groupingOpen, setGroupingOpen] = useState(false);
  // When the dialog is opened from a suggestion, these variables are pre-selected in it so
  // the user reviews the selection and groups it themselves ([] = open on current grouping).
  const [dialogSelection, setDialogSelection] = useState<string[]>([]);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  // Per-row "⋮" menu: which row's menu is open, and which question's details dialog to show.
  const [menuQid, setMenuQid] = useState<string | null>(null);
  const [detailQid, setDetailQid] = useState<string | null>(null);
  const [specialInfoChart, setSpecialInfoChart] = useState<ChartSpec | null>(null);
  const [addSpecialOpen, setAddSpecialOpen] = useState(false);

  // Close the open row menu on any click outside a menu (the trigger + menu carry
  // data-rowmenu, so clicking the trigger just toggles — no close-then-reopen flicker).
  useEffect(() => {
    if (!menuQid) return;
    const onDown = (e: MouseEvent) => {
      if (!(e.target as Element).closest("[data-rowmenu]")) setMenuQid(null);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menuQid]);

  const sKey = (vars: string[]) => [...vars].sort().join(",");
  const activeSuggestions = (suggestions ?? []).filter(
    (s) => !dismissed.has(sKey(s.variables))
  );

  function groupAsBattery(s: BatterySuggestion) {
    // Open the grouping dialog with the suggested variables PRE-SELECTED — the user sees
    // them highlighted and clicks "Group as battery" to create it (nothing auto-groups).
    setDialogSelection([...s.variables]);
    setGroupingOpen(true);
  }

  // Auto-select a newly-created group: when the reshaped list gains a group
  // question that wasn't there before (i.e. the user just grouped some
  // variables), add it to the report by default. Skips the first load so
  // opening a report doesn't add everything.
  const prevQids = useRef<Set<string> | null>(null);
  // Newly-created group qids — briefly highlighted in the list so the user sees what the
  // grouping produced when they return from the dialog.
  const [highlightQids, setHighlightQids] = useState<Set<string>>(new Set());
  const highlightRef = useRef<HTMLDivElement | null>(null);
  // Scroll the highlighted new group into view so the flash is actually visible.
  useEffect(() => {
    if (highlightQids.size === 0) return;
    const h = setTimeout(
      () => highlightRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }),
      120
    );
    return () => clearTimeout(h);
  }, [highlightQids]);
  useEffect(() => {
    if (!questions) return;
    const current = new Set(questions.map((q) => q.qid));
    if (prevQids.current) {
      const newGroups: string[] = [];
      for (const q of questions) {
        const isGroup = q.kind === "multi" || q.kind === "battery";
        if (isGroup && !prevQids.current.has(q.qid)) {
          newGroups.push(q.qid);
          if (!addedRefs.has(q.qid)) onToggle(q);
        }
      }
      if (newGroups.length) setHighlightQids(new Set(newGroups));
    }
    // Drop any chart whose question no longer exists (its variable was absorbed
    // into a group, or a group was split away).
    if ([...addedRefs].some((ref) => !current.has(ref))) {
      onPruneRefs(current);
    }
    prevQids.current = current;
  }, [questions, addedRefs, onToggle, onPruneRefs]);

  // Fade the new-group highlight after a few seconds.
  useEffect(() => {
    if (highlightQids.size === 0) return;
    const h = setTimeout(() => setHighlightQids(new Set()), 4500);
    return () => clearTimeout(h);
  }, [highlightQids]);

  const filtered = useMemo(
    () =>
      (questions ?? []).filter((q) =>
        q.text.toLowerCase().includes(search.toLowerCase())
      ),
    [questions, search]
  );

  // Titles for the deck rows (a question's text, or a special slide's heading).
  const questionMap = useMemo(() => {
    const m = new Map<string, Question>();
    (questions ?? []).forEach((q) => m.set(q.qid, q));
    return m;
  }, [questions]);

  // Special-slide types already in the deck — disabled in the add dialog so a
  // double-add can't create duplicate Overview/Conclusion/Demographics slides.
  const existingSpecialTypes = useMemo(
    () => new Set(charts.filter((c) => isSpecialSlide(c)).map((c) => c.chart_type)),
    [charts]
  );

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-24 text-center">
        <AlertCircleIcon className="mb-3 size-8 text-muted-foreground/50" />
        <p className="text-sm font-medium">Couldn't load this material's questions</p>
        <p className="mt-1 max-w-xs text-sm text-muted-foreground">
          It may have been removed. Re-import the data for this case.
        </p>
      </div>
    );
  }

  // The pool lists only questions NOT already in the report — added questions
  // live in the deck above (with a deselect checkbox), so one never appears twice.
  const pool = filtered.filter((q) => !addedRefs.has(q.qid));
  // "Add all shown" adds every chartable question currently visible in the pool
  // (a search scopes it) in one click.
  const addablePool = pool.filter((q) => q.chartable !== false);

  return (
    <div>
      {/* ── Add questions: browse the material's questions and add each as a
          slide. The report's deck (order / removal) is below. ── */}
      <div className="mb-4 flex items-center gap-3">
        <div className="relative max-w-sm flex-1">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search questions…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() => {
            setDialogSelection([]);
            setGroupingOpen(true);
          }}
        >
          <Layers2Icon className="size-4" />
          Manage grouping
        </Button>
        {addablePool.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0 text-muted-foreground"
            onClick={() => onSelectMany(addablePool, true)}
            title="Add every question shown below to the report"
          >
            <CheckCheckIcon className="size-4" />
            Add all shown
          </Button>
        )}
        <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">
          {charts.length} in report · {pool.length} to add
        </span>
      </div>

      {activeSuggestions.length > 0 && (
        <div className="mb-4 space-y-2">
          {activeSuggestions.map((s) => (
            <div
              key={sKey(s.variables)}
              className="flex items-center gap-3 rounded-lg border border-primary/30 bg-primary/5 px-3 py-2"
            >
              <BarChart3Icon className="size-4 shrink-0 text-primary" />
              <div className="min-w-0 flex-1 text-sm">
                <p className="font-medium">
                  {s.variables.length} consecutive questions share a rating scale —
                  group them as a battery (stacked comparison)?
                </p>
              </div>
              <div className="flex shrink-0 gap-1">
                <Button size="sm" className="h-7" onClick={() => groupAsBattery(s)}>
                  View suggestion
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2"
                  title="Dismiss"
                  onClick={() =>
                    setDismissed((d) => new Set(d).add(sKey(s.variables)))
                  }
                >
                  <XIcon className="size-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <ManageGroupingDialog
        materialId={materialId}
        open={groupingOpen}
        onOpenChange={setGroupingOpen}
        grouping={grouping}
        initialSelection={dialogSelection}
        onSave={onGroupingChange}
      />

      <QuestionDetailsDialog
        materialId={materialId}
        qid={detailQid}
        readOnly
        grouping={grouping}
        onOpenChange={(open) => !open && setDetailQid(null)}
      />

      <SpecialSlideInfoDialog
        chart={specialInfoChart}
        questionMap={questionMap}
        onOpenChange={(open) => !open && setSpecialInfoChart(null)}
      />

      <AddSpecialDialog
        open={addSpecialOpen}
        onOpenChange={setAddSpecialOpen}
        existingTypes={existingSpecialTypes}
        // Insert at the FRONT of the deck (afterRef=null) so the new slide is
        // immediately visible at the top rather than scrolled off the bottom.
        onPick={(type) => onAddSpecial(type, null)}
      />

      <div className="space-y-1.5">
        {pool.map((q) => {
          const isAdded = addedRefs.has(q.qid);
          const isChartable = q.chartable !== false;
          const justCreated = highlightQids.has(q.qid);
          return (
            <div
              key={q.qid}
              ref={justCreated ? highlightRef : undefined}
              className="relative"
            >
              <button
                disabled={!isChartable}
                onClick={() => isChartable && onToggle(q)}
                title={!isChartable ? q.non_chartable_reason ?? undefined : undefined}
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg border py-2.5 pr-11 pl-3 text-left transition-colors",
                  justCreated
                    ? "border-primary bg-primary/10 ring-2 ring-primary"
                    : !isChartable
                      ? "cursor-not-allowed border-transparent bg-muted/30 opacity-60"
                      : isAdded
                        ? "border-primary/40 bg-primary/5"
                        : "border-border hover:bg-muted/50"
                )}
              >
                <span
                  className={cn(
                    "flex size-5 shrink-0 items-center justify-center rounded-md border transition-colors",
                    !isChartable
                      ? "border-dashed border-muted-foreground/30"
                      : isAdded
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-input"
                  )}
                >
                  {isAdded && <CheckIcon className="size-3.5" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-2 text-sm leading-snug">
                    {q.text}
                  </span>
                  <span className="mt-0.5 block font-mono text-xs text-muted-foreground">
                    {q.qid}
                  </span>
                </span>
                <KindBadge q={q} />
                {isChartable && isWordcloudOnly(q) && (
                  <Badge
                    variant="outline"
                    className="shrink-0 whitespace-nowrap border-teal-300 bg-teal-50 font-normal text-teal-700"
                  >
                    Word cloud
                  </Badge>
                )}
                {!isChartable && (
                  <Badge
                    variant="outline"
                    className="shrink-0 whitespace-nowrap border-muted-foreground/30 bg-muted font-normal text-muted-foreground"
                    title={q.non_chartable_reason ?? undefined}
                  >
                    Not chartable
                  </Badge>
                )}
              </button>
              {/* ⋮ row menu — sits outside the toggle button so it never toggles the row */}
              <div data-rowmenu className="absolute top-1/2 right-1.5 z-30 -translate-y-1/2">
                <button
                  type="button"
                  title="More…"
                  onClick={() => setMenuQid(menuQid === q.qid ? null : q.qid)}
                  className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <MoreVerticalIcon className="size-4" />
                </button>
                {menuQid === q.qid && (
                  <div className="absolute top-full right-0 z-30 mt-1 min-w-[168px] overflow-hidden rounded-lg border bg-popover py-1 shadow-lg">
                    <button
                      type="button"
                      onClick={() => {
                        setDetailQid(q.qid);
                        setMenuQid(null);
                      }}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent"
                    >
                      <InfoIcon className="size-4 text-muted-foreground" /> View details
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="my-5 border-t" />

      {/* ── The report's deck: arrange slide order, remove slides, add special
          slides. Everything here changes only THIS report, never the material. ── */}
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="text-sm font-medium">
          Slides in this report{charts.length > 0 ? ` · ${charts.length}` : ""}
        </p>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() => setAddSpecialOpen(true)}
        >
          <PlusIcon className="size-4" /> Add special slide
        </Button>
      </div>
      {charts.length > 0 ? (
        <DeckList
          charts={charts}
          questionMap={questionMap}
          onReorder={onReorder}
          onRemove={onRemoveChart}
          onInfo={(c) =>
            isSpecialSlide(c)
              ? setSpecialInfoChart(c)
              : setDetailQid(c.question_ref)
          }
          highlightQids={highlightQids}
          highlightRef={highlightRef}
        />
      ) : (
        <div className="rounded-lg border border-dashed px-3 py-6 text-center text-sm text-muted-foreground">
          No slides yet — add questions above, or a special slide here.
        </div>
      )}
    </div>
  );
}
