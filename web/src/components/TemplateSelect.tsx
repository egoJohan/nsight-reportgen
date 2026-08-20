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
export default function TemplateSelect({
  customerId,
  value,
  onChange,
  inheritedId,
  disabled,
}: {
  customerId: string | undefined;
  /** Bound HERE, or "" when this level binds nothing of its own. */
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
  // Nothing bound here shows the inherited one, so the control always names the
  // pohja actually in use. The value stays "" underneath, so the binding is not
  // silently made specific just by looking at it.
  const shown = value || inherited?.id || "";

  // Base UI renders the raw VALUE in the trigger unless it is given a map from
  // value to label — without this the box showed "tpl-62707de80f27".
  const labels = Object.fromEntries((templates ?? []).map((t) => [t.id, t.name]));

  return (
    <Select
      items={labels}
      value={shown}
      onValueChange={(v) => onChange(v)}
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
        {templates?.map((t) => (
          <SelectItem key={t.id} value={t.id}>
            {t.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
