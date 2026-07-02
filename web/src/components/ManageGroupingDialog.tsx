import { useEffect, useMemo, useState } from "react";
import { Layers2Icon, BarChart3Icon, Undo2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
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
  // Cards reflect the report's CURRENT (incoming) grouping. Fetch the FULL
  // variable list (all=true) so grouped members carry labels — a split shows
  // titles, not raw ids.
  const { data: reshaped } = useRegroupedQuestions(open ? materialId : null, grouping);
  const { data: variables } = useVariables(open ? materialId : null, true);

  const [groups, setGroups] = useState<GroupSpec[]>([]);
  const [singles, setSingles] = useState<string[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const [pool, setPool] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [groupName, setGroupName] = useState("");
  const [seeded, setSeeded] = useState(false);

  const labelOf = useMemo(() => {
    const m = new Map<string, string>();
    (variables ?? []).forEach((v) => m.set(v.name, v.label));
    return m;
  }, [variables]);

  // Which grouping each variable is eligible for: tick-boxes → multi, rating
  // scales → battery. Drives the pool + which group action is enabled.
  const kindOf = useMemo(() => {
    const m = new Map<string, "tickbox" | "scale">();
    (variables ?? []).forEach((v) => {
      if (v.tickbox) m.set(v.name, "tickbox");
      else if (v.scale) m.set(v.name, "scale");
    });
    return m;
  }, [variables]);

  useEffect(() => {
    if (!open) {
      setSeeded(false);
      return;
    }
    if (seeded || !reshaped || !variables) return;
    const manualKeys = new Set((grouping.groups ?? []).map((g) => setKey(g.variables)));
    const groupCards = reshaped.filter((q) => q.kind === "multi" || q.kind === "battery");
    // Variables already in a group are shown as cards, not in the pool.
    const grouped = new Set(groupCards.flatMap((q) => q.variables));
    setGroups((grouping.groups ?? []).map((g) => ({ ...g })));
    setSingles([...(grouping.singles ?? [])]);
    setCards(
      groupCards.map((q) => ({
        key: q.qid,
        label: q.text,
        variables: q.variables,
        source: manualKeys.has(setKey(q.variables)) ? "manual" : "auto",
      }))
    );
    // Pool = ungrouped tick-box (multi) OR rating-scale (battery) variables.
    setPool(
      (variables ?? [])
        .filter((v) => (v.tickbox || v.scale) && !grouped.has(v.name))
        .map((v) => v.name)
    );
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

  function groupSelected(kind: "multi" | "battery") {
    const vars = [...selected];
    if (vars.length < 2) return;
    // Always send a meaningful label: the typed name, else the member labels
    // joined (so the group is never named by a weak common-prefix like "Mi").
    const label =
      groupName.trim() || vars.map((v) => labelOf.get(v) ?? v).join(" · ");
    setGroups((g) => [...g, { kind, variables: vars, label }]);
    setCards((c) => [
      { key: `manual:${setKey(vars)}`, label, variables: vars, source: "manual" },
      ...c,
    ]);
    setPool((p) => p.filter((n) => !selected.has(n)));
    setSelected(new Set());
    setGroupName("");
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

  // The selection can be grouped only when it's ≥2 variables all of one kind:
  // tick-boxes → multi, rating scales → battery. (The backend re-validates.)
  const selKind = (() => {
    const kinds = new Set([...selected].map((n) => kindOf.get(n)));
    return kinds.size === 1 ? [...kinds][0] : null;
  })();
  const canMulti = selected.size >= 2 && selKind === "tickbox";
  const canBattery = selected.size >= 2 && selKind === "scale";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[85vh] w-[85vw] max-w-[85vw] flex-col sm:max-w-[85vw]">
        <DialogHeader>
          <DialogTitle>Manage grouping</DialogTitle>
          <DialogDescription>
            Combine variables into a group — for this report. Tick-box (yes/no)
            variables form a <strong>multi-response</strong> question; rating-scale
            variables that share a scale form a <strong>battery</strong> (a stacked
            comparison chart). Other question types aren't shown here. Auto-detected
            groups can be split back into single variables too.
          </DialogDescription>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 grid-cols-2 gap-4">
          <div className="flex min-h-0 flex-col rounded-lg border">
            <div className="border-b px-3 py-2">
              <span className="text-xs font-medium uppercase text-muted-foreground">
                Groupable variables
              </span>
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
                    <span
                      className={`shrink-0 rounded px-1 text-[9px] font-medium uppercase ${
                        kindOf.get(name) === "scale"
                          ? "bg-violet-100 text-violet-700"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {kindOf.get(name) === "scale" ? "scale" : "tick"}
                    </span>
                  </button>
                ))
              )}
            </div>
            <div className="space-y-2 border-t p-2">
              <Input
                value={groupName}
                onChange={(e) => setGroupName(e.target.value)}
                placeholder="Group name (optional)"
                className="h-8"
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  className="flex-1"
                  variant="outline"
                  disabled={!canMulti}
                  title={
                    selected.size >= 2 && !canMulti
                      ? "Select 2+ tick-box (yes/no) variables"
                      : undefined
                  }
                  onClick={() => groupSelected("multi")}
                >
                  <Layers2Icon className="size-4" /> Group as multi ({selected.size})
                </Button>
                <Button
                  size="sm"
                  className="flex-1"
                  variant="outline"
                  disabled={!canBattery}
                  title={
                    selected.size >= 2 && !canBattery
                      ? "Select 2+ rating-scale variables sharing a scale"
                      : undefined
                  }
                  onClick={() => groupSelected("battery")}
                >
                  <BarChart3Icon className="size-4" /> Group as battery ({selected.size})
                </Button>
              </div>
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
