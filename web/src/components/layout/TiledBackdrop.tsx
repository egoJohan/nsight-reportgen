/**
 * The tiled analytics-doodle backdrop, behind every page.
 *
 * Landing page only. On a working page it competes with tables, charts and
 * forms; on the landing page it is the sole decoration and fights nothing.
 *
 * The parent needs `relative isolate`. A negative-z child paints above its own
 * parent's background, but without a new stacking context it slides behind an
 * opaque ancestor further up and vanishes.
 */
export default function TiledBackdrop() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 -z-10 opacity-[0.22]"
      style={{
        backgroundImage: "url(/nsight-background.jpeg)",
        backgroundRepeat: "repeat",
        backgroundSize: "620px auto",
      }}
    />
  );
}
