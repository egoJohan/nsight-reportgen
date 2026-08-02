import { useEffect, useMemo, useState } from "react";
import { ColumnsIcon, FileTextIcon, ListChecksIcon, Loader2Icon, UsersIcon } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import type { GroupingOverride, Question, Variable } from "@/lib/api";

// The slide types a user can add beyond the one-per-question defaults. The three
// AI ones write their CONTENT from the report's data and are once-only; "Compare
// groups" is neither AI-written nor once-only — comparing by Polku and then by
// gender are two legitimate sections. (spec 2026-08-02-compare-groups-section §1.2)
const SLIDE_CHOICES: {
  type: string;
  label: string;
  description: string;
  Icon: typeof FileTextIcon;
  repeatable?: boolean;
}[] = [
  {
    type: "special_overview",
    label: "Overview",
    description:
      "Background about the research, written by AI from the available information.",
    Icon: FileTextIcon,
  },
  {
    type: "special_conclusion",
    label: "Conclusion",
    description:
      "The major conclusions drawn across the report's questions, written by AI.",
    Icon: ListChecksIcon,
  },
  {
    type: "special_demographics",
    label: "Demographics",
    description:
      "Facts about the respondents plus a chart per demographic question, written by AI.",
    Icon: UsersIcon,
  },
  {
    type: "compare_groups",
    label: "Compare groups",
    description:
      "One slide per question, split into the groups of a variable you choose — e.g. the two packaging designs.",
    Icon: ColumnsIcon,
    repeatable: true,
  },
];

export function AddSpecialDialog({
  open,
  onOpenChange,
  existingTypes,
  onPick,
  materialId,
  grouping,
  variables,
  questions,
  reportQids,
  onAddComparison,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  existingTypes: Set<string>;
  onPick: (type: string) => void;
  materialId: string;
  grouping: GroupingOverride;
  variables: Variable[] | undefined;
  questions: Question[] | undefined;
  // Questions currently in the report — the ones a comparison section can copy.
  reportQids: Set<string>;
  onAddComparison: (classifyingVar: string, qids: string[]) => void;
}) {
  const [mode, setMode] = useState<"pick" | "compare">("pick");

  // Reset to the chooser whenever the dialog reopens.
  useEffect(() => {
    if (open) setMode("pick");
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {mode === "compare" ? "Compare groups" : "Add a slide"}
          </DialogTitle>
          <DialogDescription>
            {mode === "compare"
              ? "Adds one slide per question, split into the chosen variable's groups. Your existing total-level slides stay as they are."
              : "Add a slide beyond the one-per-question defaults."}
          </DialogDescription>
        </DialogHeader>

        {mode === "compare" ? (
          <CompareGroupsForm
            materialId={materialId}
            grouping={grouping}
            variables={variables}
            questions={(questions ?? []).filter((q) => reportQids.has(q.qid))}
            onCancel={() => setMode("pick")}
            onSubmit={(clf, qids) => {
              onAddComparison(clf, qids);
              onOpenChange(false);
            }}
          />
        ) : (
          <div className="space-y-2">
            {SLIDE_CHOICES.map(({ type, label, description, Icon, repeatable }) => {
              const added = existingTypes.has(type) && !repeatable;
              return (
                <button
                  key={type}
                  type="button"
                  disabled={added}
                  onClick={() => {
                    if (type === "compare_groups") {
                      setMode("compare");
                      return;
                    }
                    onPick(type);
                    onOpenChange(false);
                  }}
                  className="flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors hover:bg-accent/50 disabled:pointer-events-none disabled:opacity-50"
                >
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="size-4" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      {label}
                      {added && (
                        <span className="ml-2 text-xs font-normal text-muted-foreground">
                          Added
                        </span>
                      )}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function CompareGroupsForm({
  materialId,
  grouping,
  variables,
  questions,
  onCancel,
  onSubmit,
}: {
  materialId: string;
  grouping: GroupingOverride;
  variables: Variable[] | undefined;
  questions: Question[];
  onCancel: () => void;
  onSubmit: (classifyingVar: string, qids: string[]) => void;
}) {
  const [clf, setClf] = useState<string>("");
  const [counts, setCounts] = useState<Record<string, number> | null>(null);
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());

  const segmenters = useMemo(
    () => (variables ?? []).filter((v) => v.segmentable),
    [variables]
  );

  // Which questions this variable ACTUALLY splits. A battery whose members belong
  // to one study arm returns 1 group, and offering it would generate a slide that
  // looks unsplit. (spec 2026-08-02-compare-groups-section §1.1)
  useEffect(() => {
    if (!clf) {
      setCounts(null);
      setPicked(new Set());
      return;
    }
    let live = true;
    setLoading(true);
    setCounts(null);
    api.materials
      .splitGroups(materialId, clf, grouping)
      .then((c) => {
        if (!live) return;
        setCounts(c);
        setPicked(
          new Set(questions.filter((q) => (c[q.qid] ?? 0) >= 2).map((q) => q.qid))
        );
      })
      .catch(() => live && setCounts({}))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [clf, materialId, grouping, questions]);

  const splits = (qid: string) => (counts?.[qid] ?? 0) >= 2;
  const toggle = (qid: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(qid)) next.delete(qid);
      else next.add(qid);
      return next;
    });

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label className="text-xs font-medium text-muted-foreground">Group by</Label>
        <Select value={clf} onValueChange={(v) => setClf(v ?? "")}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Choose a variable…" />
          </SelectTrigger>
          <SelectContent>
            {segmenters.map((v) => (
              <SelectItem key={v.name} value={v.name}>
                {v.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs font-medium text-muted-foreground">Questions</Label>
        {!clf ? (
          <p className="text-xs text-muted-foreground">
            Choose a variable to see which questions it splits.
          </p>
        ) : loading ? (
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2Icon className="size-3 animate-spin" /> Checking which questions
            split…
          </p>
        ) : (
          <div className="max-h-64 space-y-1 overflow-y-auto rounded-md border p-2">
            {questions.map((q) => {
              const ok = splits(q.qid);
              return (
                <label
                  key={q.qid}
                  className={`flex items-start gap-2 rounded p-1.5 text-xs ${
                    ok ? "cursor-pointer hover:bg-accent/50" : "opacity-50"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    disabled={!ok}
                    checked={picked.has(q.qid)}
                    onChange={() => toggle(q.qid)}
                  />
                  <span className="min-w-0">
                    <span className="block truncate">{q.text || q.qid}</span>
                    {!ok && (
                      <span className="text-muted-foreground">
                        only one group answered this question
                      </span>
                    )}
                  </span>
                </label>
              );
            })}
          </div>
        )}
      </div>

      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Back
        </Button>
        <Button
          size="sm"
          disabled={!clf || picked.size === 0}
          onClick={() => onSubmit(clf, questions.map((q) => q.qid).filter((q) => picked.has(q)))}
        >
          Add {picked.size || ""} slide{picked.size === 1 ? "" : "s"}
        </Button>
      </div>
    </div>
  );
}
