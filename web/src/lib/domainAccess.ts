import type { AccessSettings, AllowedDomain, DomainAccess } from "@/lib/api";

/** A domain as the admin screen edits it: two INDEPENDENT answers about the
 *  same domain.
 *
 *  `signIn` — may people on this domain get an account without an invitation?
 *  `mode`   — what are they owed, across every customer?
 *
 *  Neither implies the other. A partner whose people are all invited by hand
 *  can still be owed access to everything; a domain allowed to sign itself in
 *  can be owed nothing. They were one control, and one control could not say
 *  either of those things. (Johan, 2026-09-11) */
export type DomainRow = {
  domain: string;
  signIn: boolean;
  mode: "none" | "view" | "edit";
};

type Stored = { allowed_domains: (string | AllowedDomain)[]; domain_access: DomainAccess[] };

function clean(value: string | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function nameOf(entry: string | AllowedDomain): string {
  return clean(typeof entry === "string" ? entry : entry.domain);
}

export function toRows(value: AccessSettings | undefined): DomainRow[] {
  const rows: DomainRow[] = [];
  const at = new Map<string, DomainRow>();
  const add = (domain: string): DomainRow => {
    let row = at.get(domain);
    if (!row) {
      row = { domain, signIn: false, mode: "none" };
      at.set(domain, row);
      rows.push(row);
    }
    return row;
  };

  for (const entry of value?.allowed_domains ?? []) {
    const domain = nameOf(entry);
    if (!domain) continue;
    const row = add(domain);
    row.signIn = true;
    // A mode here is what the screen that had ONE list wrote. It meant admit
    // AND grant, so it keeps meaning that; `domain_access` below overrides it.
    if (typeof entry !== "string" && entry.mode) row.mode = entry.mode;
  }
  for (const entry of value?.domain_access ?? []) {
    const domain = clean(entry.domain);
    if (!domain) continue;
    add(domain).mode = entry.mode;
  }
  return rows;
}

export function toStored(rows: DomainRow[]): Stored {
  const out: Stored = { allowed_domains: [], domain_access: [] };
  for (const row of rows) {
    const domain = clean(row.domain);
    if (!domain) continue;
    // Bare strings only: writing a mode back into the sign-in list would put
    // the two questions in one field again, which is what this undoes.
    if (row.signIn) out.allowed_domains.push(domain);
    if (row.mode !== "none") out.domain_access.push({ domain, mode: row.mode });
  }
  return out;
}
