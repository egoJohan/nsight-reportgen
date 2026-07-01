import { useEffect, useMemo, useState } from "react";
import { Layers2Icon, Undo2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { GroupingOverride, GroupSpec } from "@/lib/api";
import { useRegroupedQuestions, useVariables } from "@/lib/queries";

type Card = { key: string; label: string; variables: string[]; source: "manual" | "auto" };

const setKey = (vars: string[]) => [...vars].sort().join(" ");

/**
 * Controlled grouping editor for a REPORT. Seeded from the report's current
 * `grouping`; on Save it emits the edited override via `onSave` (the report saves
 * it — nothing is persisted per-material here).
 */
export default function ManageGroupingDialog({
  materialId,
  open,
  onOpenChange,
  grouping,
  onSave,
}: {
  materialId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  grouping: GroupingOverride;
  onSave: (override: GroupingOverride) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  // Cards reflect the report's CURRENT (incoming) grouping.
  const { data: reshaped } = useRegroupedQuestions(open ? materialId : null, grouping);
  const { data: variables } = useVariables(open ? materialId : null, showAll);

  const [groups, setGroups] = useState<GroupSpec[]>([]);
  const [singles, setSingles] = useState<string[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const [pool, setPool] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [seeded, setSeeded] = useState(false);

  const labelOf = useMemo(() => {
    const m = new Map<string, string>();
    (variables ?? []).forEach((v) => m.set(v.name, v.label));
    return m;
  }, [variables]);

  useEffect(() => {
    if (!open) {
      setSeeded(false);
      return;
    }
    if (seeded || !reshaped || !variables) return;
    const manualKeys = new Set((grouping.groups ?? []).map((g) => setKey(g.variables)));
    setGroups((grouping.groups ?? []).map((g) => ({ ...g })));
    setSingles([...(grouping.singles ?? [])]);
    setCards(
      reshaped
        .filter((q) => q.kind === "multi" || q.kind === "battery")
        .map((q) => ({
          key: q.qid,
          label: q.text,
          variables: q.variables,
          source: manualKeys.has(setKey(q.variables)) ? "manual" : "auto",
        }))
    );
    setPool((variables ?? []).map((v) => v.name));
    setSelected(new Set());
    setSeeded(true);
  }, [open, seeded, reshaped, variables, grouping]);

  function toggle(name: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  function groupSelected() {
    const vars = [...selected];
    if (vars.length < 2) return;
    setGroups((g) => [...g, { kind: "multi", variables: vars }]);
    setCards((c) => [
      { key: `manual:${setKey(vars)}`, label: vars.map((v) => labelOf.get(v) ?? v).join(" · "), variables: vars, source: "manual" },
      ...c,
    ]);
    setPool((p) => p.filter((n) => !selected.has(n)));
    setSelected(new Set());
  }

  function ungroup(card: Card) {
    setCards((c) => c.filter((x) => x !== card));
    if (card.source === "manual") {
      setGroups((g) => g.filter((x) => setKey(x.variables) !== setKey(card.variables)));
    } else {
      setSingles((s) => Array.from(new Set([...s, ...card.variables])));
    }
    setPool((p) => Array.from(new Set([...p, ...card.variables])));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[85vh] w-[85vw] max-w-[85vw] flex-col">
        <DialogHeader>
          <DialogTitle>Manage grouping</DialogTitle>
          <DialogDescription>
            Combine variables into a multi-response question, or split a group back
            into single variables — for this report. Auto-detected groups can be split too.
          </DialogDescription>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 grid-cols-2 gap-4">
          <div className="flex min-h-0 flex-col rounded-lg border">
            <div className="flex items-center justify-between border-b px-3 py-2">
              <span className="text-xs font-medium uppercase text-muted-foreground">Variables</span>
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <input type="checkbox" checked={showAll} onChange={(e) => { setShowAll(e.target.checked); setSeeded(false); }} />
                show all
              </label>
            </div>
            <div className="flex-1 overflow-y-auto p-1.5">
              {pool.length === 0 ? (
                <p className="px-2 py-6 text-center text-xs text-muted-foreground">No ungrouped variables</p>
              ) : (
                pool.map((name) => (
                  <button
                    key={name}
                    onClick={() => toggle(name)}
                    className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm hover:bg-muted/60 ${selected.has(name) ? "bg-primary/10" : ""}`}
                  >
                    <span className={`flex size-4 shrink-0 items-center justify-center rounded border text-[10px] ${selected.has(name) ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40"}`}>
                      {selected.has(name) ? "✓" : ""}
                    </span>
                    <span className="min-w-0 flex-1 truncate">{labelOf.get(name) ?? name}</span>
                    <span className="font-mono text-[10px] text-muted-foreground">{name}</span>
                  </button>
                ))
              )}
            </div>
            <div className="border-t p-2">
              <Button size="sm" className="w-full" disabled={selected.size < 2} onClick={groupSelected}>
                <Layers2Icon className="size-4" /> Group as multi ({selected.size})
              </Button>
            </div>
          </div>

          <div className="flex min-h-0 flex-col rounded-lg border">
            <div className="border-b px-3 py-2">
              <span className="text-xs font-medium uppercase text-muted-foreground">Groups</span>
            </div>
            <div className="flex-1 space-y-2 overflow-y-auto p-2">
              {cards.length === 0 ? (
                <p className="px-2 py-6 text-center text-xs text-muted-foreground">No groups</p>
              ) : (
                cards.map((card) => (
                  <div key={card.key} className="rounded-md border p-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{card.label}</p>
                        <p className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">
                          {card.variables.join(", ")}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <Badge variant="outline" className="font-normal text-[10px]">
                          {card.source === "manual" ? "manual" : "auto"}
                        </Badge>
                        <Button size="icon-sm" variant="ghost" title="Split into single variables" onClick={() => ungroup(card)}>
                          <Undo2Icon className="size-4" />
                        </Button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            onClick={() => {
              onSave({ groups, singles });
              onOpenChange(false);
            }}
          >
            Apply to report
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
