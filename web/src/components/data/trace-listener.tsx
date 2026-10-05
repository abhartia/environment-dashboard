"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

// The panel (Radix Popover/Drawer + TanStack Query) is fetched on the first click only, so no page ships it in its
// first-load JavaScript (pattern from gigabiome's mobile nav).
const TracePanel = dynamic(() => import("./trace-panel").then((m) => m.TracePanel), { ssr: false });

export type TraceTarget = { id: string; period: string; entity: string; anchor: HTMLElement; seq: number };

/**
 * Every <Num> is a link to its data page. With JavaScript, a plain click opens a short source panel instead; a
 * modified click (new tab) still follows the link.
 */
export function TraceListener() {
  const [target, setTarget] = useState<TraceTarget | null>(null);
  const seq = useRef(0);
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.("a[data-indicator]");
      if (!(a instanceof HTMLAnchorElement)) return;
      e.preventDefault();
      setTarget({
        id: a.dataset.indicator!,
        period: a.dataset.period ?? "",
        entity: a.dataset.entity ?? "",
        anchor: a,
        seq: ++seq.current,
      });
    }
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);
  return target ? <TracePanel key={target.seq} target={target} onClose={() => setTarget(null)} /> : null;
}
