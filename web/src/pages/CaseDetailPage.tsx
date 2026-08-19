import { useCallback, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { PencilIcon, CheckIcon, XIcon, Trash2Icon, Loader2Icon } from "lucide-react";
import { toast } from "sonner";
import { PAGE, PAGE_HEADER, PAGE_TITLE } from "@/lib/surfaces";
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
  useResolvedCase,
  useRenameCustomerCase,
  useTemplateActions,
  useDeleteCase,
  useCaseMaterials,
} from "@/lib/queries";
import { useWorkspace, clearWorkspace } from "@/lib/workspace";
import TemplateButton from "@/components/wizard/TemplateButton";

function CaseHeading({
  caseId,
  name,
  customerId,
}: {
  caseId: string;
  name: string;
  customerId?: string;
}) {
  const rename = useRenameCase();
  const renameInCustomer = useRenameCustomerCase(customerId);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);

  function save() {
    const next = draft.trim();
    if (!next || next === name) {
      setEditing(false);
      return;
    }
    // A case under a customer lives in the hierarchy store; the legacy rename
    // route would not find it.
    const mutation = customerId ? renameInCustomer : rename;
    mutation.mutate(
      { caseId, name: next },
      {
        onSuccess: () => setEditing(false),
        onError: (e) => toast.error(`Nimen muutos epäonnistui: ${e.message}`),
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
        <Button size="icon-sm" onClick={save} disabled={rename.isPending || renameInCustomer.isPending}>
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
      <h1 className={PAGE_TITLE}>{name}</h1>
      <Button
        size="icon-sm"
        variant="ghost"
        className="text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
        onClick={() => {
          setDraft(name);
          setEditing(true);
        }}
        title="Muuta tutkimuksen nimeä"
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
  // A case under a customer is not in the legacy /cases list, so resolve it by
  // id; without this the heading fell back to rendering the raw case id.
  const { data: resolved } = useResolvedCase(id);
  const templates = useTemplateActions(resolved?.customer_id);
  const legacyCase = cases?.find((c) => c.id === id);
  const caseName = resolved?.name ?? legacyCase?.name ?? "";
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
        toast.success("Tutkimus poistettu");
        // One level up — the asiakas whose tutkimus this was — not the landing
        // page. Deleting one study of several should leave you looking at the
        // rest of them. A pre-hierarchy case has no customer page to go to.
        navigate(resolved?.customer_id ? `/customers/${resolved.customer_id}` : "/");
      },
      onError: (e) => toast.error(`Poisto epäonnistui: ${e.message}`),
    });
  }

  if (!id) return null;

  // A report is open → the wizard takes over the whole page.
  if (openReportId && materialId) {
    return (
      <div className={PAGE}>
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
    <div className={PAGE}>
      {/* Heading + delete */}
      <div className={PAGE_HEADER}>
        <div className="min-w-0">
          <CaseHeading caseId={id} name={caseName} customerId={resolved?.customer_id} />
          <p className="mt-1 font-mono text-xs text-muted-foreground">{id}</p>
        </div>
        {/* Same compact control as the report toolbar: the pohja is a setting
            you check at a glance, not a panel that competes with the data. */}
        <div className="flex shrink-0 items-center gap-2">
          {id && <TemplateButton caseId={id} />}
          <Button
            variant="outline"
            size="sm"
            className="text-muted-foreground hover:border-destructive/40 hover:text-destructive"
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2Icon className="size-4" />
            Poista tutkimus
          </Button>
        </div>
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
            <DialogTitle>Poistetaanko tutkimus?</DialogTitle>
            <DialogDescription>
              Tämä poistaa pysyvästi tutkimuksen “{caseName || id}”, sen ladatun
              datan ja sen raportit. Toimintoa ei voi perua.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Peruuta
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteCase.isPending}
            >
              {deleteCase.isPending && <Loader2Icon className="size-4 animate-spin" />}
              Poista tutkimus
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
