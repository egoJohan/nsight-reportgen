import { useEffect, useMemo, useRef, useState } from "react";
import { CheckIcon, SearchIcon, AlertCircleIcon, Layers2Icon, BarChart3Icon, XIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Question, GroupingOverride, BatterySuggestion } from "@/lib/api";
import { useRegroupedQuestions, useBatterySuggestions } from "@/lib/queries";
import ManageGroupingDialog from "@/components/ManageGroupingDialog";

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
  grouping,
  onGroupingChange,
  onPruneRefs,
}: {
  materialId: string;
  addedRefs: Set<string>;
  onToggle: (question: Question) => void;
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
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const sKey = (vars: string[]) => [...vars].sort().join(",");
  const activeSuggestions = (suggestions ?? []).filter(
    (s) => !dismissed.has(sKey(s.variables))
  );

  function groupAsBattery(s: BatterySuggestion) {
    // Default label from the first few statements; the user can rename in the dialog.
    const label =
      s.labels.slice(0, 3).join(" · ") + (s.labels.length > 3 ? " …" : "");
    onGroupingChange({
      ...grouping,
      groups: [
        ...grouping.groups,
        { kind: "battery", variables: s.variables, label },
      ],
    });
  }

  // Auto-select a newly-created group: when the reshaped list gains a group
  // question that wasn't there before (i.e. the user just grouped some
  // variables), add it to the report by default. Skips the first load so
  // opening a report doesn't add everything.
  const prevQids = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!questions) return;
    const current = new Set(questions.map((q) => q.qid));
    if (prevQids.current) {
      for (const q of questions) {
        const isGroup = q.kind === "multi" || q.kind === "battery";
        if (isGroup && !prevQids.current.has(q.qid) && !addedRefs.has(q.qid)) {
          onToggle(q);
        }
      }
    }
    // Drop any chart whose question no longer exists (its variable was absorbed
    // into a group, or a group was split away).
    if ([...addedRefs].some((ref) => !current.has(ref))) {
      onPruneRefs(current);
    }
    prevQids.current = current;
  }, [questions, addedRefs, onToggle, onPruneRefs]);

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
          onClick={() => setGroupingOpen(true)}
        >
          <Layers2Icon className="size-4" />
          Manage grouping
        </Button>
        <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">
          {selectedCount} selected · {filtered.length} questions
        </span>
      </div>

      {activeSuggestions.length > 0 && (
        <div className="mb-4 space-y-2">
          {activeSuggestions.map((s) => (
            <div
              key={sKey(s.variables)}
              className="flex items-start gap-3 rounded-lg border border-primary/30 bg-primary/5 px-3 py-2"
            >
              <BarChart3Icon className="mt-0.5 size-4 shrink-0 text-primary" />
              <div className="min-w-0 flex-1 text-sm">
                <p className="font-medium">
                  {s.variables.length} consecutive questions share a rating scale —
                  group them as a battery (stacked comparison)?
                </p>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  {s.labels.join(" · ")}
                </p>
              </div>
              <div className="flex shrink-0 gap-1">
                <Button size="sm" className="h-7" onClick={() => groupAsBattery(s)}>
                  Group as battery
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
        onSave={onGroupingChange}
      />

      <div className="space-y-1.5">
        {filtered.map((q) => {
          const isAdded = addedRefs.has(q.qid);
          const isChartable = q.chartable !== false;
          return (
            <button
              key={q.qid}
              disabled={!isChartable}
              onClick={() => isChartable && onToggle(q)}
              title={!isChartable ? q.non_chartable_reason ?? undefined : undefined}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
                !isChartable
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
