import { useState } from "react";
import {
  DatabaseIcon,
  FileTextIcon,
  PlusIcon,
  Trash2Icon,
  Loader2Icon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import ReportWizard from "@/components/wizard/ReportWizard";

function EmptyNoMaterial({ onGoToData }: { onGoToData: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-muted">
        <DatabaseIcon className="size-7 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-semibold tracking-tight">
        Upload data first
      </h3>
      <p className="mt-2 max-w-xs text-sm leading-relaxed text-muted-foreground">
        Reports are built from a survey's curated questions. Add an SPSS file in
        the Data tab to get started.
      </p>
      <Button className="mt-5" onClick={onGoToData}>
        Go to Data tab
      </Button>
    </div>
  );
}

function NewReportDialog({
  open,
  onOpenChange,
  onCreate,
  pending,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreate: (name: string) => void;
  pending: boolean;
}) {
  const [name, setName] = useState("");
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) setName("");
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New report</DialogTitle>
          <DialogDescription>
            Give your report a name. You can add charts in the next step.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="report-name">Report name</Label>
          <Input
            id="report-name"
            autoFocus
            placeholder="e.g. Brand Tracker — Q4"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && name.trim()) onCreate(name.trim());
            }}
          />
        </div>
        <DialogFooter>
          <Button
            onClick={() => name.trim() && onCreate(name.trim())}
            disabled={!name.trim() || pending}
          >
            {pending && <Loader2Icon className="size-4 animate-spin" />}
            Create report
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function ReportsTab({
  caseId,
  onGoToData,
}: {
  caseId: string;
  onGoToData: () => void;
}) {
  const { workspace, addReport, removeReport } = useWorkspace(caseId);
  const createReport = useCreateReport(caseId);
  const deleteReport = useDeleteReport(caseId);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [openReportId, setOpenReportId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const materialId = workspace.materialId;

  if (!materialId) {
    return <EmptyNoMaterial onGoToData={onGoToData} />;
  }

  if (openReportId) {
    return (
      <ReportWizard
        key={openReportId}
        caseId={caseId}
        reportId={openReportId}
        materialId={materialId}
        onClose={() => setOpenReportId(null)}
        onMissing={() => {
          removeReport(openReportId);
          setOpenReportId(null);
          toast.error("That report no longer exists.");
        }}
      />
    );
  }

  function handleCreate(name: string) {
    createReport.mutate(
      {
        name,
        render_mode: "image",
        template_ref: "",
        charts: [],
      },
      {
        onSuccess: ({ report_id }) => {
          addReport({ id: report_id, name, materialId: materialId ?? undefined });
          setDialogOpen(false);
          setOpenReportId(report_id);
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
        // Only self-heal the workspace list on a genuine 404 (gone server-side).
        // A transient/network failure keeps the still-existing report listed.
        if (e instanceof Error && e.message.startsWith("404")) removeReport(id);
        setConfirmDelete(null);
        toast.error(`Delete failed: ${e.message}`);
      },
    });
  }

  // Scope to reports built on the current material. Legacy entries without a
  // materialId (persisted before scoping) are also shown — harmless.
  const reports = workspace.reports.filter(
    (r) => r.materialId === undefined || r.materialId === materialId
  );

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold">Reports</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Build chart reports from this case's survey data.
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <PlusIcon className="size-4" />
          New report
        </Button>
      </div>

      {reports.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-20 text-center">
          <div className="mb-4 flex size-12 items-center justify-center rounded-xl bg-muted">
            <FileTextIcon className="size-6 text-muted-foreground" />
          </div>
          <h3 className="text-base font-semibold">No reports yet</h3>
          <p className="mt-1.5 max-w-xs text-sm text-muted-foreground">
            Create your first report to start adding charts.
          </p>
          <Button className="mt-5" onClick={() => setDialogOpen(true)}>
            <PlusIcon className="size-4" />
            New report
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {reports.map((r) => (
            <Card
              key={r.id}
              className="group flex-row items-center justify-between gap-3 p-4 transition-colors hover:border-primary/30"
            >
              <button
                className="flex min-w-0 flex-1 items-center gap-3 text-left"
                onClick={() => setOpenReportId(r.id)}
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
      )}

      <NewReportDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreate={handleCreate}
        pending={createReport.isPending}
      />

      {/* Delete confirm */}
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
    </div>
  );
}
