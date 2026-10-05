/**
 * The few scale helpers the server-rendered SVG figures need (instead of d3).
 */

export type Linear = ((x: number) => number) & {
  domain: readonly [number, number];
  range: readonly [number, number];
  /** Round-number ticks inside the domain, about `count` of them (steps of 1, 2 or 5 × 10^k). */
  ticks: (count?: number) => number[];
  invert: (y: number) => number;
};

function tickStep(lo: number, hi: number, count: number): number {
  const raw = Math.abs(hi - lo) / Math.max(1, count);
  let step = 10 ** Math.floor(Math.log10(raw));
  const err = raw / step;
  if (err >= Math.sqrt(50)) step *= 10;
  else if (err >= Math.sqrt(10)) step *= 5;
  else if (err >= Math.sqrt(2)) step *= 2;
  return step;
}

export function linear(domain: readonly [number, number], range: readonly [number, number]): Linear {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0;
  // A degenerate domain maps to the middle of the range.
  const scale = ((x: number) => (span === 0 ? (r0 + r1) / 2 : r0 + ((x - d0) / span) * (r1 - r0))) as Linear;
  Object.assign(scale, {
    domain,
    range,
    ticks: (count = 5) => {
      const lo = Math.min(d0, d1);
      const hi = Math.max(d0, d1);
      if (lo === hi) return [lo];
      const step = tickStep(lo, hi, count);
      const digits = Math.max(0, -Math.floor(Math.log10(step)));
      const out: number[] = [];
      for (let i = Math.ceil(lo / step); i * step <= hi + step * 1e-9; i++) out.push(Number((i * step).toFixed(digits)));
      return out;
    },
    invert: (y: number) => (r1 === r0 ? d0 : d0 + ((y - r0) / (r1 - r0)) * span),
  });
  return scale;
}

/** Round to 1 decimal place (SVG coordinates). */
export function r1(n: number): number {
  return Math.round(n * 10) / 10;
}

/** An SVG path through points; each null starts a new segment (a gap in the data). */
export function linePath(points: readonly (readonly [number, number] | null)[]): string {
  let d = "";
  let pen = false;
  for (const p of points) {
    if (p === null) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${r1(p[0])} ${r1(p[1])}`;
    pen = true;
  }
  return d;
}
