/**
 * Claims in story prose ("the highest in the record", "warmer than any year before") are declared next to the story
 * and re-checked against the published data by vitest every time the data changes, so a refresh can never silently
 * make the text wrong (plan: "Latest, claims and cross-checks"). Pure functions over indicator JSON, no I/O.
 */
import type { Indicator, Observation } from "@/gen/hey-api/types.gen";
import { calendarPeriod } from "@/lib/format";

export type Ref = { indicator: string; entity?: string; period?: string; dims?: Record<string, string> };

export type ClaimCheck =
  /** `period` holds the highest value of the series (entity/dims as given, else the headline series). */
  | { kind: "argmax"; series: Omit<Ref, "period">; period: string }
  | { kind: "argmin"; series: Omit<Ref, "period">; period: string }
  /** Every value from `from` on is higher than the one before. */
  | { kind: "rising-every-period"; series: Omit<Ref, "period">; from: string }
  /** Value a is greater than value b. */
  | { kind: "greater"; a: Ref; b: Ref }
  /** Value a is greater than every value of another series (e.g. today's CO2 above the whole ice-core record). */
  | { kind: "exceeds-series"; a: Ref; series: Omit<Ref, "period"> }
  /** Value is within [min, max] (for "about" statements written as words). */
  | { kind: "between"; ref: Ref; min: number; max: number };

export type Claim = { text: string; check: ClaimCheck };

function series(ind: Indicator, ref: Omit<Ref, "period">): Observation[] {
  const entity = ref.entity ?? ind.headline_entity;
  const dims = ref.dims ?? ind.latest.dims;
  return ind.observations.filter(
    (o) => o.entity === entity && o.value !== null && Object.entries(dims).every(([k, v]) => o.dims[k] === v),
  );
}

function value(ind: Indicator, ref: Ref): number {
  const s = series(ind, ref);
  const period = ref.period ?? ind.latest.period;
  const hit = s.filter((o) => o.period === period);
  if (hit.length !== 1) throw new Error(`${ref.indicator}: ${hit.length} values for period ${period}`);
  return hit[0].value as number;
}

/** Returns null when the claim holds, else a sentence saying why it does not. */
export function evaluate(claim: Claim, load: (id: string) => Indicator): string | null {
  const c = claim.check;
  switch (c.kind) {
    case "argmax":
    case "argmin": {
      const s = series(load(c.series.indicator), c.series);
      const best = s.reduce((a, b) => ((c.kind === "argmax" ? (b.value as number) > (a.value as number) : (b.value as number) < (a.value as number)) ? b : a));
      return best.period === c.period ? null : `${claim.text}: the ${c.kind === "argmax" ? "highest" : "lowest"} value is now in ${best.period}, not ${c.period}`;
    }
    case "rising-every-period": {
      const s = series(load(c.series.indicator), c.series).filter((o) => calendarPeriod(o) >= c.from);
      for (let i = 1; i < s.length; i++) {
        if ((s[i].value as number) <= (s[i - 1].value as number)) return `${claim.text}: ${s[i].period} is not above ${s[i - 1].period}`;
      }
      return s.length > 1 ? null : `${claim.text}: fewer than two values from ${c.from}`;
    }
    case "greater": {
      const a = value(load(c.a.indicator), c.a);
      const b = value(load(c.b.indicator), c.b);
      return a > b ? null : `${claim.text}: ${a} is not greater than ${b}`;
    }
    case "exceeds-series": {
      const a = value(load(c.a.indicator), c.a);
      const s = series(load(c.series.indicator), c.series);
      const top = s.reduce((x, y) => ((y.value as number) > (x.value as number) ? y : x));
      return a > (top.value as number) ? null : `${claim.text}: ${a} is not above ${top.value} (${top.period})`;
    }
    case "between": {
      const v = value(load(c.ref.indicator), c.ref);
      return v >= c.min && v <= c.max ? null : `${claim.text}: ${v} is outside ${c.min}–${c.max}`;
    }
  }
}
