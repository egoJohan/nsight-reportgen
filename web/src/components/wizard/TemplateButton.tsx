import { useState } from "react";
import { PaletteIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import TemplatePicker from "@/components/TemplatePicker";
import { useResolvedCase, useReportTemplate, useTemplateActions } from "@/lib/queries";

/** Compact template control for the wizard toolbar.
 *
 *  A full panel belongs on the customer and tutkimus pages, where choosing a
 *  template is the task. Here it is one of several things competing for a
 *  toolbar, so it shows the ACTIVE template's name and opens the picker on
 *  demand — the name is what an analyst needs at a glance ("am I on Attendo's
 *  pohja?"), not the whole list.
 */
export default function TemplateButton({
  caseId,
  reportId,
}: {
  caseId: string;
  reportId: string;
}) {
  const [open, setOpen] = useState(false);
  const { data: resolvedCase } = useResolvedCase(caseId);
  const customerId = resolvedCase?.customer_id;
  const { data: resolved } = useReportTemplate(customerId, caseId, reportId);
  const actions = useTemplateActions(customerId);

  if (!customerId) return null;

  const label = resolved?.name ?? "Pohja";
  const inherited = resolved && resolved.level !== "report";

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        title={
          inherited
            ? `Peritty (${resolved?.level}): ${label}`
            : `Asetettu tälle raportille: ${label}`
        }
      >
        <PaletteIcon className="size-4" />
        <span className="max-w-[14rem] truncate">{label}</span>
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Raportin esityspohja</DialogTitle>
            <DialogDescription>
              Valinta koskee vain tätä raporttia. Ilman valintaa käytetään
              tutkimuksen tai asiakkaan pohjaa.
            </DialogDescription>
          </DialogHeader>
          <TemplatePicker
            customerId={customerId}
            level="report"
            currentId={resolved?.level === "report" ? resolved.template_id : ""}
            inheritedFrom={inherited ? label : undefined}
            onBind={(tid) =>
              actions.bindReport.mutate({ caseId, reportId, templateId: tid })
            }
          />
          {resolved?.level === "pinned" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => actions.refreshReport.mutate({ caseId, reportId })}
            >
              Päivitä nykyiseen pohjaan
            </Button>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
