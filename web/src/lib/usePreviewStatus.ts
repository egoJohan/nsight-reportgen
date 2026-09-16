import { useCallback, useSyncExternalStore } from "react";
import * as previewQueue from "./previewQueue";
import type { ProducerId, Status } from "./previewQueue";

/**
 * What the preview queue is doing to one slide, as React state.
 *
 * The components used to be told this by the wizard, through a `titlePending`
 * prop threaded down three levels — which meant the flag and the work could
 * disagree, and for a while they did: a stranded flag left a slide showing
 * "Generating title…" for ever. Now they ask the thing doing the work.
 */
export function usePreviewStatus(slideId: string): Partial<Record<ProducerId, Status>> {
  const subscribe = useCallback(
    (fn: () => void) => previewQueue.subscribe(fn),
    []
  );
  const get = useCallback(() => previewQueue.statusKeyOf(slideId), [slideId]);
  // A string, because useSyncExternalStore compares snapshots by identity and a
  // fresh object every render would loop for ever.
  const key = useSyncExternalStore(subscribe, get, get);
  return decode(key);
}

/** What this slide's last render said about itself — blank, or unlabelled.
 *
 *  Subscribed rather than read, because the row that shows the warning is not
 *  the slide the author is editing: nothing else re-renders the slide list when
 *  a preview lands, so a plain read would put the marker up whenever the list
 *  happened to render next, which for a slide nobody has touched is never.
 */
export function useChartFacts(slideId: string): previewQueue.ChartFacts {
  const subscribe = useCallback(
    (fn: () => void) => previewQueue.subscribe(fn),
    []
  );
  const get = useCallback(() => previewQueue.chartFactsOf(slideId), [slideId]);
  return useSyncExternalStore(subscribe, get, get);
}

/** True while this slide's headline is being written. */
export function useTitlePending(slideId: string): boolean {
  return usePreviewStatus(slideId).title === "running";
}

function decode(key: string): Partial<Record<ProducerId, Status>> {
  const out: Partial<Record<ProducerId, Status>> = {};
  for (const part of key.split(",")) {
    if (!part) continue;
    const [id, status] = part.split(":");
    out[id as ProducerId] = status as Status;
  }
  return out;
}
