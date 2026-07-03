import { useEffect, useMemo, useState } from "react";
import { Layers2Icon, BarChart3Icon, Undo2Icon, GitCompareIcon } from "lucide-react";
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
import type { GroupingOverride, GroupSpec, ComparisonSpec } from "@/lib/api";
import {
  useRegroupedQuestions,
  useParallelSuggestions,
  useVariables,
} from "@/lib/queries";

type Card = {
  key: string;
  label: string;
  variables: string[];
  source: "manual" | "auto";
  kind: "multi" | "battery";
};

type Change = {
  id: number;
  text: string;
  before: { groups: GroupSpec[]; singles: string[]; comparisons: ComparisonSpec[] };
};

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
  const { data: variables } = useVariables(open ? materialId : null, true);

  const [groups, setGroups] = useState<GroupSpec[]>([]);
  const [singles, setSingles] = useState<string[]>([]);
  const [comparisons, setComparisons] = useState<ComparisonSpec[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [groupName, setGroupName] = useState("");
  const [seeded, setSeeded] = useState(false);
  const [stage, setStage] = useState<"questions" | "comparisons">("questions");
  const [changes, setChanges] = useState<Change[]>([]);

  // Snapshot the working state BEFORE a mutation, so its Changes entry can revert to it
  // (undoing that change and everything after it — "revert to this point").
  function record(text: string) {
    setChanges((cs) => [
      { id: (cs[0]?.id ?? 0) + 1, text, before: { groups, singles, comparisons } },
      ...cs,
    ]);
  }
  function undoTo(change: Change) {
    setGroups(change.before.groups);
    setSingles(change.before.singles);
    setComparisons(change.before.comparisons);
    setChanges((cs) => cs.filter((c) => c.id < change.id));
  }

  // Reshape with the WORKING grouping so each card's title is the REAL title the
  // backend produces (the frontend can't re-derive it — O-pattern members carry the
  // OPTION label, not the question). Cards + pool are DERIVED from this, so what you
  // see always matches the questions list after "Apply to report".
  const working = { groups, singles, comparisons };
  const { data: workingReshaped } = useRegroupedQuestions(
    open ? materialId : null,
    working
  );
  const { data: parallelSuggestions } = useParallelSuggestions(
    open ? materialId : null,
    working
  );
  // Baseline = the report's grouping as it was when the dialog opened, for the impact delta.
  const { data: seededReshaped } = useRegroupedQuestions(
    open ? materialId : null,
    grouping
  );

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

  // Seed the WORKING grouping from the report's incoming grouping (once per open).
  useEffect(() => {
    if (!open) {
      setSeeded(false);
      return;
    }
    if (seeded) return;
    setGroups((grouping.groups ?? []).map((g) => ({ ...g })));
    setSingles([...(grouping.singles ?? [])]);
    setComparisons((grouping.comparisons ?? []).map((c) => ({ ...c })));
    setSelected(new Set());
    setChanges([]);
    setSeeded(true);
  }, [open, seeded, grouping]);

  // Cards = the multi/battery questions the backend forms from the working grouping
  // (label = the REAL title). Manual = the var-set is in our groups list; else auto.
  const cards: Card[] = useMemo(() => {
    const manualKeys = new Set(groups.map((g) => setKey(g.variables)));
    return (workingReshaped ?? [])
      .filter((q) => q.kind === "multi" || q.kind === "battery")
      .map((q) => ({
        key: q.qid,
        label: q.text,
        variables: q.variables,
        source: manualKeys.has(setKey(q.variables)) ? "manual" : "auto",
        kind: q.kind as "multi" | "battery",
      }));
  }, [workingReshaped, groups]);

  const groupedVars = useMemo(
    () => new Set(cards.flatMap((c) => c.variables)),
    [cards]
  );

  // Pool = groupable variables not currently in a group: tick-boxes (multi) OR
  // shared-scale rating variables (battery). Lone-scale demographics are excluded.
  const pool = useMemo(
    () =>
      (variables ?? [])
        .filter((v) => kindOf.has(v.name) && !groupedVars.has(v.name))
        .map((v) => v.name),
    [variables, kindOf, groupedVars]
  );

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
    // Send the typed name, else EMPTY — the backend derives the shared question stem.
    // The card's title comes from the backend reshaping (see `cards`), so it always
    // matches the applied result.
    const label = groupName.trim();
    record(`Combined ${vars.length} variables into a ${kind}${label ? ` — ${label}` : ""}`);
    setGroups((g) => [...g, { kind, variables: vars, label }]);
    // Grouping wins over a forced-single: clear any lingering singles for these vars
    // (e.g. re-grouping right after an ungroup) so they aren't in both lists.
    setSingles((s) => s.filter((n) => !selected.has(n)));
    setSelected(new Set());
    setGroupName("");
  }

  function ungroup(card: Card) {
    record(`Split ${card.label} into single variables`);
    if (card.source === "manual") {
      setGroups((g) => g.filter((x) => setKey(x.variables) !== setKey(card.variables)));
    }
    // Force the members single so auto-detection (tick-box multis, ":"-pattern
    // batteries) doesn't immediately re-group them — otherwise the card reappears
    // and the group looks un-ungroupable. Applies to manual AND auto groups.
    setSingles((s) => Array.from(new Set([...s, ...card.variables])));
  }

  // ---- Tier 2: comparisons (overlay parallel questions as one radar / grouped bar) ----
  const labelByQid = useMemo(() => {
    const m = new Map<string, string>();
    (workingReshaped ?? []).forEach((q) => m.set(q.qid, q.text));
    return m;
  }, [workingReshaped]);

  const comparisonCards = useMemo(
    () => (workingReshaped ?? []).filter((q) => q.kind === "comparison"),
    [workingReshaped]
  );
  const comparedKeys = useMemo(
    () => new Set(comparisons.map((c) => setKey(c.members))),
    [comparisons]
  );

  function compareAll(qids: string[]) {
    if (qids.length < 2) return;
    record(`Compared ${qids.length} questions`);
    setComparisons((cs) => [...cs, { members: qids, label: null }]);
    setStage("comparisons");
  }
  function splitComparison(members: string[]) {
    record(`Split a comparison back into ${members.length} questions`);
    setComparisons((cs) => cs.filter((c) => setKey(c.members) !== setKey(members)));
  }
  function removeMember(members: string[], qid: string) {
    record(`Removed ${labelByQid.get(qid) ?? "a question"} from a comparison`);
    setComparisons((cs) =>
      cs
        .map((c) =>
          setKey(c.members) === setKey(members)
            ? { ...c, members: c.members.filter((m) => m !== qid) }
            : c
        )
        .filter((c) => c.members.length >= 2)
    );
  }

  // Suggestions not yet turned into a comparison (by exact member set).
  const openSuggestions = (parallelSuggestions ?? []).filter(
    (s) => !comparedKeys.has(setKey(s.qids))
  );

  // Live structure counts (Structure rail + Report-impact).
  const counts = useMemo(() => {
    const qs = workingReshaped ?? [];
    return {
      total: qs.length,
      multi: qs.filter((q) => q.kind === "multi").length,
      battery: qs.filter((q) => q.kind === "battery").length,
      comparison: qs.filter((q) => q.kind === "comparison").length,
    };
  }, [workingReshaped]);
  const baseCount = seededReshaped?.length ?? counts.total;
  const delta = counts.total - baseCount;

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

        <div className="flex min-h-0 flex-1 gap-3">
          {/* Structure rail — always-on view of the current grouping */}
          <div className="flex w-48 shrink-0 flex-col rounded-lg border">
            <div className="border-b px-3 py-2">
              <span className="text-xs font-medium uppercase text-muted-foreground">Structure</span>
            </div>
            <div className="flex-1 space-y-0.5 overflow-y-auto p-2 text-sm">
              <div className="flex items-center rounded px-2 py-1 font-medium text-muted-foreground">
                <span className="flex-1">Questions</span>
                <span className="tabular-nums">{counts.total - counts.comparison}</span>
              </div>
              <div className="flex items-center gap-2 rounded px-2 py-1 pl-4">
                <span className="rounded bg-muted px-1 text-[10px] font-medium uppercase">multi</span>
                <span className="flex-1">Multi</span>
                <span className="tabular-nums text-muted-foreground">{counts.multi}</span>
              </div>
              <div className="flex items-center gap-2 rounded px-2 py-1 pl-4">
                <span className="rounded bg-violet-100 px-1 text-[10px] font-medium uppercase text-violet-700">battery</span>
                <span className="flex-1">Battery</span>
                <span className="tabular-nums text-muted-foreground">{counts.battery}</span>
              </div>
              <div className="mt-1 flex items-center rounded px-2 py-1 font-medium text-muted-foreground">
                <span className="flex-1">Comparisons</span>
                <span className="tabular-nums">{counts.comparison}</span>
              </div>
            </div>
          </div>

          {/* Working area */}
          <div className="flex min-h-0 flex-1 flex-col gap-2">
            <div className="flex items-center gap-3">
              <div className="inline-flex shrink-0 rounded-lg border bg-muted p-0.5 text-sm">
                <button
                  onClick={() => setStage("questions")}
                  className={`rounded-md px-3 py-1 font-medium ${stage === "questions" ? "bg-background shadow-sm" : "text-muted-foreground"}`}
                >
                  Questions
                </button>
                <button
                  onClick={() => setStage("comparisons")}
                  className={`rounded-md px-3 py-1 font-medium ${stage === "comparisons" ? "bg-background shadow-sm" : "text-muted-foreground"}`}
                >
                  Comparisons{comparisonCards.length ? ` (${comparisonCards.length})` : ""}
                </button>
              </div>
              <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
                <span>Report impact</span>
                <span className="font-semibold tabular-nums text-foreground">{counts.total} items</span>
                {delta !== 0 && (
                  <span className={`rounded-full px-2 py-0.5 font-medium tabular-nums ${delta < 0 ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                    {delta > 0 ? "+" : ""}{delta}
                  </span>
                )}
              </div>
            </div>

        {stage === "questions" && (
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
        )}

        {stage === "comparisons" && (
        <div className="grid min-h-0 flex-1 grid-cols-2 gap-4">
          <div className="flex min-h-0 flex-col rounded-lg border">
            <div className="border-b px-3 py-2">
              <span className="text-xs font-medium uppercase text-muted-foreground">
                Questions to compare
              </span>
            </div>
            <div className="flex-1 space-y-2 overflow-y-auto p-2">
              {openSuggestions.length === 0 ? (
                <p className="px-2 py-6 text-center text-xs text-muted-foreground">
                  No questions share a category set yet — combine variables into questions
                  first, then compare the parallel ones.
                </p>
              ) : (
                openSuggestions.map((s, i) => (
                  <div key={i} className="rounded-md border border-primary/30 bg-primary/5 p-2.5">
                    <p className="text-sm font-medium">
                      {s.qids.length} questions share the same{" "}
                      {s.kind === "battery" ? "attributes" : "options"}
                    </p>
                    <p className="mt-1 truncate text-xs text-muted-foreground">
                      {s.labels.join(", ")}
                    </p>
                    <Button size="sm" className="mt-2" onClick={() => compareAll(s.qids)}>
                      <GitCompareIcon className="size-4" /> Compare
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="flex min-h-0 flex-col rounded-lg border">
            <div className="border-b px-3 py-2">
              <span className="text-xs font-medium uppercase text-muted-foreground">
                Comparisons
              </span>
            </div>
            <div className="flex-1 space-y-2 overflow-y-auto p-2">
              {comparisonCards.length === 0 ? (
                <p className="px-2 py-6 text-center text-xs text-muted-foreground">
                  No comparisons. Accept a suggestion to overlay parallel questions as one
                  chart — pick radar or grouped bars later, in Design.
                </p>
              ) : (
                comparisonCards.map((q) => (
                  <div key={q.qid} className="rounded-md border p-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{q.text}</p>
                        <p className="mt-0.5 text-[10px] text-muted-foreground">
                          {(q.members ?? []).length} questions
                        </p>
                      </div>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        title="Split back into separate questions"
                        onClick={() => splitComparison(q.members ?? [])}
                      >
                        <Undo2Icon className="size-4" />
                      </Button>
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {(q.members ?? []).map((mq) => (
                        <span
                          key={mq}
                          className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]"
                        >
                          {labelByQid.get(mq) ?? mq}
                          <button
                            className="text-muted-foreground hover:text-foreground"
                            title="Remove from comparison"
                            onClick={() => removeMember(q.members ?? [], mq)}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
        )}
          </div>

          {/* Changes rail — every edit, reversible */}
          <div className="flex w-60 shrink-0 flex-col rounded-lg border">
            <div className="flex items-center justify-between border-b px-3 py-2">
              <span className="text-xs font-medium uppercase text-muted-foreground">Changes</span>
              {changes.length > 0 && (
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700">
                  {changes.length} pending
                </span>
              )}
            </div>
            <div className="flex-1 overflow-y-auto p-2">
              {changes.length === 0 ? (
                <p className="px-2 py-6 text-center text-xs text-muted-foreground">
                  No changes yet. Combine variables or compare questions — each edit is listed
                  here and can be undone.
                </p>
              ) : (
                changes.map((c) => (
                  <div key={c.id} className="flex items-start gap-2 border-b py-2 text-xs last:border-0">
                    <span className="flex-1 leading-snug">{c.text}</span>
                    <button
                      className="shrink-0 font-medium text-primary hover:underline"
                      onClick={() => undoTo(c)}
                    >
                      Undo
                    </button>
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
              onSave({ groups, singles, comparisons });
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
