import { indicator } from "@/lib/data";
import { linePath, linear } from "@/lib/viz/scale";
import { periodToYear } from "@/lib/viz/period";

/**
 * A small trend line for an indicator's headline series (decorative: the sentence beside it carries the number).
 * dims picks one series of a multi-series indicator; the headline series is used by default.
 */
export function Sparkline({ id, dims, className }: { id: string; dims?: Record<string, string>; className?: string }) {
  const ind = indicator(id);
  const want = dims ?? ind.latest.dims;
  const obs = ind.observations.filter(
    (o) => o.entity === ind.headline_entity && o.value !== null && Object.entries(want).every(([k, v]) => o.dims[k] === v),
  );
  if (obs.length < 2) throw new Error(`Sparkline(${id}): fewer than two values`);
  const xs = obs.map((o) => periodToYear(o.period));
  const ys = obs.map((o) => o.value as number);
  const x = linear([Math.min(...xs), Math.max(...xs)], [2, 158]);
  const y = linear([Math.min(...ys), Math.max(...ys)], [46, 4]);
  const last = obs.length - 1;
  return (
    <svg viewBox="0 0 160 50" className={className} aria-hidden="true" focusable="false">
      <path d={linePath(xs.map((xv, i) => [x(xv), y(ys[i])] as const))} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" />
      <circle cx={x(xs[last])} cy={y(ys[last])} r={2.5} fill="currentColor" />
    </svg>
  );
}
