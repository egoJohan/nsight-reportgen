/**
 * The tiled analytics-doodle backdrop.
 *
 * Painted once, behind the main content pane, so every page gets it — it used
 * to be the landing page's alone. That means it now sits under tables, charts
 * and forms, which is why it is fainter than it was: at the old 0.22 it read as
 * texture competing with the content, and the content has to win.
 *
 * The parent needs `relative isolate`. A negative-z child paints above its own
 * parent's background, but without a new stacking context it slides behind an
 * opaque ancestor further up and vanishes.
 *
 * `opacity` is a prop, not baked in, because the login screen is the inverse
 * case: no table or chart to compete with, one small card floating on an
 * otherwise empty page — so the backdrop can carry real weight there. 0.13
 * stays the default so every existing caller (which never passes it) is
 * unchanged.
 */
export default function TiledBackdrop({ opacity = 0.13 }: { opacity?: number }) {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 -z-10"
      style={{
        opacity,
        backgroundImage: "url(/nsight-background.jpeg)",
        backgroundRepeat: "repeat",
        backgroundSize: "620px auto",
      }}
    />
  );
}
