import { useEffect, useRef, useState } from "react";
import {
  AlertCircleIcon,
  FileTextIcon,
  Loader2Icon,
  PresentationIcon,
  SparklesIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { ReportDoc } from "@/lib/api";
import { useRenderReport } from "@/lib/queries";
import { downloadBlob, safeFileName } from "@/lib/download";

export default function StepDownload({
  caseId,
  reportId,
  materialId,
  draft,
  save,
}: {
  caseId: string;
  reportId: string;
  materialId: string;
  draft: ReportDoc;
  save: () => Promise<boolean>;
}) {
  const render = useRenderReport(caseId);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rendered, setRendered] = useState(false);
  const [downloading, setDownloading] = useState<"pdf" | "pptx" | null>(null);
  const pdfUrlRef = useRef<string | null>(null);

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

  async function handleGenerate() {
    setError(null);
    setPreview(null);
    setRendered(false);
    try {
      const ok = await save();
      if (!ok) {
        setError("Could not save the report before rendering. Try again.");
        return;
      }
      await render.mutateAsync({ reportId, materialId });
      const blob = await api.reports.previewPdf(caseId, reportId);
      setPreview(URL.createObjectURL(blob));
      setRendered(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Render failed";
      // 503 → LibreOffice missing
      if (/503/.test(msg) || /libreoffice/i.test(msg)) {
        setError("Chart rendering requires LibreOffice on the server.");
      } else {
        setError(msg);
      }
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

  const pending = render.isPending;

  return (
    <div className="space-y-5">
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
          <Button onClick={handleGenerate} disabled={pending || noCharts}>
            {pending ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : (
              <SparklesIcon className="size-4" />
            )}
            {rendered ? "Regenerate deck" : "Generate deck"}
          </Button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
          <span className="leading-snug">{error}</span>
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
