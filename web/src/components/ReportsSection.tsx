import { useState } from "react";
import {
  FileTextIcon,
  PlusIcon,
  CopyIcon,
  Trash2Icon,
  Loader2Icon,
} from "lucide-react";
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
import { useQueryClient } from "@tanstack/react-query";
import { useWorkspace } from "@/lib/workspace";
import {
  useCreateReport,
  useDeleteReport,
  useQuestions,
  useReport,
  useCaseReports,
  useDuplicateReport,
  qk,
} from "@/lib/queries";
import { makeChart, normalizeSlots } from "@/lib/charts";
import { formatReportDate } from "@/lib/utils";
import { api } from "@/lib/api";
import { downloadBlob, safeFileName } from "@/lib/download";
import { EMPTY, PANEL, SECTION_TITLE } from "@/lib/surfaces";
import { Skeleton } from "@/components/ui/skeleton";

// A viewer's row has no status and no delete — a half-built report is the
// analyst's working state, not something to hand a viewer. PDF/PPTX download
// buttons take the trailing edge instead. This is a UI courtesy, not a
// security control: preview.pdf/.pptx are already guarded by read access
// (require_case, see routes_render.py), so a viewer fetching them directly
// works whether or not this button is on screen.
function DownloadButtons({ caseId, reportId, name }: {
  caseId: string;
  reportId: string;
  name: string;
}) {
  const [downloading, setDownloading] = useState<"pdf" | "pptx" | null>(null);
  const fileBase = safeFileName(name);

  async function handleDownload(kind: "pdf" | "pptx") {
    setDownloading(kind);
    try {
      const blob =
        kind === "pdf"
          ? await api.reports.previewPdf(caseId, reportId)
          : await api.reports.previewPptx(caseId, reportId);
      downloadBlob(blob, `${fileBase}.${kind}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div
      className="flex shrink-0 items-center gap-2"
      // Load-bearing: an editor's row IS clickable and opens the wizard, so
      // without this, downloading a deck would also open the report behind it.
      // (A viewer's row is not clickable, so there it is merely harmless.)
      onClick={(e) => e.stopPropagation()}
    >
      {/* Text, not icons: "PDF" and "PPTX" are the words people actually use
          for these files, and a glyph made you decode which was which. Both
          buttons are the same width so the pair reads as one control rather
          than two ragged ones, and the label is set in the UI's own font at a
          heavier weight with a little tracking — a file format is a short word
          that has to stay legible small. */}
      <Button
        variant="outline"
        size="sm"
        className="w-[4.25rem] shrink-0 font-semibold tracking-wide"
        disabled={downloading !== null}
        title={`Download ${fileBase}.pdf`}
        onClick={() => handleDownload("pdf")}
      >
        {downloading === "pdf" ? <Loader2Icon className="size-3.5 animate-spin" /> : "PDF"}
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="w-[4.25rem] shrink-0 font-semibold tracking-wide"
        disabled={downloading !== null}
        title={`Download ${fileBase}.pptx`}
        onClick={() => handleDownload("pptx")}
      >
        {downloading === "pptx" ? <Loader2Icon className="size-3.5 animate-spin" /> : "PPTX"}
      </Button>
    </div>
  );
}

// One report row — fetches the report doc to show its statistics. In edit
// mode it also shows a Draft/Empty status and opens the wizard on click; a
// viewer sees neither (see canEdit) and gets download buttons instead.
function ReportRow({
  caseId,
  report,
  canEdit,
  onOpen,
  onCopy,
  copyPending,
  onDelete,
}: {
  caseId: string;
  report: {
    id: string;
    name: string;
    createdAt?: string;
    renderedAt?: string;
    rendered?: boolean;
    rendering?: boolean;
  };
  canEdit: boolean;
  onOpen: (id: string) => void;
  onCopy: (id: string) => void;
  copyPending: boolean;
  onDelete: (id: string) => void;
}) {
  const { data: doc, isLoading } = useReport(caseId, report.id);
  const n = doc?.charts?.length ?? null;
  // Four states now. Empty -> no charts. Draft -> charts, no deck. Generated
  // -> a deck exists, which is exactly when it becomes downloadable and when
  // a viewer can see it at all. Generating -> a render is in progress right
  // now (server-side state, not this browser's memory — a render outlives
  // navigation and sign-out, so this list has to be able to say so to
  // whoever comes back and looks, not just the tab that started it).
  //
  // "Generating" is checked FIRST, ahead of even "Generated": a re-render of
  // an already-finished report is still in progress, and showing the OLD
  // "Generated" badge while a NEW one is being built claims a fact ("this is
  // what a viewer would get") that is not settled yet.
  const status = report.rendering
    ? "Generating…"
    : report.rendered
      ? "Generated"
      : n == null
        ? null
        : n === 0
          ? "Empty"
          : "Draft";
  const created = formatReportDate(report.createdAt);
  const base =
    n == null
      ? "Loading…"
      : n === 0
        ? "No charts yet"
        : `${n} chart${n === 1 ? "" : "s"} · ${n} slide${n === 1 ? "" : "s"}`;
  // A viewer is looking at a deliverable, not a work in progress: the useful
  // fact is when the deck was generated, not how many charts went into it.
  // ("No charts yet" on a finished, downloadable report reads as broken.)
  const generated = formatReportDate(report.renderedAt);
  const stat = canEdit
    ? created
      ? `${base} · ${created}`
      : base
    : generated
      ? `Generated ${generated}`
      : "Generated";

  return (
    <div
      className={
        "group flex items-center gap-3 px-4 py-3 transition-colors " +
        (canEdit ? "cursor-pointer hover:bg-muted/50" : "")
      }
      onClick={canEdit ? () => onOpen(report.id) : undefined}
    >
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
        <FileTextIcon className="size-4 text-primary" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{report.name}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {canEdit && isLoading ? "Loading…" : stat}
        </p>
      </div>
      {canEdit ? (
        <>
          {status && (
            <Badge
              variant="outline"
              className={
                status === "Generating…"
                  ? "shrink-0 border-blue-300 bg-blue-50 font-normal text-blue-700"
                  : status === "Generated"
                    ? "shrink-0 border-teal-300 bg-teal-50 font-normal text-teal-700"
                    : "shrink-0 border-muted-foreground/30 bg-muted font-normal text-muted-foreground"
              }
            >
              {status === "Generating…" && (
                <Loader2Icon className="size-3 animate-spin" />
              )}
              {status}
            </Badge>
          )}
          {/* An editor wants the deck too, without opening the wizard to get
              it. Only once one exists: the download routes 404 on a report
              that has never been rendered, and a button that cannot work is
              worse than no button. */}
          {report.rendered && (
            <DownloadButtons caseId={caseId} reportId={report.id} name={report.name} />
          )}
          <Button
            variant="ghost"
            size="icon-sm"
            title="Copy to a new report"
            aria-label="Copy to a new report"
            // Always visible, for the same reason as delete below.
            className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
            disabled={copyPending}
            onClick={(e) => {
              e.stopPropagation();
              onCopy(report.id);
            }}
          >
            {copyPending ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : (
              <CopyIcon className="size-4" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            // Always visible: a control that appears on hover cannot be found by
            // someone looking for it, and is invisible on a touch screen.
            className="shrink-0 text-muted-foreground transition-colors hover:text-destructive"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(report.id);
            }}
          >
            <Trash2Icon className="size-4" />
          </Button>
        </>
      ) : (
        <DownloadButtons caseId={caseId} reportId={report.id} name={report.name} />
      )}
    </div>
  );
}

/**
 * The Reports section: a list (like the Questions list) with "New report"
 * as the top row, then each report showing its status + statistics.
 *
 * A viewer (canEdit=false) sees none of that: no "New report" row, and only
 * FINISHED reports — a half-built report is the analyst's working state, not
 * a deliverable. "Finished" keys on the server's `rendered` flag (a render
 * has been stamped for the report's current content — see repository.py's
 * ReportRef.rendered) — the same flag the Generated badge keys on, so "what a
 * viewer can see" and "what the badge says" cannot drift apart.
 */
export default function ReportsSection({
  caseId,
  materialId,
  canEdit,
  onOpen,
}: {
  caseId: string;
  materialId: string | null;
  canEdit: boolean;
  onOpen: (reportId: string) => void;
}) {
  const qc = useQueryClient();
  const { workspace, addReport, removeReport } = useWorkspace(caseId);
  const createReport = useCreateReport(caseId);
  const deleteReport = useDeleteReport(caseId);
  const { data: questions } = useQuestions(materialId);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  // Reports come from the SERVER (visible to any user/device), newest first.
  // Enrich with this browser's locally-remembered createdAt when we have it.
  const { data: serverReports, isPending: reportsPending } = useCaseReports(caseId);
  const duplicateReport = useDuplicateReport(caseId);
  const [copyingId, setCopyingId] = useState<string | null>(null);
  const wsById = new Map(workspace.reports.map((r) => [r.id, r]));
  const allReports = (serverReports?.reports ?? []).map((r) => ({
    id: r.report_id,
    name: r.name,
    createdAt: wsById.get(r.report_id)?.createdAt,
    rendered: r.rendered,
    renderedAt: r.rendered_at,
    rendering: r.rendering,
  }));
  const orderedReports = canEdit ? allReports : allReports.filter((r) => r.rendered);

  function handleCreate() {
    const name = `Report ${orderedReports.length + 1}`;
    // Pre-select every question by default, in the material's own SAV/SPSS order
    // (the same order the survey uses) so the user doesn't have to hunt for the
    // right sequence. They remove the ones they don't want in the Select step.
    const charts = normalizeSlots(
      (questions ?? []).map((q) => makeChart(q.qid, q.suggested_chart_type))
    );
    createReport.mutate(
      { name, render_mode: "image", template_ref: "", charts },
      {
        onSuccess: ({ report_id }) => {
          addReport({
            id: report_id,
            name,
            // Only reachable via the "New report" row, which is editor-only
            // and requires materialId truthy — see the questions-driven
            // `disabled` above.
            materialId: materialId ?? undefined,
            createdAt: new Date().toISOString(),
          });
          qc.invalidateQueries({ queryKey: qk.caseReports(caseId) });
          onOpen(report_id);
        },
        onError: (e) => toast.error(`Could not create report: ${e.message}`),
      }
    );
  }

  /** "<name> (copy)", and "(copy 2)" if that is taken — copying twice must not
   *  leave two reports a person cannot tell apart. Names come from the list the
   *  user is looking at, so the suffix reflects what they can actually see. */
  function copyName(source: string): string {
    const taken = new Set(orderedReports.map((r) => r.name));
    const base = `${source} (copy)`;
    if (!taken.has(base)) return base;
    for (let i = 2; ; i += 1) {
      const next = `${source} (copy ${i})`;
      if (!taken.has(next)) return next;
    }
  }

  function handleCopy(id: string) {
    const source = orderedReports.find((r) => r.id === id);
    if (!source) return;
    setCopyingId(id);
    duplicateReport.mutate(
      { reportId: id, name: copyName(source.name) },
      {
        onSuccess: () => {
          // The server owns the copy; re-read the list rather than guessing
          // what it made, so the row shows the report that actually exists.
          qc.invalidateQueries({ queryKey: qk.caseReports(caseId) });
          setCopyingId(null);
          toast.success("Report copied");
        },
        onError: (e) => {
          setCopyingId(null);
          toast.error(`Copy failed: ${e.message}`);
        },
      }
    );
  }

  function handleDelete(id: string) {
    deleteReport.mutate(id, {
      onSuccess: () => {
        removeReport(id);
        qc.invalidateQueries({ queryKey: qk.caseReports(caseId) });
        setConfirmDelete(null);
        toast.success("Report deleted");
      },
      onError: (e) => {
        if (e instanceof Error && e.message.startsWith("404")) removeReport(id);
        qc.invalidateQueries({ queryKey: qk.caseReports(caseId) });
        setConfirmDelete(null);
        toast.error(`Delete failed: ${e.message}`);
      },
    });
  }

  return (
    <section>
      <div className="mb-3">
        <h2 className={SECTION_TITLE}>Reports</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {canEdit
            ? "Build chart reports from this case's survey data."
            : "Finished reports for this study."}
        </p>
      </div>

      {/* Placeholders while the reports are in flight. Rendering the empty
          state instead told a viewer there were no finished reports a moment
          before showing them several — an empty answer and an unanswered
          question are not the same thing. Three rows, pulsing, matching the
          customers and studies lists. */}
      {reportsPending ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg" />
          ))}
        </div>
      ) : !canEdit && orderedReports.length === 0 ? (
        <div className={EMPTY}>
          <FileTextIcon className="mx-auto size-8 text-muted-foreground" />
          <p className="mt-3 text-sm text-muted-foreground">
            No finished reports yet.
          </p>
        </div>
      ) : (
        <div className={`divide-y ${PANEL}`}>
          {/* Topmost row: create a new report. Editor-only — starting a
              report is the workbench, not something a viewer does. */}
          {canEdit && (
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
                <p className="text-sm font-medium">New report</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Pick questions and build charts
                </p>
              </div>
            </button>
          )}

          {orderedReports.map((r) => (
            <ReportRow
              key={r.id}
              caseId={caseId}
              report={r}
              canEdit={canEdit}
              onOpen={onOpen}
              onCopy={handleCopy}
              copyPending={duplicateReport.isPending && copyingId === r.id}
              onDelete={setConfirmDelete}
            />
          ))}
        </div>
      )}

      <Dialog
        open={!!confirmDelete}
        onOpenChange={(v) => !v && setConfirmDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this report?</DialogTitle>
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
