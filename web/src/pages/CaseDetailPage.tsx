import { useCallback, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { PencilIcon, CheckIcon, XIcon, Trash2Icon, Loader2Icon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import DataTab from "@/components/DataTab";
import ReportsSection from "@/components/ReportsSection";
import ReportWizard from "@/components/wizard/ReportWizard";
import {
  useCases,
  useRenameCase,
  useDeleteCase,
  useCaseMaterials,
} from "@/lib/queries";
import { useWorkspace, clearWorkspace } from "@/lib/workspace";

function CaseHeading({ caseId, name }: { caseId: string; name: string }) {
  const rename = useRenameCase();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);

  function save() {
    const next = draft.trim();
    if (!next || next === name) {
      setEditing(false);
      return;
    }
    rename.mutate(
      { caseId, name: next },
      {
        onSuccess: () => setEditing(false),
        onError: (e) => toast.error(`Rename failed: ${e.message}`),
      }
    );
  }

  if (editing) {
    return (
      <div className="flex items-center gap-2">
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") save();
            if (e.key === "Escape") setEditing(false);
          }}
          className="h-10 max-w-md text-lg font-semibold"
        />
        <Button size="icon-sm" onClick={save} disabled={rename.isPending}>
          <CheckIcon className="size-4" />
        </Button>
        <Button size="icon-sm" variant="ghost" onClick={() => setEditing(false)}>
          <XIcon className="size-4" />
        </Button>
      </div>
    );
  }

  return (
    <div className="group flex items-center gap-2">
      <h1 className="text-2xl font-semibold tracking-tight">{name}</h1>
      <Button
        size="icon-sm"
        variant="ghost"
        className="text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
        onClick={() => {
          setDraft(name);
          setEditing(true);
        }}
        title="Rename case"
      >
        <PencilIcon className="size-4" />
      </Button>
    </div>
  );
}

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: cases } = useCases();
  const currentCase = cases?.find((c) => c.id === id);
  const { workspace, removeReport } = useWorkspace(id ?? "");
  // The case→material link is server-side; fall back to it when this browser has
  // no local pointer (e.g. the case was created by someone else / another device).
  const { data: caseMaterials } = useCaseMaterials(id ?? null);
  const serverMaterialId = caseMaterials?.materials?.[0]?.material_id ?? null;
  const materialId = workspace.materialId ?? serverMaterialId;
  // The open report lives in the URL (?report=<id>) so the app-shell breadcrumb
  // row can show a close button for it.
  const [searchParams, setSearchParams] = useSearchParams();
  const openReportId = searchParams.get("report");
  const setOpenReportId = useCallback(
    (rid: string | null) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (rid) next.set("report", rid);
          else next.delete("report");
          return next;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteCase = useDeleteCase();

  function handleDelete() {
    if (!id) return;
    deleteCase.mutate(id, {
      onSuccess: () => {
        clearWorkspace(id);
        toast.success("Case deleted");
        navigate("/");
      },
      onError: (e) => toast.error(`Delete failed: ${e.message}`),
    });
  }

  if (!id) return null;

  // A report is open → the wizard takes over the whole page.
  if (openReportId && materialId) {
    return (
      <div className="mx-auto w-full max-w-6xl px-6 py-8">
        <ReportWizard
          key={openReportId}
          caseId={id}
          reportId={openReportId}
          materialId={materialId}
          onClose={() => setOpenReportId(null)}
          onMissing={() => {
            removeReport(openReportId);
            setOpenReportId(null);
            toast.error("That report no longer exists.");
          }}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      {/* Heading + delete */}
      <div className="mb-8 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <CaseHeading caseId={id} name={currentCase?.name ?? id} />
          <p className="mt-1 font-mono text-xs text-muted-foreground">{id}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0 text-muted-foreground hover:border-destructive/40 hover:text-destructive"
          onClick={() => setConfirmDelete(true)}
        >
          <Trash2Icon className="size-4" />
          Delete case
        </Button>
      </div>

      {!materialId ? (
        // No data yet (e.g. a legacy case): let the user import a SAV into it.
        <DataTab caseId={id} />
      ) : (
        <div className="space-y-10">
          <ReportsSection
            caseId={id}
            materialId={materialId}
            onOpen={setOpenReportId}
          />
          {/* Questions section */}
          <DataTab caseId={id} />
        </div>
      )}

      <Dialog open={confirmDelete} onOpenChange={(v) => !v && setConfirmDelete(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this case?</DialogTitle>
            <DialogDescription>
              This permanently removes “{currentCase?.name ?? id}”, its uploaded
              data, and its reports. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteCase.isPending}
            >
              {deleteCase.isPending && <Loader2Icon className="size-4 animate-spin" />}
              Delete case
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
