import { useMemo, useState } from "react";
import { CheckIcon, SearchIcon, AlertCircleIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Question } from "@/lib/api";
import { useQuestions } from "@/lib/queries";

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
}: {
  materialId: string;
  addedRefs: Set<string>;
  onToggle: (question: Question) => void;
}) {
  const { data: questions, isLoading, isError } = useQuestions(materialId);
  const [search, setSearch] = useState("");

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
        <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">
          {selectedCount} selected · {filtered.length} questions
        </span>
      </div>

      <p className="mb-3 text-sm text-muted-foreground">
        Toggle a question to add or remove its chart from the report, then press
        Next.
      </p>

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
