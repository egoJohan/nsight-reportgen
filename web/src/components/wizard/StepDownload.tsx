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
import {
  useCancelRender,
  useRegroupedQuestions,
  useRenderReport,
  useRenderStatus,
} from "@/lib/queries";
import { downloadBlob, safeFileName } from "@/lib/download";
import { SlideGrid } from "@/components/wizard/SlideGrid";
import { PANEL_TITLE } from "@/lib/surfaces";

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
  const cancelRender = useCancelRender(caseId);
  // Server-side truth, not this tab's memory: whether a render is in progress
  // for THIS report right now, whether or not this session is the one that
  // started it. Polls only while it's running (see useRenderStatus).
  const { data: statusData } = useRenderStatus(caseId, reportId);
  const serverRendering = statusData?.rendering ?? false;
  const grouping = draft.grouping ?? { groups: [], singles: [] };
  const { data: questions } = useRegroupedQuestions(materialId, grouping);
  const questionMap = useMemo(() => {
    const m = new Map<string, Question>();
    (questions ?? []).forEach((q) => m.set(q.qid, q));
    return m;
  }, [questions]);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Fonts the template names that the render host could not supply. Not an
  // error — the deck rendered — but the typeface is not the customer's, and
  // this is the last screen before it gets sent to one.
  const [fontWarnings, setFontWarnings] = useState<string[]>([]);
  const [rendered, setRendered] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [downloading, setDownloading] = useState<"pdf" | "pptx" | null>(null);
  const pdfUrlRef = useRef<string | null>(null);
  // Tracks the LAST server-reported rendering state the reconciliation effect
  // below has accounted for. handleGenerate forces this to false once it has
  // recorded its own outcome (rendered/error/cancelled), so a stale poll
  // catching up afterwards does not re-run reconciliation over a render this
  // tab already knows the ending of.
  const wasServerRenderingRef = useRef(false);

  const fileBase = safeFileName(draft.name);
  // Slides unticked in Select are kept in the report but left OUT of the deck, so
  // Preview must show — and count — exactly what will be assembled.
  const deckCharts = useMemo(
    () => draft.charts.filter((c) => !c.excluded),
    [draft.charts]
  );
  const noCharts = deckCharts.length === 0;

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

  // Reconnecting to a render this tab didn't start (a reload mid-render, or a
  // render someone else kicked off): when the server-side status flips from
  // running to idle, go see what it left behind rather than staying on a
  // spinner that will never resolve itself. A preview that's now fetchable
  // means it finished; a 404 means it didn't (cancelled, failed, or a stale
  // in-flight state) — either way there is nothing left to wait for.
  useEffect(() => {
    const justStopped = wasServerRenderingRef.current && !serverRendering;
    wasServerRenderingRef.current = serverRendering;
    if (!justStopped) return;
    (async () => {
      try {
        const blob = await api.reports.previewPdf(caseId, reportId);
        setPreview(URL.createObjectURL(blob));
        setRendered(true);
        setCancelled(false);
      } catch {
        setCancelled(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverRendering, caseId, reportId]);

  function handleCancel() {
    cancelRender.mutate(reportId);
  }

  async function handleGenerate() {
    setError(null);
    setFontWarnings([]);
    setCancelled(false);
    setPreview(null);
    setRendered(false);
    try {
      const ok = await save();
      if (!ok) {
        setError("Could not save the report before rendering. Try again.");
        return;
      }
      const out = await render.mutateAsync({ reportId, materialId });
      setFontWarnings(out?.font_warnings ?? []);
      const blob = await api.reports.previewPdf(caseId, reportId);
      setPreview(URL.createObjectURL(blob));
      setRendered(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Rendering failed";
      // The explicit Cancel took effect (see routes_render.cancel_render) —
      // a clean stop, not a failure.
      if (msg === "Render cancelled") {
        setCancelled(true);
        return;
      }
      // 409 → someone/something else is already rendering this report.
      if (/409/.test(msg)) {
        setError("This report is already being generated — wait for it to finish.");
      } else if (/503/.test(msg) || /libreoffice/i.test(msg)) {
        // 503 → LibreOffice missing
        setError("Rendering charts needs LibreOffice on the server.");
      } else {
        setError(msg);
      }
    } finally {
      // Our own render's outcome is recorded above, and the server-side flag
      // is already gone (this call would not have resolved otherwise) even
      // though a stale poll may not have caught up yet. Mark it settled so
      // the reconciliation effect does not re-run over an outcome this tab
      // already knows, once that poll does catch up.
      wasServerRenderingRef.current = false;
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
  //
  // `pending` is true both while THIS tab is waiting on its own render call
  // and while the server reports one already running that this tab merely
  // reconnected to — a returning visitor sees "generating", not a stale
  // "not rendered yet".
  const pending = render.isPending || serverRendering;

  return (
    <div className="space-y-5">
      {/* The pohja is chosen on the tutkimus (or the asiakas), not per report:
          every report of a study is delivered in the same template, and a
          per-report override was one more place for them to disagree. */}
      {/* Action bar */}
      <div className="flex flex-col gap-4 rounded-xl border bg-card p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h3 className={PANEL_TITLE}>Generate deck</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Assemble {deckCharts.length}{" "}
            {deckCharts.length === 1 ? "slide" : "slides"} into a PowerPoint
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
            <Button variant="outline" className="min-w-[150px]" onClick={handleGenerate} disabled={noCharts}>
              <SparklesIcon className="size-4" />
              {rendered ? "Generate again" : "Generate deck"}
            </Button>
          )}
        </div>
      </div>

      {/* All slides — a final visual review. Click one to jump back to Design and
          edit it. Adding / removing / reordering lives in the Select step. */}
      {!noCharts && (
        <div className="rounded-xl border bg-card p-4">
          <h3 className={`${PANEL_TITLE} mb-3`}>
            All slides ({deckCharts.length})
          </h3>
          <SlideGrid
            charts={deckCharts}
            materialId={materialId}
            reportId={reportId}
            templateRef={draft.template_ref}
            grouping={grouping}
            questionMap={questionMap}
            activeRef={active}
            onSelect={(i) => {
              setActive(deckCharts[i].slide_id ?? null);
              onGoToDesign();
            }}
          />
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
          <span className="leading-snug">{error}</span>
        </div>
      )}

      {/* Fonts the host could not supply. Amber, not red: the deck rendered
          and is downloadable — it just is not in the customer's typeface. */}
      {fontWarnings.length > 0 && (
        <div className="flex items-start gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
          <AlertCircleIcon className="mt-0.5 size-4 shrink-0 text-amber-600" />
          <div className="leading-snug">
            <p className="font-medium">The preview and the PDF use a substitute font</p>
            <p className="mt-1 text-muted-foreground">
              The PowerPoint file still names the template's own font, so it
              looks right on a machine that has it installed.
            </p>
            {fontWarnings.map((w) => (
              <p key={w} className="mt-1 text-muted-foreground">
                {w}
              </p>
            ))}
          </div>
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
            <p className="text-sm font-medium">Generating the deck…</p>
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
      ) : null}
    </div>
  );
}
