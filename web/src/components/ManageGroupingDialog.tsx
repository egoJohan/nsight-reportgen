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

type Card = {
  key: string;
  label: string;
  variables: string[];
  source: "manual" | "auto";
  kind: "multi" | "battery";
};

const setKey = (vars: string[]) => [...vars].sort().join(" ");

// Mirror of the backend's _group_text/_shared_question so a new group's card shows
// the SAME title it will get when applied (the shared question stem), not a preview.
function commonPrefix(strs: string[]): string {
  if (!strs.length) return "";
  let p = strs[0];
  for (const s of strs.slice(1)) {
    let i = 0;
    while (i < p.length && i < s.length && p[i] === s[i]) i++;
    p = p.slice(0, i);
  }
  return p;
}

function deriveGroupTitle(labels: string[]): string {
  if (!labels.length) return "";
  if (labels[0].includes(":")) {
    const rhs = labels.map((l) => l.slice(l.indexOf(":") + 1).trim());
    if (rhs.every(Boolean)) {
      // Shared question = the longest right-hand side when every other is its prefix
      // (tolerant of SPSS truncation; covers the identical case too).
      const longest = rhs.reduce((a, b) => (b.length > a.length ? b : a));
      if (rhs.every((r) => longest.startsWith(r))) return longest;
    }
  }
  const stem = commonPrefix(labels).replace(/[\s:-]+$/, "");
  return stem || labels[0];
}

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

  // Scale keys shared by ≥2 variables — only these can form a battery (a battery
  // needs ≥2 members on ONE scale, so a lone age/gender/region scale is excluded).
  const sharedScaleKeys = useMemo(() => {
    const counts = new Map<string, number>();
    (variables ?? []).forEach((v) => {
      if (v.scale && v.scale_key)
        counts.set(v.scale_key, (counts.get(v.scale_key) ?? 0) + 1);
    });
    return new Set([...counts].filter(([, n]) => n >= 2).map(([k]) => k));
  }, [variables]);

  const scaleKeyOf = useMemo(() => {
    const m = new Map<string, string>();
    (variables ?? []).forEach((v) => {
      if (v.scale && v.scale_key) m.set(v.name, v.scale_key);
    });
    return m;
  }, [variables]);

  // Which grouping each variable is eligible for: tick-boxes → multi, SHARED-scale
  // rating variables → battery. Drives the pool + which group action is enabled.
  const kindOf = useMemo(() => {
    const m = new Map<string, "tickbox" | "scale">();
    (variables ?? []).forEach((v) => {
      if (v.tickbox) m.set(v.name, "tickbox");
      else if (v.scale && v.scale_key && sharedScaleKeys.has(v.scale_key))
        m.set(v.name, "scale");
    });
    return m;
  }, [variables, sharedScaleKeys]);

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
        kind: q.kind as "multi" | "battery",
      }))
    );
    // Pool = ungrouped, groupable variables: tick-boxes (multi) OR shared-scale
    // rating variables (battery). Lone-scale demographics (age/gender/region) are
    // NOT groupable, so they're excluded.
    setPool(
      (variables ?? [])
        .filter((v) => kindOf.has(v.name) && !grouped.has(v.name))
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
    // Send the typed name, else EMPTY — the backend derives the shared question stem
    // (concatenating member labels made huge, ugly group names). For the in-session
    // card we show a short preview until the reshaped list re-derives the real name.
    const typed = groupName.trim();
    // Show the SAME title the group gets on apply (the shared stem), so the new card
    // is recognisable and matches the questions list after "Apply to report".
    const preview = typed || deriveGroupTitle(vars.map((v) => labelOf.get(v) ?? v));
    setGroups((g) => [...g, { kind, variables: vars, label: typed }]);
    setCards((c) => [
      { key: `manual:${setKey(vars)}`, label: preview, variables: vars, source: "manual", kind },
      ...c,
    ]);
    setPool((p) => p.filter((n) => !selected.has(n)));
    // Grouping wins over a forced-single: clear any lingering singles for these vars
    // (e.g. re-grouping right after an ungroup) so they aren't in both lists.
    setSingles((s) => s.filter((n) => !selected.has(n)));
    setSelected(new Set());
    setGroupName("");
  }

  function ungroup(card: Card) {
    setCards((c) => c.filter((x) => x !== card));
    if (card.source === "manual") {
      setGroups((g) => g.filter((x) => setKey(x.variables) !== setKey(card.variables)));
    }
    // Force the members single so auto-detection (tick-box multis, ":"-pattern
    // batteries) doesn't immediately re-group them — otherwise the card reappears
    // and the group looks un-ungroupable. Applies to manual AND auto groups.
    setSingles((s) => Array.from(new Set([...s, ...card.variables])));
    setPool((p) => Array.from(new Set([...p, ...card.variables])));
  }

  // The selection can be grouped only when it's ≥2 variables all of one kind:
  // tick-boxes → multi, rating scales → battery. (The backend re-validates.)
  const selKind = (() => {
    const kinds = new Set([...selected].map((n) => kindOf.get(n)));
    return kinds.size === 1 ? [...kinds][0] : null;
  })();
  const canMulti = selected.size >= 2 && selKind === "tickbox";
  // A battery also requires all selected variables to share ONE scale.
  const canBattery =
    selected.size >= 2 &&
    selKind === "scale" &&
    new Set([...selected].map((n) => scaleKeyOf.get(n))).size === 1;

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
                        <Badge
                          variant="secondary"
                          className={`font-normal text-[10px] ${
                            card.kind === "battery"
                              ? "bg-violet-100 text-violet-700"
                              : ""
                          }`}
                        >
                          {card.kind === "battery" ? "battery" : "multi"}
                        </Badge>
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
