import { indicator } from "@/lib/data";
import { formatSigned } from "@/lib/format";

/** ColorBrewer RdBu (11 classes), colour-blind safe diverging: cooler blue, warmer red. */
const RDBU = ["#053061", "#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#f7f7f7", "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f"];

/** Diverging about the baseline (0): the coolest year is the darkest blue, the warmest the darkest red. */
function colour(anomaly: number, coolest: number, warmest: number): string {
  const t = anomaly < 0 ? -Math.min(1, anomaly / coolest) : Math.min(1, anomaly / warmest); // -1..1
  return RDBU[Math.round(((t + 1) / 2) * (RDBU.length - 1))];
}

/**
 * Warming stripes from a published annual anomaly series: one stripe per year, blue below the series' own baseline
 * (zero) and red above it; the darkest blue is the coolest year and the darkest red the warmest.
 * Design after Ed Hawkins' warming stripes (showyourstripes.info, CC BY 4.0); the numbers are the indicator's.
 */
export function WarmingStripes({ id, className }: { id: string; className?: string }) {
  const ind = indicator(id);
  const obs = ind.observations.filter((o) => o.entity === ind.headline_entity && o.value !== null);
  if (obs.length < 30) throw new Error(`WarmingStripes(${id}): only ${obs.length} annual values`);
  const values = obs.map((o) => o.value as number);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  if (lo >= 0 || hi <= 0) throw new Error(`WarmingStripes(${id}): needs years on both sides of the baseline`);
  const coolest = obs[values.indexOf(Math.min(...values))];
  const warmest = obs[values.indexOf(Math.max(...values))];
  const dec = ind.display.decimals;
  return (
    <figure className={className} data-stripes={id}>
      <svg
        viewBox={`0 0 ${obs.length} 1`}
        preserveAspectRatio="none"
        shapeRendering="crispEdges"
        className="block h-full w-full"
        role="img"
        aria-label={`Warming stripes, ${obs[0].period} to ${obs[obs.length - 1].period}: one stripe per year, blue cooler and red warmer than the ${ind.scope.baseline ?? "baseline"}. Coolest ${coolest.period} (${formatSigned(coolest.value as number, dec)} ${ind.unit.short}), warmest ${warmest.period} (${formatSigned(warmest.value as number, dec)} ${ind.unit.short}).`}
      >
        {obs.map((o, i) => (
          <rect key={o.period} x={i} y={0} width={1.05} height={1} fill={colour(o.value as number, lo, hi)} />
        ))}
      </svg>
    </figure>
  );
}
