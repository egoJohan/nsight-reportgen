/**
 * The one list of terms the panel shows.
 *
 * Three sources feed it and they are not interchangeable: what the study's
 * structure PROPOSED, what somebody has already ACCEPTED, and what somebody
 * has just TYPED in this session. The third is the one that got missed — a
 * typed term went straight into the ticked set and never into the rendered
 * list, so it disappeared at the moment of adding and the only way to learn it
 * had registered was to save and reload.
 *
 * Order is first-seen, so the list does not reshuffle under the cursor while
 * somebody is adding several names.
 */
export function mergeTerms(
  proposed: readonly string[] | null | undefined,
  accepted: readonly string[] | null | undefined,
  added: readonly string[] | null | undefined
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of [...(proposed ?? []), ...(accepted ?? []), ...(added ?? [])]) {
    const term = (raw ?? "").trim();
    if (!term) continue;
    // Case- and padding-insensitive, because "attendo" typed by hand is the
    // same company as the proposed "Attendo" — rendering both would give one
    // name two chips that disagree about whether it is ticked.
    const key = term.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(term);
  }
  return out;
}
