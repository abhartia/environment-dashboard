"use client";

import { useEffect, useRef, useState } from "react";

/**
 * An element's own size in pixels, kept current as it resizes, so a chart or map draws at its container's size (never a
 * fixed viewBox). Null until the first measurement; `min` keeps a collapsing box drawable.
 */
export function useSize<T extends Element>(min: { w: number; h: number } = { w: 50, h: 16 }) {
  const ref = useRef<T>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: Math.max(min.w, Math.round(e.contentRect.width)), h: Math.max(min.h, Math.round(e.contentRect.height)) }));
    ro.observe(el);
    return () => ro.disconnect();
  }, [min.w, min.h]);
  return { ref, size };
}
