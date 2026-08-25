/**
 * What to call a study, given the file it was made of.
 *
 * A new study starts with a file, not with a name — nobody opens nSight to
 * type a title, they open it because they have a data set. So the name is
 * derived, and only corrected later if the derived one is wrong.
 *
 * The SAV's own study label wins where there is one: it is what the researcher
 * typed into SPSS, and it usually reads like a study ("Hoivapalvelut 2026")
 * where the file name reads like a file ("q4_final_v3"). It is not always
 * present, and SPSS often fills it with the export's own file name, which is
 * no information at all.
 */
const EXT = /\.(sav|zsav)$/i;

export const FALLBACK_STUDY_NAME = "Untitled study";

export function studyNameFrom(
  fileName: string,
  fileLabel: string | null | undefined
): string {
  const base = (fileName ?? "").replace(EXT, "").trim();
  const label = (fileLabel ?? "").trim();
  // A label that is just the file name again tells us nothing, and applying it
  // would show up as a rename that changed nothing.
  const labelIsEcho =
    label.replace(EXT, "").trim().toLowerCase() === base.toLowerCase();
  if (label && !labelIsEcho) return label;
  return base || FALLBACK_STUDY_NAME;
}
