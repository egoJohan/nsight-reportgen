import { useState } from "react";
import { FileTextIcon, PlusIcon, Trash2Icon, Loader2Icon } from "lucide-react";
import { toast } from "sonner";
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
import { useWorkspace } from "@/lib/workspace";
import {
  useCreateReport,
  useDeleteReport,
  useQuestions,
  useReport,
} from "@/lib/queries";
import { makeChart, normalizeSlots } from "@/lib/charts";

// One report row — fetches the report doc to show its status + statistics.
function ReportRow({
  caseId,
  report,
  onOpen,
  onDelete,
}: {
  caseId: string;
  report: { id: string; name: string };
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const { data: doc, isLoading } = useReport(caseId, report.id);
  const n = doc?.charts?.length ?? null;
  const status = n == null ? null : n === 0 ? "Empty" : "Draft";
  const stat =
    n == null
      ? "Loading…"
      : n === 0
        ? "No charts yet"
        : `${n} chart${n === 1 ? "" : "s"} · ${n} slide${n === 1 ? "" : "s"}`;

  return (
    <div
      className="group flex cursor-pointer items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/50"
      onClick={() => onOpen(report.id)}
    >
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
        <FileTextIcon className="size-4 text-primary" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{report.name}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {isLoading ? "Loading…" : stat}
        </p>
      </div>
      {status && (
        <Badge
          variant="outline"
          className={
            status === "Empty"
              ? "shrink-0 border-muted-foreground/30 bg-muted font-normal text-muted-foreground"
              : "shrink-0 border-teal-300 bg-teal-50 font-normal text-teal-700"
          }
        >
          {status}
        </Badge>
      )}
      <Button
        variant="ghost"
        size="icon-sm"
        className="shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(report.id);
        }}
      >
        <Trash2Icon className="size-4" />
      </Button>
    </div>
  );
}

/**
 * The Reports section: a list (like the Questions list) with "Create new report"
 * as the top row, then each report showing its status + statistics.
 */
export default function ReportsSection({
  caseId,
  materialId,
  onOpen,
}: {
  caseId: string;
  materialId: string;
  onOpen: (reportId: string) => void;
}) {
  const { workspace, addReport, removeReport } = useWorkspace(caseId);
  const createReport = useCreateReport(caseId);
  const deleteReport = useDeleteReport(caseId);
  const { data: questions } = useQuestions(materialId);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const reports = workspace.reports.filter(
    (r) => r.materialId === undefined || r.materialId === materialId
  );

  function handleCreate() {
    const name = `Report ${reports.length + 1}`;
    // Pre-select every question by default: seed the report with a chart per
    // question (in the questions' natural order). The user removes the ones
    // they don't want in the Select step.
    const charts = normalizeSlots(
      (questions ?? []).map((q) => makeChart(q.qid, q.suggested_chart_type))
    );
    createReport.mutate(
      { name, render_mode: "image", template_ref: "", charts },
      {
        onSuccess: ({ report_id }) => {
          addReport({ id: report_id, name, materialId });
          onOpen(report_id);
        },
        onError: (e) => toast.error(`Could not create report: ${e.message}`),
      }
    );
  }

  function handleDelete(id: string) {
    deleteReport.mutate(id, {
      onSuccess: () => {
        removeReport(id);
        setConfirmDelete(null);
        toast.success("Report deleted");
      },
      onError: (e) => {
        if (e instanceof Error && e.message.startsWith("404")) removeReport(id);
        setConfirmDelete(null);
        toast.error(`Delete failed: ${e.message}`);
      },
    });
  }

  return (
    <section>
      <div className="mb-3">
        <h2 className="text-base font-semibold">Reports</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Build chart reports from this case's survey data.
        </p>
      </div>

      <div className="divide-y overflow-hidden rounded-xl border">
        {/* Topmost row: create a new report */}
        <button
          type="button"
          onClick={handleCreate}
          disabled={createReport.isPending || !questions}
          className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-accent/50 disabled:opacity-60"
        >
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            {createReport.isPending ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : (
              <PlusIcon className="size-4" />
            )}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium">Create new report</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Pick questions and build charts
            </p>
          </div>
        </button>

        {reports.map((r) => (
          <ReportRow
            key={r.id}
            caseId={caseId}
            report={r}
            onOpen={onOpen}
            onDelete={setConfirmDelete}
          />
        ))}
      </div>

      <Dialog
        open={!!confirmDelete}
        onOpenChange={(v) => !v && setConfirmDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete report?</DialogTitle>
            <DialogDescription>
              This permanently removes the report and its charts. This cannot be
              undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => confirmDelete && handleDelete(confirmDelete)}
              disabled={deleteReport.isPending}
            >
              {deleteReport.isPending && (
                <Loader2Icon className="size-4 animate-spin" />
              )}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
