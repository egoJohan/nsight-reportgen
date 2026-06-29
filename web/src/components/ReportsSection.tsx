import { useState } from "react";
import { FileTextIcon, PlusIcon, Trash2Icon, Loader2Icon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Card } from "@/components/ui/card";
import { useWorkspace } from "@/lib/workspace";
import { useCreateReport, useDeleteReport } from "@/lib/queries";

/**
 * The Reports section of a case page: a "Create new report" tile first, then
 * the report list. Creating a report auto-names it and opens the wizard
 * immediately (via onOpen). No tabs, no name dialog.
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
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const reports = workspace.reports.filter(
    (r) => r.materialId === undefined || r.materialId === materialId
  );

  function handleCreate() {
    const name = `Report ${reports.length + 1}`;
    createReport.mutate(
      { name, render_mode: "image", template_ref: "", charts: [] },
      {
        onSuccess: ({ report_id }) => {
          addReport({ id: report_id, name, materialId });
          onOpen(report_id); // open the wizard immediately
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
      <h2 className="mb-3 text-sm font-medium tracking-wide text-muted-foreground uppercase">
        Reports
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {/* Topmost item: create a new report */}
        <button
          type="button"
          onClick={handleCreate}
          disabled={createReport.isPending}
          className="group flex items-center gap-3 rounded-xl border border-dashed bg-card/50 p-4 text-left transition-colors hover:border-primary/40 hover:bg-accent/40 disabled:opacity-60"
        >
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            {createReport.isPending ? (
              <Loader2Icon className="size-5 animate-spin" />
            ) : (
              <PlusIcon className="size-5" />
            )}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium">Create new report</p>
            <p className="text-xs text-muted-foreground">
              Pick questions and build charts
            </p>
          </div>
        </button>

        {reports.map((r) => (
          <Card
            key={r.id}
            className="group flex-row items-center justify-between gap-3 p-4 transition-colors hover:border-primary/30"
          >
            <button
              className="flex min-w-0 flex-1 items-center gap-3 text-left"
              onClick={() => onOpen(r.id)}
            >
              <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <FileTextIcon className="size-5 text-primary" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{r.name}</p>
                <p className="truncate font-mono text-xs text-muted-foreground">
                  {r.id}
                </p>
              </div>
            </button>
            <Button
              variant="ghost"
              size="icon-sm"
              className="shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive"
              onClick={() => setConfirmDelete(r.id)}
            >
              <Trash2Icon className="size-4" />
            </Button>
          </Card>
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
