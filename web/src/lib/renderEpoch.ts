/** Which drawing of the pictures the editor holds.
 *
 *  A slide's picture is kept for as long as it is on screen, under a key made
 *  of what the chart asks for — and nothing about which server drew it. An
 *  editor left open across a deploy therefore went on showing pictures drawn by
 *  the code from before it: a chart fixed that morning reported as still
 *  broken. (Johan, 2026-09-11)
 *
 *  `/health` says which pictures the server draws (`render_identity`). When
 *  that changes from one known value to another, the epoch moves on; every
 *  picture key carries the epoch, so every slide is drawn again. The first
 *  answer after a page load is not a change — counting it would draw every
 *  slide of a report twice on opening it. */
export interface RenderEpoch {
  epoch: number;
  identity?: string;
}

export function nextRenderEpoch(prev: RenderEpoch, identity: string | undefined): RenderEpoch {
  if (!identity) return prev;                       // no answer: nothing known to have changed
  if (prev.identity === undefined) return { epoch: prev.epoch, identity };
  if (prev.identity === identity) return prev;
  return { epoch: prev.epoch + 1, identity };
}
