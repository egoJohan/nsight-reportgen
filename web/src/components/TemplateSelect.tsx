import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useTemplates } from "@/lib/queries";

/** Pick which of the asiakas's pohjat something renders with.
 *
 *  A dropdown, not the customer page's panel: here you are choosing one of a
 *  short list, not managing the list. Uploading, configuring and deleting stay
 *  on the asiakas's page, because the templates belong to the asiakas and are
 *  shared by every tutkimus under it.
 */
/** The "follow the level above" option. A sentinel rather than "", because an
 *  empty string is Base UI's "nothing selected" and would show the placeholder
 *  instead of naming what is inherited. */
const INHERIT = "__inherit__";

export default function TemplateSelect({
  customerId,
  value,
  onChange,
  inheritedId,
  disabled,
}: {
  customerId: string | undefined;
  /** Bound HERE, or "" when this level follows the one above it. */
  value: string;
  onChange: (templateId: string | null) => void;
  /** What applies when this level binds nothing — shown as the placeholder so
   *  the control says what is in effect rather than looking unset. */
  inheritedId?: string;
  disabled?: boolean;
}) {
  const { data: templates } = useTemplates(customerId);

  if (!customerId) return null;

  const inherited = templates?.find((t) => t.id === inheritedId);
  // A binding whose template the asiakas has deleted is no binding at all —
  // the backend already resolves past it, and the control has to agree or it
  // would show a selection that is not in effect.
  const bound = templates?.some((t) => t.id === value) ? value : "";
  const shown = bound || INHERIT;

  // Base UI renders the raw VALUE in the trigger unless it is given a map from
  // value to label — without this the box showed "tpl-62707de80f27".
  const labels: Record<string, string> = {
    [INHERIT]: inherited
      ? `Käytä yläpuolen asetusta (${inherited.name})`
      : "Käytä yläpuolen asetusta",
    ...Object.fromEntries((templates ?? []).map((t) => [t.id, t.name])),
  };

  return (
    <Select
      items={labels}
      value={shown}
      onValueChange={(v) => onChange(v === INHERIT ? null : v)}
      disabled={disabled || !templates?.length}
    >
      <SelectTrigger className="h-9 w-[16rem]">
        <SelectValue
          placeholder={
            templates?.length
              ? "Valitse pohja"
              : "Ei pohjia — lisää asiakkaan sivulla"
          }
        />
      </SelectTrigger>
      <SelectContent>
        {/* First, and the default: following the level above is a choice you
            can return to, not merely the absence of one. */}
        <SelectItem value={INHERIT}>{labels[INHERIT]}</SelectItem>
        {templates?.map((t) => (
          <SelectItem key={t.id} value={t.id}>
            {t.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
