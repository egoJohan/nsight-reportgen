/**
 * The tiled analytics-doodle backdrop, behind every page.
 *
 * Rendered once inside SidebarInset rather than per page: it sits in the
 * non-scrolling content area, so it stays put while a long page scrolls over
 * it instead of sliding away with the content.
 *
 * The parent needs `isolate`. SidebarInset paints an opaque `bg-background`,
 * and while a negative-z child does paint above its OWN parent's background,
 * without a new stacking context it would slide behind an opaque ancestor
 * further up and vanish.
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
