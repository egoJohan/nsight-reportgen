import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeftIcon, PencilIcon, CheckIcon, XIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import DataTab from "@/components/DataTab";
import ReportsSection from "@/components/ReportsSection";
import ReportWizard from "@/components/wizard/ReportWizard";
import { useCases, useRenameCase } from "@/lib/queries";
import { useWorkspace } from "@/lib/workspace";

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
  const materialId = workspace.materialId;
  const [openReportId, setOpenReportId] = useState<string | null>(null);

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
      {/* Back + heading */}
      <div className="mb-8">
        <Button
          variant="ghost"
          size="sm"
          className="mb-3 -ml-2 text-muted-foreground"
          onClick={() => navigate("/")}
        >
          <ArrowLeftIcon className="size-4" />
          All cases
        </Button>
        <CaseHeading caseId={id} name={currentCase?.name ?? id} />
        <p className="mt-1 font-mono text-xs text-muted-foreground">{id}</p>
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
    </div>
  );
}
