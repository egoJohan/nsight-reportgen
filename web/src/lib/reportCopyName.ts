/** The name a copied report gets.
 *
 * "<name> (copy)", and "(copy 2)", "(copy 3)"… when those are taken — copying
 * twice must never leave two rows a person cannot tell apart. `existing` is the
 * names the user can actually see in that case, so the suffix reflects the list
 * in front of them rather than the whole store.
 *
 * Shared because there are two ways to copy a report — the button in the reports
 * list and the one beside "Close report" in the open report's header — and a
 * name that depended on which one you used would be a bug nobody would think to
 * look for.
 */
export function reportCopyName(source: string, existing: Iterable<string>): string {
  const taken = new Set(existing);
  const base = `${source} (copy)`;
  if (!taken.has(base)) return base;
  for (let i = 2; ; i += 1) {
    const next = `${source} (copy ${i})`;
    if (!taken.has(next)) return next;
  }
}
