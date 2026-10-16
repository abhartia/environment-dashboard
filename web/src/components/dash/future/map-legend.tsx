"use client";

import { formatValue } from "@/lib/format";
import type { FutureMeasure } from "@/lib/dash/types";

import type { ColourScale } from "./colour";

/**
 * The map's key: the colour ramp as a bar with readable values along it (placed as the colours are, so on a
 * square-root scale the low counts get room), the unit, the hatch that means no value, and the grey of a disputed area.
 */
export function MapLegend({ measure, scale, hatch }: { measure: FutureMeasure; scale: ColourScale; hatch: string }) {
  // Ticks a whole unit apart or more read as whole numbers; finer ones (warming in halves of a degree) keep one decimal.
  const decimals = scale.ticks.length > 1 && scale.ticks[1] - scale.ticks[0] < 1 ? 1 : 0;
  const gradient = `linear-gradient(to right, ${scale.stops.join(", ")})`;
  return (
    <div data-probe role="group" className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-muted-foreground sm:text-[11px]" aria-label={`Map key: ${measure.unitLabel}`}>
      <div className="flex items-center gap-2">
        <div className="relative w-40 pb-3.5 sm:w-56">
          <div className="h-2 rounded-full" style={{ background: gradient }} />
          {scale.ticks.map((t) => (
            <span key={t} className="absolute top-2.5 -translate-x-1/2 num" style={{ left: `${scale.position(t) * 100}%` }}>
              {formatValue(t, decimals)}
            </span>
          ))}
        </div>
        <span className="font-medium text-foreground">{measure.unit}</span>
      </div>
      <span className="flex items-center gap-1">
        <svg width="12" height="10" aria-hidden>
          <rect width="12" height="10" fill={`url(#${hatch})`} stroke="var(--border)" />
        </svg>
        No data
      </span>
      <span className="flex items-center gap-1">
        <span className="h-2.5 w-3 border border-dashed border-muted-foreground bg-muted" />
        Disputed
      </span>
    </div>
  );
}
