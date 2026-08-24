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
import SensitiveTermsPanel from "@/components/SensitiveTermsPanel";
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
  useCaseTemplate,
} from "@/lib/queries";
import { useWorkspace, useClearWorkspace } from "@/lib/workspace";
import TemplateSelect from "@/components/TemplateSelect";

function CaseHeading({
  caseId,
  name,
  customerId,
  canEdit,
}: {
  caseId: string;
  name: string;
  customerId?: string;
  canEdit: boolean;
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
          className="max-w-md text-lg font-semibold"
        />
        <Button variant="outline" size="icon" onClick={save} disabled={rename.isPending || renameInCustomer.isPending}>
          <CheckIcon className="size-4" />
        </Button>
        <Button size="icon" variant="ghost" onClick={() => setEditing(false)}>
          <XIcon className="size-4" />
        </Button>
      </div>
    );
  }

  return (
    <div className="group flex items-center gap-2">
      <h1 className={PAGE_TITLE}>{name}</h1>
      {/* Renaming is a write. A viewer gets no affordance for it — the
          route would 403 anyway, but there is no reason to offer a control
          that only ever fails for them. */}
      {canEdit && (
        <Button
          size="icon-sm"
          variant="ghost"
          className="text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
          onClick={() => {
            setDraft(name);
            setEditing(true);
          }}
          title="Rename study"
        >
          <PencilIcon className="size-4" />
        </Button>
      )}
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
  // What this tutkimus actually renders with — the backend's own answer, which
  // walks case -> asiakas -> the asiakas's first template. Reading the
  // asiakas's explicit binding instead missed that last step, so a customer who
  // had uploaded a pohja but never bound one showed an empty dropdown while
  // rendering with it.
  const { data: caseTemplate } = useCaseTemplate(resolved?.customer_id, id);
  const legacyCase = cases?.find((c) => c.id === id);
  const caseName = resolved?.name ?? legacyCase?.name ?? "";
  // The one place this page asks "may I write here" — computed server-side
  // from may_write on "{customer_id}/{case_id}" (see routes_customers.py's
  // resolve_case), never from is_admin: admin is the right to manage users,
  // not a right to edit data. Defaults true while `resolved` is still
  // loading (and for a legacy pre-hierarchy case /resolve 404s on) so an
  // editor's page — the common case — renders exactly as it always has,
  // with nothing to wait on; a viewer sees the full editor UI hidden the
  // instant the answer comes back false.
  //
  // This is a UI courtesy, not a security boundary: every write route
  // (require_case_write) re-checks the same grant independently, so a
  // viewer who reaches a write action before this flag resolves — or who
  // calls the API directly — still gets 403.
  // Assume NOT editable until the server says otherwise. Defaulting to true
  // flashes delete buttons and the workbench at a viewer for one fetch, and
  // every one of those controls would 403 if clicked. Erring closed costs an
  // editor a moment of quiet; erring open shows people doors that are locked.
  const canEdit = resolved?.can_edit ?? false;
  const { workspace, removeReport } = useWorkspace(id ?? "");
  const clearWorkspace = useClearWorkspace();
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
        toast.success("Study deleted");
        // One level up — the asiakas whose tutkimus this was — not the landing
        // page. Deleting one study of several should leave you looking at the
        // rest of them. A pre-hierarchy case has no customer page to go to.
        navigate(resolved?.customer_id ? `/customers/${resolved.customer_id}` : "/");
      },
      onError: (e) => toast.error(`Delete failed: ${e.message}`),
    });
  }

  if (!id) return null;

  // A report is open → the wizard takes over the whole page. Editor-only:
  // the wizard IS the workbench (select questions, build charts, render),
  // so a viewer who lands on a stale `?report=` URL sees the normal
  // read-only page instead, not the tool that only ever 403s for them.
  if (canEdit && openReportId && materialId) {
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
          <CaseHeading caseId={id} name={caseName} customerId={resolved?.customer_id} canEdit={canEdit} />
          <p className="mt-1 font-mono text-xs text-muted-foreground">{id}</p>
        </div>
        {/* Choosing a template and deleting the study are both writes — a
            viewer gets neither control. */}
        {canEdit && (
          <div className="flex shrink-0 items-center gap-2">
            {/* The pohja this tutkimus renders with. Managing the LIST is the
                asiakas's page; here you choose from it. */}
            <TemplateSelect
              customerId={resolved?.customer_id}
              value={resolved?.template_id ?? ""}
              inheritedId={caseTemplate?.template_id}
              onChange={(templateId) =>
                templates.bindCase.mutate({ caseId: id, templateId })
              }
            />
            <Button
              variant="outline"
              size="sm"
              className="text-muted-foreground hover:border-destructive/40 hover:text-destructive"
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2Icon className="size-4" />Delete study</Button>
          </div>
        )}
      </div>

      {!canEdit ? (
        // A viewer never sees the workbench (DataTab: upload, questions,
        // curation) — only the finished-reports list, regardless of whether
        // a material happens to be attached.
        <ReportsSection
          caseId={id}
          materialId={materialId}
          canEdit={false}
          onOpen={setOpenReportId}
        />
      ) : !materialId ? (
        // No data yet (e.g. a legacy case): let the user import a SAV into it.
        <DataTab caseId={id} />
      ) : (
        <div className="space-y-10">
          {/* Above the reports on purpose: reports cannot be created until
              these are accepted, so the thing that unblocks the page should
              not be below the thing it blocks. */}
          <SensitiveTermsPanel materialId={materialId} canEdit />
          <ReportsSection
            caseId={id}
            materialId={materialId}
            canEdit
            onOpen={setOpenReportId}
          />
          {/* Questions section */}
          <DataTab caseId={id} />
        </div>
      )}

      <Dialog open={confirmDelete} onOpenChange={(v) => !v && setConfirmDelete(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this study?</DialogTitle>
            <DialogDescription>
              This permanently deletes the study “{caseName || id}”, the data
              imported into it, and its reports. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteCase.isPending}
            >
              {deleteCase.isPending && <Loader2Icon className="size-4 animate-spin" />}
              Delete study
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
