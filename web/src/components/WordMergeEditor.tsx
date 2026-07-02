import { useEffect, useMemo, useState } from "react";
import { Layers2Icon, Undo2Icon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { WordMerge } from "@/lib/api";
import { useQuestionWords, useSetWordMerges } from "@/lib/queries";

/**
 * Merge word-cloud token variants (Esperi, esper) into one word so their counts
 * sum. Material-level — applies to every word cloud of this text question. Lives
 * in the case-page question dialog.
 */
export default function WordMergeEditor({
  materialId,
  qid,
}: {
  materialId: string;
  qid: string;
}) {
  const { data } = useQuestionWords(materialId, qid);
  const save = useSetWordMerges(materialId);
  const [groups, setGroups] = useState<WordMerge[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [label, setLabel] = useState("");
  const [seeded, setSeeded] = useState(false);

  const counts = useMemo(() => {
    const m = new Map<string, number>();
    (data?.words ?? []).forEach((w) => m.set(w.word, w.count));
    return m;
  }, [data]);

  // Seed the working groups from the saved merges once, on load / qid change.
  useEffect(() => {
    setSeeded(false);
  }, [qid]);
  useEffect(() => {
    if (seeded || !data) return;
    setGroups(data.merges.map((g) => ({ label: g.label, words: [...g.words] })));
    setSelected(new Set());
    setSeeded(true);
  }, [data, seeded]);

  const grouped = useMemo(() => new Set(groups.flatMap((g) => g.words)), [groups]);
  const pool = (data?.words ?? []).filter((w) => !grouped.has(w.word));
  const dirty = JSON.stringify(groups) !== JSON.stringify(data?.merges ?? []);

  function toggle(word: string) {
    setSelected((prev) => {
      const n = new Set(prev);
      n.has(word) ? n.delete(word) : n.add(word);
      return n;
    });
  }

  function mergeSelected() {
    const words = [...selected];
    if (words.length < 2) return;
    const top = [...words].sort((a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0))[0];
    setGroups((g) => [...g, { label: label.trim() || top, words }]);
    setSelected(new Set());
    setLabel("");
  }

  function persist() {
    save.mutate(
      { qid, merges: groups },
      {
        onSuccess: () => toast.success("Word-cloud merges saved"),
        onError: (e) =>
          toast.error(`Save failed: ${e instanceof Error ? e.message : "unknown error"}`),
      }
    );
  }

  if (!data) {
    return <p className="text-xs text-muted-foreground">Loading words…</p>;
  }
  if (data.words.length === 0 && groups.length === 0) {
    return <p className="text-xs text-muted-foreground">No word-cloud answers to merge.</p>;
  }

  return (
    <div className="space-y-2.5">
      {groups.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {groups.map((g, i) => (
            <span
              key={`${g.label}-${i}`}
              className="inline-flex items-center gap-1.5 rounded-md border bg-muted/40 px-2 py-1 text-xs"
            >
              <span className="font-medium">{g.label}</span>
              <span className="text-muted-foreground">← {g.words.join(", ")}</span>
              <button
                type="button"
                onClick={() => setGroups((gs) => gs.filter((x) => x !== g))}
                className="text-muted-foreground hover:text-destructive"
                title="Split this merge"
              >
                <Undo2Icon className="size-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="max-h-52 overflow-y-auto rounded-lg border p-1.5">
        {pool.length === 0 ? (
          <p className="px-2 py-4 text-center text-xs text-muted-foreground">
            No more words to merge.
          </p>
        ) : (
          pool.map((w) => (
            <button
              key={w.word}
              type="button"
              onClick={() => toggle(w.word)}
              className={`flex w-full items-center justify-between rounded px-2 py-1 text-left text-sm hover:bg-muted/60 ${
                selected.has(w.word) ? "bg-primary/10" : ""
              }`}
            >
              <span className="flex min-w-0 items-center gap-2">
                <span
                  className={`flex size-4 shrink-0 items-center justify-center rounded border text-[10px] ${
                    selected.has(w.word)
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-muted-foreground/40"
                  }`}
                >
                  {selected.has(w.word) ? "✓" : ""}
                </span>
                <span className="truncate">{w.word}</span>
              </span>
              <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{w.count}</span>
            </button>
          ))
        )}
      </div>

      <div className="flex items-center gap-2">
        <Input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Merged word (defaults to the most frequent)"
          className="h-8 flex-1"
        />
        <Button size="sm" variant="outline" disabled={selected.size < 2} onClick={mergeSelected}>
          <Layers2Icon className="size-4" /> Merge ({selected.size})
        </Button>
      </div>

      {dirty && (
        <div className="flex justify-end">
          <Button size="sm" disabled={save.isPending} onClick={persist}>
            Save merges
          </Button>
        </div>
      )}
    </div>
  );
}
