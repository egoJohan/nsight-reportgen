import { useEffect, useMemo, useRef, useState } from "react";
import { CheckIcon, CheckCheckIcon, SquareIcon, SearchIcon, AlertCircleIcon, Layers2Icon, BarChart3Icon, XIcon, MoreVerticalIcon, InfoIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Question, GroupingOverride, BatterySuggestion } from "@/lib/api";
import { useRegroupedQuestions, useBatterySuggestions } from "@/lib/queries";
import ManageGroupingDialog from "@/components/ManageGroupingDialog";
import QuestionDetailsDialog from "@/components/QuestionDetailsDialog";

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
  addedRefs,
  onToggle,
  onSelectMany,
  grouping,
  onGroupingChange,
  onPruneRefs,
}: {
  materialId: string;
  addedRefs: Set<string>;
  onToggle: (question: Question) => void;
  onSelectMany: (questions: Question[], select: boolean) => void;
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

  const selectedCount = (questions ?? []).filter((q) =>
    addedRefs.has(q.qid)
  ).length;

  // "Select all / Deselect all" acts on the currently-VISIBLE chartable questions
  // (so a search scopes it) — turning a big deck into a small one, or vice-versa, in
  // one click instead of toggling every row.
  const chartableFiltered = filtered.filter((q) => q.chartable !== false);
  const allSelected =
    chartableFiltered.length > 0 &&
    chartableFiltered.every((q) => addedRefs.has(q.qid));

  return (
    <div>
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
        {chartableFiltered.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0 text-muted-foreground"
            onClick={() => onSelectMany(chartableFiltered, !allSelected)}
            title={
              allSelected
                ? "Deselect every question shown below"
                : "Select every question shown below"
            }
          >
            {allSelected ? (
              <SquareIcon className="size-4" />
            ) : (
              <CheckCheckIcon className="size-4" />
            )}
            {allSelected ? "Deselect all" : "Select all"}
          </Button>
        )}
        <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">
          {selectedCount} selected · {filtered.length} questions
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

      <div className="space-y-1.5">
        {filtered.map((q) => {
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
        {filtered.length === 0 && (
          <div className="py-16 text-center text-sm text-muted-foreground">
            No questions match your search.
          </div>
        )}
      </div>
    </div>
  );
}
