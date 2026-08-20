import { useEffect, useMemo, useState } from "react";
import {
  ColumnsIcon,
  FileTextIcon,
  ListChecksIcon,
  Loader2Icon,
  PencilLineIcon,
  UsersIcon,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
    label: "Yhteenveto",
    description:
      "Background on the study, written by AI from what is available.",
    Icon: FileTextIcon,
  },
  {
    type: "special_conclusion",
    label: "Conclusions",
    description:
      "The key conclusions drawn from the report's questions, written by AI.",
    Icon: ListChecksIcon,
  },
  {
    type: "special_demographics",
    label: "Taustatiedot",
    description:
      "Who answered, plus a chart per background question, written by AI.",
    Icon: UsersIcon,
  },
  {
    type: "special_blank",
    label: "Blank slide",
    description:
      "A heading and your own bullets in markdown — nothing is generated.",
    Icon: PencilLineIcon,
    repeatable: true,
  },
  {
    type: "compare_groups",
    label: "Compare groups",
    description:
      "Yksi dia per kysymys, jaettuna valitsemasi muuttujan ryhmiin — esim. kahteen pakkausvaihtoehtoon.",
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
      {/* The compare form is a working surface listing whole question sentences,
          so it follows ManageGroupingDialog's shape rather than the small chooser's:
          a flex COLUMN with a scrolling body and a footer pinned at the bottom, so
          the actions are always reachable however long the question list is. */}
      <DialogContent
        className={
          mode === "compare"
            ? "flex max-h-[85vh] flex-col gap-4 sm:max-w-2xl"
            : undefined
        }
      >
        <DialogHeader className="min-w-0">
          <DialogTitle>
            {mode === "compare" ? "Compare groups" : "Add slide"}
          </DialogTitle>
          <DialogDescription>
            {mode === "compare"
              ? "Lisää yhden dian per kysymys, jaettuna valitun muuttujan ryhmiin. Nykyiset kokonaistason diat säilyvät ennallaan."
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
  // The questions this variable actually splits — the only ones selectable.
  const selectable = questions.filter((q) => splits(q.qid)).map((q) => q.qid);
  const toggle = (qid: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(qid)) next.delete(qid);
      else next.add(qid);
      return next;
    });

  const chosen = questions.map((q) => q.qid).filter((q) => picked.has(q));

  return (
    <>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-y-auto">
      <div className="min-w-0 space-y-1.5">
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

      <div className="min-w-0 space-y-1.5">
        <div className="flex items-center justify-between gap-3">
          <Label className="text-xs font-medium text-muted-foreground">
            Questions
          </Label>
          {/* Only the questions this variable SPLITS can be selected, so
              "Select all" means all selectable ones — never a disabled row. */}
          {clf && !loading && selectable.length > 0 && (
            <div className="flex shrink-0 items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                disabled={picked.size === selectable.length}
                onClick={() => setPicked(new Set(selectable))}
              >
                Select all
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                disabled={picked.size === 0}
                onClick={() => setPicked(new Set())}
              >
                Select none
              </Button>
            </div>
          )}
        </div>
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
          <div className="w-full space-y-1 overflow-x-hidden rounded-md border p-2">
            {questions.map((q) => {
              const ok = splits(q.qid);
              return (
                <label
                  key={q.qid}
                  className={`flex w-full items-start gap-2 rounded p-1.5 text-xs ${
                    ok ? "cursor-pointer hover:bg-accent/50" : "opacity-50"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 shrink-0"
                    disabled={!ok}
                    checked={picked.has(q.qid)}
                    onChange={() => toggle(q.qid)}
                  />
                  {/* Question texts are long sentences, so they WRAP rather than
                      truncate — `truncate` sets white-space: nowrap, which made the
                      row expand past the dialog instead of shrinking to it.
                      min-w-0 lets the flex child shrink below its content width. */}
                  <span className="min-w-0 flex-1 break-words">
                    <span className="block">{q.text || q.qid}</span>
                    {!ok && (
                      <span className="block text-muted-foreground">
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

      </div>

      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>
          Back
        </Button>
        <Button disabled={!clf || chosen.length === 0} onClick={() => onSubmit(clf, chosen)}>
          {chosen.length
            ? `Add ${chosen.length} slide${chosen.length === 1 ? "" : "s"}`
            : "Add slides"}
        </Button>
      </DialogFooter>
    </>
  );
}
