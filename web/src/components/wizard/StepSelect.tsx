import { useMemo, useState } from "react";
import { CheckIcon, SearchIcon, PlusIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Question } from "@/lib/api";
import { useQuestions } from "@/lib/queries";

function KindBadge({ q }: { q: Question }) {
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
  onAdd,
}: {
  materialId: string;
  addedRefs: Set<string>;
  onAdd: (questions: Question[]) => void;
}) {
  const { data: questions, isLoading } = useQuestions(materialId);
  const [search, setSearch] = useState("");
  const [checked, setChecked] = useState<Set<string>>(new Set());

  const filtered = useMemo(
    () =>
      (questions ?? []).filter((q) =>
        q.text.toLowerCase().includes(search.toLowerCase())
      ),
    [questions, search]
  );

  function toggle(qid: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(qid)) next.delete(qid);
      else next.add(qid);
      return next;
    });
  }

  function handleAdd() {
    const toAdd = (questions ?? []).filter(
      (q) => checked.has(q.qid) && !addedRefs.has(q.qid)
    );
    if (toAdd.length > 0) onAdd(toAdd);
    setChecked(new Set());
  }

  const selectableChecked = [...checked].filter((id) => !addedRefs.has(id));

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-lg" />
        ))}
      </div>
    );
  }

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
          {filtered.length} questions
        </span>
        <Button
          onClick={handleAdd}
          disabled={selectableChecked.length === 0}
          size="sm"
        >
          <PlusIcon className="size-4" />
          Add selected
          {selectableChecked.length > 0 ? ` (${selectableChecked.length})` : ""}
        </Button>
      </div>

      <div className="space-y-1.5">
        {filtered.map((q) => {
          const isAdded = addedRefs.has(q.qid);
          const isChecked = checked.has(q.qid);
          return (
            <button
              key={q.qid}
              disabled={isAdded}
              onClick={() => toggle(q.qid)}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
                isAdded
                  ? "cursor-default border-transparent bg-muted/40 opacity-70"
                  : isChecked
                    ? "border-primary/40 bg-primary/5"
                    : "border-border hover:bg-muted/50"
              )}
            >
              <span
                className={cn(
                  "flex size-5 shrink-0 items-center justify-center rounded-md border transition-colors",
                  isAdded
                    ? "border-transparent bg-muted-foreground/30 text-background"
                    : isChecked
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input"
                )}
              >
                {(isChecked || isAdded) && <CheckIcon className="size-3.5" />}
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
              {isAdded && (
                <Badge
                  variant="outline"
                  className="shrink-0 border-emerald-300 bg-emerald-50 font-normal text-emerald-600"
                >
                  Added
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
