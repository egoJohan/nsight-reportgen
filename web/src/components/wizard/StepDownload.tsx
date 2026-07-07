import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircleIcon,
  FileTextIcon,
  Loader2Icon,
  PresentationIcon,
  SparklesIcon,
  XIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Question, ReportDoc } from "@/lib/api";
import { useRegroupedQuestions, useRenderReport } from "@/lib/queries";
import { downloadBlob, safeFileName } from "@/lib/download";
import { SlideGrid } from "@/components/wizard/SlideGrid";

export default function StepDownload({
  caseId,
  reportId,
  materialId,
  draft,
  active,
  setActive,
  onGoToDesign,
  save,
}: {
  caseId: string;
  reportId: string;
  materialId: string;
  draft: ReportDoc;
  // The Preview grid highlights the current slide and, on click, selects it and
  // jumps back to Design to edit it (state owned by ReportWizard).
  active: string | null;
  setActive: (ref: string | null) => void;
  onGoToDesign: () => void;
  save: () => Promise<boolean>;
}) {
  const render = useRenderReport(caseId);
  const grouping = draft.grouping ?? { groups: [], singles: [] };
  const { data: questions } = useRegroupedQuestions(materialId, grouping);
  const questionMap = useMemo(() => {
    const m = new Map<string, Question>();
    (questions ?? []).forEach((q) => m.set(q.qid, q));
    return m;
  }, [questions]);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rendered, setRendered] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [downloading, setDownloading] = useState<"pdf" | "pptx" | null>(null);
  const pdfUrlRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fileBase = safeFileName(draft.name);
  const noCharts = draft.charts.length === 0;

  useEffect(
    () => () => {
      if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current);
    },
    []
  );

  function setPreview(url: string | null) {
    if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current);
    pdfUrlRef.current = url;
    setPdfUrl(url);
  }

  function handleCancel() {
    abortRef.current?.abort();
  }

  async function handleGenerate() {
    setError(null);
    setCancelled(false);
    setPreview(null);
    setRendered(false);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const ok = await save();
      if (!ok) {
        setError("Could not save the report before rendering. Try again.");
        return;
      }
      await render.mutateAsync({ reportId, materialId, signal: controller.signal });
      const blob = await api.reports.previewPdf(caseId, reportId);
      setPreview(URL.createObjectURL(blob));
      setRendered(true);
    } catch (e) {
      // The user cancelled — the request was aborted; treat as a clean stop.
      if (controller.signal.aborted || (e instanceof Error && e.name === "AbortError")) {
        setCancelled(true);
        return;
      }
      const msg = e instanceof Error ? e.message : "Render failed";
      // 503 → LibreOffice missing
      if (/503/.test(msg) || /libreoffice/i.test(msg)) {
        setError("Chart rendering requires LibreOffice on the server.");
      } else {
        setError(msg);
      }
    } finally {
      abortRef.current = null;
    }
  }

  async function handleDownload(kind: "pdf" | "pptx") {
    setDownloading(kind);
    try {
      const blob =
        kind === "pdf"
          ? await api.reports.previewPdf(caseId, reportId)
          : await api.reports.previewPptx(caseId, reportId);
      downloadBlob(blob, `${fileBase}.${kind}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(null);
    }
  }

  // Deck generation is DELIBERATE (a "Generate deck" click), not automatic on entering
  // this step — a full render can be very resource-heavy (a large deck of slides), so it
  // must never run just because the user navigated here.
  const pending = render.isPending;

  return (
    <div className="space-y-5">
      {/* All slides — a final visual review. Click one to jump back to Design and
          edit it. Adding / removing / reordering lives in the Select step. */}
      {!noCharts && (
        <div className="rounded-xl border bg-card p-4">
          <h3 className="mb-3 text-base font-semibold">
            All slides ({draft.charts.length})
          </h3>
          <SlideGrid
            charts={draft.charts}
            materialId={materialId}
            grouping={grouping}
            questionMap={questionMap}
            activeRef={active}
            onSelect={(i) => {
              setActive(draft.charts[i].question_ref);
              onGoToDesign();
            }}
          />
        </div>
      )}

      {/* Action bar */}
      <div className="flex flex-col gap-4 rounded-xl border bg-card p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h3 className="text-base font-semibold">Generate your deck</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Assemble {draft.charts.length}{" "}
            {draft.charts.length === 1 ? "slide" : "slides"} into a PowerPoint
            deck and PDF. Rendering can take a moment.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button
            variant="outline"
            disabled={!rendered || downloading !== null}
            onClick={() => handleDownload("pdf")}
          >
            {downloading === "pdf" ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : (
              <FileTextIcon className="size-4" />
            )}
            Download PDF
          </Button>
          <Button
            variant="outline"
            disabled={!rendered || downloading !== null}
            onClick={() => handleDownload("pptx")}
          >
            {downloading === "pptx" ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : (
              <PresentationIcon className="size-4" />
            )}
            Download PowerPoint
          </Button>
          {pending ? (
            <Button variant="outline" className="min-w-[150px]" onClick={handleCancel}>
              <XIcon className="size-4" /> Cancel
            </Button>
          ) : (
            <Button className="min-w-[150px]" onClick={handleGenerate} disabled={noCharts}>
              <SparklesIcon className="size-4" />
              {rendered ? "Regenerate deck" : "Generate deck"}
            </Button>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
          <span className="leading-snug">{error}</span>
        </div>
      )}

      {/* Cancelled */}
      {cancelled && !pending && (
        <div className="flex items-start gap-2 rounded-xl border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
          <XIcon className="mt-0.5 size-4 shrink-0" />
          <span className="leading-snug">
            Generation cancelled. Press “Generate deck” to run it again.
          </span>
        </div>
      )}

      {/* Preview area */}
      {pending ? (
        <div className="flex h-[640px] w-full flex-col items-center justify-center gap-4 rounded-xl border bg-muted/30 text-center">
          <Loader2Icon className="size-7 animate-spin text-primary" />
          <div>
            <p className="text-sm font-medium">Generating your deck…</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Rendering charts and assembling slides — this can take a moment.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={handleCancel}>
            <XIcon className="size-4" /> Cancel
          </Button>
        </div>
      ) : pdfUrl ? (
        <iframe
          src={pdfUrl}
          title="Report PDF preview"
          className="h-[640px] w-full rounded-xl border"
        />
      ) : (
        !error && (
          <div className="flex h-[640px] w-full flex-col items-center justify-center gap-4 rounded-xl border border-dashed bg-muted/20 text-center">
            <div className="flex size-12 items-center justify-center rounded-xl bg-muted">
              <PresentationIcon className="size-6 text-muted-foreground" />
            </div>
            <div className="max-w-sm">
              <p className="text-sm font-medium">
                {noCharts ? "No slides to render" : "Ready to generate"}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {noCharts
                  ? "Add and configure charts first — each becomes a slide."
                  : "Press Generate deck to render the slides into a PDF preview here, then download the PDF or PowerPoint."}
              </p>
            </div>
          </div>
        )
      )}
    </div>
  );
}
