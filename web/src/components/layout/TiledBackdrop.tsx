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
 */
export default function TiledBackdrop() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 -z-10 opacity-[0.13]"
      style={{
        backgroundImage: "url(/nsight-background.jpeg)",
        backgroundRepeat: "repeat",
        backgroundSize: "620px auto",
      }}
    />
  );
}
