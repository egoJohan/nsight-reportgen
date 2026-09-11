import { useEffect, useState } from "react";
import { PlusIcon, Trash2Icon, GlobeIcon } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { EMPTY, PANEL_PADDED, PANEL_TITLE } from "@/lib/surfaces";
import { useAccessSettings, useSetAccessSettings } from "@/lib/queries";
import { toRows, toStored } from "@/lib/domainAccess";
import type { DomainRow } from "@/lib/domainAccess";

/** Base UI's SelectValue renders the raw value unless the Root is told the
 *  labels, so "view" showed on the closed trigger instead of the sentence. */
const MODE_LABELS: Record<DomainRow["mode"], string> = {
  none: "No access",
  view: "View everything",
  edit: "Edit everything",
};

export default function DomainAccessTab() {
  const { data } = useAccessSettings();
  const save = useSetAccessSettings();
  const [rows, setRows] = useState<DomainRow[]>([]);
  const [seeded, setSeeded] = useState(false);

  useEffect(() => {
    if (seeded || !data) return;
    setRows(toRows(data));
    setSeeded(true);
  }, [data, seeded]);

  function edit(i: number, change: Partial<DomainRow>) {
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...change } : r)));
  }

  // Compare through the same conversion, so a domain the server stored in
  // another casing does not light Save up on a screen nobody touched.
  const pending = toStored(rows);
  const saved = toStored(toRows(data));
  const dirty = JSON.stringify(pending) !== JSON.stringify(saved);

  function persist() {
    save.mutate(
      { ...pending, default_grants: data?.default_grants ?? [] },
      {
        onSuccess: () => toast.success("Domains saved"),
        onError: (e) => toast.error(e instanceof Error ? e.message : "Could not save"),
      }
    );
  }

  return (
    <div className={PANEL_PADDED}>
      <h2 className={PANEL_TITLE}>Domains</h2>
      <p className="mb-4 max-w-3xl text-sm text-muted-foreground">
        Two separate things about an email domain.{" "}
        <strong>Sign in without an invitation</strong> decides who gets an account
        on their own. <strong>Access</strong> decides what those people may do,
        across every customer, including ones created later. Neither implies the
        other: a partner you invite by hand can still be given access, and letting
        a domain in grants nothing by itself. A grant on a single customer
        overrides the access here, which is how you narrow someone down.
      </p>

      {rows.length === 0 ? (
        <div className={EMPTY}>
          <GlobeIcon className="mx-auto size-8 text-muted-foreground" />
          <p className="mt-3 text-sm text-muted-foreground">
            No domains yet. Everyone needs an invitation, and nobody is granted
            anything by their email address.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center gap-3 pr-11 text-xs font-medium text-muted-foreground">
            <span className="flex-1">Domain</span>
            <span className="w-44 shrink-0">Sign in without an invitation</span>
            <span className="w-52 shrink-0">Access</span>
          </div>
          {rows.map((row, i) => (
            <div key={i} className="flex items-center gap-3">
              <Input
                value={row.domain}
                placeholder="nsight.fi"
                aria-label="Email domain"
                className="h-9 flex-1"
                onChange={(e) => edit(i, { domain: e.target.value })}
              />
              <div className="flex w-44 shrink-0 justify-center">
                {/* A Switch, matching the Admin toggle a tab away -- one
                    boolean per row is the same gesture in both places. */}
                <Switch
                  size="sm"
                  checked={row.signIn}
                  aria-label={`${row.domain || "This domain"} may sign in without an invitation`}
                  onCheckedChange={(v) => edit(i, { signIn: v })}
                />
              </div>
              <Select
                items={MODE_LABELS}
                value={row.mode}
                onValueChange={(v) => edit(i, { mode: v as DomainRow["mode"] })}
              >
                <SelectTrigger className="h-9 w-52 shrink-0" aria-label="Access">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(MODE_LABELS) as DomainRow["mode"][]).map((m) => (
                    <SelectItem key={m} value={m}>{MODE_LABELS[m]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="ghost"
                size="icon-sm"
                title="Remove this domain"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => setRows((rs) => rs.filter((_r, j) => j !== i))}
              >
                <Trash2Icon className="size-4" />
              </Button>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            setRows((rs) => [...rs, { domain: "", signIn: true, mode: "none" }])
          }
        >
          <PlusIcon className="size-4" />Add domain
        </Button>
        {dirty && (
          <Button size="sm" disabled={save.isPending} onClick={persist}>
            Save
          </Button>
        )}
      </div>
    </div>
  );
}
