import { useCallback, useEffect, useRef, useState } from "react";

/** Nearest ancestor (including el) that actually scrolls vertically. */
function scrollableAncestor(el: HTMLElement | null): HTMLElement | Window {
  let node: HTMLElement | null = el;
  while (node) {
    const style = getComputedStyle(node);
    const oy = style.overflowY;
    if ((oy === "auto" || oy === "scroll") && node.scrollHeight > node.clientHeight) {
      return node;
    }
    node = node.parentElement;
  }
  return window;
}

/**
 * Native HTML5 drag-and-drop list reordering with edge auto-scroll.
 *
 * Returns:
 *  - `dragIndex` / `overIndex` for rendering drag/drop affordances,
 *  - `containerRef` to attach to the list wrapper (locates the scroll parent),
 *  - `itemProps(i)` to spread onto each draggable row.
 *
 * While a drag is in progress, the pointer nearing the top/bottom of the
 * scrollable viewport auto-scrolls it, so a row can be dropped beyond the
 * currently visible window (REQ: "respecting also scrolling").
 */
export function useDragReorder(onReorder?: (from: number, to: number) => void) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  const containerRef = useRef<HTMLElement | null>(null);
  const pointerY = useRef(0);
  const rafRef = useRef<number | null>(null);

  // Edge auto-scroll loop, live only while dragging.
  useEffect(() => {
    if (dragIndex === null) return;
    const target = scrollableAncestor(containerRef.current);
    const onDocDragOver = (e: DragEvent) => {
      pointerY.current = e.clientY;
      e.preventDefault(); // allow drop
    };
    const tick = () => {
      const margin = 90; // px from edge that triggers scrolling
      const max = 18; // px per frame at the very edge
      let top: number, bottom: number;
      if (target instanceof Window) {
        top = 0;
        bottom = window.innerHeight;
      } else {
        const r = target.getBoundingClientRect();
        top = r.top;
        bottom = r.bottom;
      }
      const y = pointerY.current;
      let dy = 0;
      if (y < top + margin) dy = -Math.ceil(((top + margin - y) / margin) * max);
      else if (y > bottom - margin)
        dy = Math.ceil(((y - (bottom - margin)) / margin) * max);
      if (dy !== 0) {
        if (target instanceof Window) target.scrollBy(0, dy);
        else target.scrollTop += dy;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    document.addEventListener("dragover", onDocDragOver);
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      document.removeEventListener("dragover", onDocDragOver);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [dragIndex]);

  const end = useCallback(() => {
    setDragIndex(null);
    setOverIndex(null);
  }, []);

  const itemProps = useCallback(
    (i: number) => {
      if (!onReorder) return {};
      return {
        draggable: true,
        onDragStart: (e: React.DragEvent) => {
          setDragIndex(i);
          setOverIndex(i);
          e.dataTransfer.effectAllowed = "move";
          // Firefox requires data to be set for the drag to start.
          try {
            e.dataTransfer.setData("text/plain", String(i));
          } catch {
            /* ignore */
          }
        },
        onDragEnter: (e: React.DragEvent) => {
          if (dragIndex !== null) {
            e.preventDefault();
            setOverIndex(i);
          }
        },
        onDragOver: (e: React.DragEvent) => {
          if (dragIndex !== null) e.preventDefault();
        },
        onDrop: (e: React.DragEvent) => {
          e.preventDefault();
          if (dragIndex !== null && dragIndex !== i) onReorder(dragIndex, i);
          end();
        },
        onDragEnd: end,
      };
    },
    [onReorder, dragIndex, end]
  );

  return { dragIndex, overIndex, containerRef, itemProps };
}
