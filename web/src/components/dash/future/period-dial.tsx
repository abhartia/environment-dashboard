"use client";

import { useRef } from "react";

import type { FuturePeriod } from "@/lib/dash/types";
import { cn } from "@/lib/utils";

/**
 * The big year, once the story reaches the future: it names a 20-year window ("2040–2059"), never a single year, and
 * moves between the published windows. Drag across it (it snaps to a window), or focus it and use the arrow keys; the
 * ticks under it show where the window sits among the others.
 */
export function PeriodDial({ periods, value, onChange }: { periods: FuturePeriod[]; value: string; onChange: (period: string, commit: boolean) => void }) {
  const index = Math.max(0, periods.findIndex((p) => p.period === value));
  const current = periods[index];
  // A drag in progress: where it began, and whether it has added its one step to the history yet.
  const drag = useRef<{ x: number; index: number; pushed: boolean } | null>(null);

  function step(by: number, commit: boolean) {
    const next = Math.min(periods.length - 1, Math.max(0, index + by));
    if (next !== index) onChange(periods[next].period, commit);
  }

  return (
    <div
      role="slider"
      tabIndex={0}
      aria-label="Which 20 years to show"
      aria-valuemin={0}
      aria-valuemax={periods.length - 1}
      aria-valuenow={index}
      aria-valuetext={`${current.from} to ${current.to}`}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight" || e.key === "ArrowUp") step(1, true);
        else if (e.key === "ArrowLeft" || e.key === "ArrowDown") step(-1, true);
        else if (e.key === "Home") onChange(periods[0].period, true);
        else if (e.key === "End") onChange(periods.at(-1)!.period, true);
        else return;
        e.preventDefault();
      }}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        drag.current = { x: e.clientX, index, pushed: false };
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d) return;
        // One window per 40 px of drag, snapping: the dial never rests between two windows. A drag is one step back
        // in the history, as one arrow key is: its first move adds the step, the rest replace it.
        const target = Math.min(periods.length - 1, Math.max(0, d.index + Math.round((e.clientX - d.x) / 40)));
        if (target === index) return;
        onChange(periods[target].period, !d.pushed);
        d.pushed = true;
      }}
      onPointerUp={() => {
        drag.current = null;
      }}
      onPointerCancel={() => (drag.current = null)}
      className="group flex cursor-ew-resize touch-none flex-col items-end rounded-md outline-none select-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="text-3xl leading-none font-black tracking-tighter whitespace-nowrap num sm:text-5xl">
        {current.from}–{current.to}
      </span>
      <span aria-hidden className="mt-1 flex gap-1">
        {periods.map((p, i) => (
          <span key={p.period} className={cn("h-1 w-5 rounded-full sm:w-7", i === index ? "bg-foreground" : "bg-border group-hover:bg-muted-foreground/40")} />
        ))}
      </span>
    </div>
  );
}
