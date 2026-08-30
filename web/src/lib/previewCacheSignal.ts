/**
 * "The rendered previews were just thrown away."
 *
 * Said by the Clear cache button, heard by the report wizard.
 *
 * The two cannot talk directly and should not: the button lives in the app
 * shell, which knows a report is open and nothing else, while the decision the
 * requirement actually states — re-render only if the author is LOOKING at the
 * pictures, on Design or Preview — needs the wizard's own step, which the shell
 * has no business knowing. So the shell announces the fact and the wizard
 * decides what it means.
 *
 * A counter rather than an event payload, so `useSyncExternalStore` can compare
 * snapshots by identity and a listener that mounts late still sees that
 * something happened.
 */
let generation = 0;
const listeners = new Set<() => void>();

/** The cache was cleared. */
export function noteCacheCleared() {
  generation += 1;
  for (const fn of listeners) fn();
}

export function subscribeCacheCleared(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** How many times it has been cleared this session. */
export function cacheClearedGeneration(): number {
  return generation;
}

export function __resetForTest() {
  generation = 0;
  listeners.clear();
}
