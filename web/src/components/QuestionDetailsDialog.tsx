import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Loader2Icon, AlertCircleIcon, TriangleAlertIcon, CircleXIcon } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useQuestionSummary, useSetQuestionLabel } from "@/lib/queries";
import type { QuestionSummary } from "@/lib/api";

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border bg-muted/30 px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm font-medium tabular-nums">{value}</p>
    </div>
  );
}

function Distribution({ s }: { s: QuestionSummary }) {
  const rows = s.distribution ?? [];
  if (rows.length === 0) return null;
  // Battery questions report a mean per category; everything else a percentage.
  const isMean = s.statistic === "mean";
  const val = (r: (typeof rows)[number]) => (isMean ? r.mean : r.pct) ?? 0;
  const max = Math.max(...rows.map(val), isMean ? 5 : 1);
  return (
    <div>
      <p className="mb-2 text-sm font-medium">
        {isMean ? "Mean rating per item" : "Response distribution"}
      </p>
      <div className="space-y-1.5">
        {rows.map((r, i) => (
          <div key={`${r.category}-${i}`} className="flex items-center gap-3">
            <div className="w-1/2 min-w-0 shrink-0 truncate text-sm" title={r.category}>
              {r.category}
            </div>
            <div className="relative h-5 flex-1 overflow-hidden rounded bg-muted">
              <div
                className="absolute inset-y-0 left-0 rounded bg-primary/80"
                style={{ width: `${(val(r) / max) * 100}%` }}
              />
            </div>
            <div className="w-24 shrink-0 text-right text-sm tabular-nums">
              {isMean
                ? r.mean != null
                  ? r.mean.toFixed(1)
                  : "—"
                : r.pct != null
                  ? `${r.pct.toFixed(0)} %`
                  : "—"}
              <span className="ml-1 text-xs text-muted-foreground">
                ({r.count ?? "—"})
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function QuestionDetailsDialog({
  materialId,
  qid,
  onOpenChange,
}: {
  materialId: string;
  qid: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { data: s, isLoading, isError } = useQuestionSummary(materialId, qid);
  const setLabel = useSetQuestionLabel(materialId);
  const [name, setName] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);
  // Seed the editor from the current (possibly already-renamed) question text.
  useEffect(() => {
    setName(s?.text ?? "");
  }, [s?.text, qid]);
  // Grow the editor to fit the whole (possibly long/multi-line) question. Runs
  // in a layout effect (measured after DOM update, before paint) and re-fits on
  // the next frame so the dialog's open-animation/layout has settled — so the
  // full question is guaranteed visible the moment the dialog opens.
  useLayoutEffect(() => {
    const el = taRef.current;
    if (!el) return;
    const fit = () => {
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    };
    fit();
    const raf = requestAnimationFrame(fit);
    return () => cancelAnimationFrame(raf);
  }, [name, s?.text, qid]);

  function saveName() {
    if (!qid) return;
    setLabel.mutate(
      { qid, label: name },
      {
        onSuccess: () => toast.success("Question name updated"),
        onError: (e) =>
          toast.error(
            `Rename failed: ${e instanceof Error ? e.message : "unknown error"}`
          ),
      }
    );
  }

  return (
    <Dialog open={!!qid} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] gap-0 overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="pr-6 text-left text-base leading-snug">
            {s?.text ?? "Question details"}
          </DialogTitle>
          <DialogDescription className="text-left font-mono text-xs">
            {qid}
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2Icon className="size-5 animate-spin" />
          </div>
        ) : isError || !s ? (
          <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4 text-sm text-destructive">
            <AlertCircleIcon className="size-4 shrink-0" />
            Couldn't load question details.
          </div>
        ) : (
          <div className="space-y-5 py-2">
            {/* Status flags — only shown when NOT everything-ok. */}
            {(s.chartable === false ||
              (s.missing_values && s.missing_values.length > 0)) && (
              <div className="flex flex-wrap gap-2">
                {s.chartable === false && (
                  <span className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700">
                    <CircleXIcon className="size-3.5" /> Not chartable
                  </span>
                )}
                {s.missing_values && s.missing_values.length > 0 && (
                  <span className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
                    <TriangleAlertIcon className="size-3.5" /> Has "Not answered" values
                  </span>
                )}
              </div>
            )}

            {/* Editable question name — shown above the chart in reports/deck. */}
            <div>
              <label className="text-sm font-medium">Question name</label>
              <p className="mb-1.5 text-xs text-muted-foreground">
                Shown above the chart in every report. Clear the field to restore
                the original.
              </p>
              <div className="flex items-start gap-2">
                <textarea
                  ref={taRef}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  rows={1}
                  className="flex-1 resize-y overflow-hidden rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
                <Button
                  size="sm"
                  className="shrink-0"
                  disabled={setLabel.isPending || name === (s.text ?? "")}
                  onClick={saveName}
                >
                  Save
                </Button>
              </div>
            </div>

            {/* Tags */}
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary" className="font-normal">
                {s.kind === "battery"
                  ? `Rating battery · ${s.variables.length}`
                  : s.kind === "multi"
                    ? `Multi-response · ${s.variables.length}`
                    : "Single"}
              </Badge>
              <Badge variant="outline" className="font-normal">
                {s.measurement}
              </Badge>
              {s.chartable === false ? (
                <Badge
                  variant="outline"
                  className="border-muted-foreground/30 bg-muted font-normal text-muted-foreground"
                >
                  Not chartable
                </Badge>
              ) : (
                s.suggested_chart_type && (
                  <Badge
                    variant="outline"
                    className="border-teal-300 bg-teal-50 font-normal text-teal-700"
                  >
                    Suggested: {s.suggested_chart_type.replace(/_/g, " ")}
                  </Badge>
                )
              )}
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-2">
              <Stat label="Respondents (n)" value={s.respondent_total} />
              <Stat label="Answered (base)" value={s.base_n ?? "—"} />
              <Stat
                label="Mean"
                value={s.mean != null ? s.mean.toFixed(2) : "—"}
              />
            </div>

            {/* Distribution */}
            <Distribution s={s} />

            {/* Value labels (codes) */}
            {s.value_labels.length > 0 && (
              <div>
                <p className="mb-2 text-sm font-medium">Value labels</p>
                <div className="max-h-40 space-y-0.5 overflow-y-auto rounded-lg border bg-muted/20 p-2">
                  {s.value_labels.map((v) => (
                    <div key={v.code} className="flex gap-3 px-1.5 py-0.5 text-sm">
                      <span className="w-14 shrink-0 text-right font-mono text-xs text-muted-foreground">
                        {v.code}
                      </span>
                      <span className="min-w-0 flex-1 truncate">{v.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Missing values */}
            {s.missing_values.length > 0 && (
              <div>
                <p className="mb-1 text-sm font-medium">
                  Non-response values{" "}
                  <span className="font-normal text-muted-foreground">
                    (excluded from the base by default)
                  </span>
                </p>
                <p className="mb-2 text-xs leading-snug text-muted-foreground">
                  Answer codes the data marks as a non-response — e.g. "Don't
                  know"/EOS, skipped, or not asked. Percentages are calculated
                  over valid answers; these can be shown as a "Not answered"
                  category per chart.
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {s.missing_values.map((m) => (
                    <Badge
                      key={m.code}
                      variant="outline"
                      className="border-amber-300 bg-amber-50 font-normal text-amber-700"
                    >
                      <span className="font-mono">{m.code}</span> · {m.label}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Variables */}
            <div>
              <p className="mb-1.5 text-sm font-medium">
                {s.variables.length === 1 ? "Variable" : "Variables"}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {s.variables.map((v) => (
                  <Badge key={v.name} variant="outline" className="font-mono font-normal" title={v.label}>
                    {v.name}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
