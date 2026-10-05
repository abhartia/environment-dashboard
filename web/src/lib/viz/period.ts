/**
 * ISO 8601 periods as decimal years for chart x positions: a year sits at its middle, a month at its middle, a day
 * at its middle, a range at its midpoint. "2025" -> 2025.5, "2026-08" -> 2026.625 (approximately; months are
 * treated as twelfths of a year), "2012/2021" -> 2017.0.
 */
export function periodToYear(period: string): number {
  if (period.includes("/")) {
    const [a, b] = period.split("/");
    return (periodStart(a) + periodEnd(b)) / 2;
  }
  return (periodStart(period) + periodEnd(period)) / 2;
}

function parts(period: string): [number, number | null, number | null] {
  const m = period.match(/^(-?\d{4,})(?:-(\d{2})(?:-(\d{2}))?)?$/);
  if (!m) throw new Error(`not an ISO 8601 period: ${period}`);
  return [Number(m[1]), m[2] ? Number(m[2]) : null, m[3] ? Number(m[3]) : null];
}

function daysIn(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function periodStart(period: string): number {
  const [y, mo, d] = parts(period);
  if (mo === null) return y;
  if (d === null) return y + (mo - 1) / 12;
  return y + (mo - 1) / 12 + (d - 1) / daysIn(y, mo) / 12;
}

function periodEnd(period: string): number {
  const [y, mo, d] = parts(period);
  if (mo === null) return y + 1;
  if (d === null) return y + mo / 12;
  return y + (mo - 1) / 12 + d / daysIn(y, mo) / 12;
}

/** Any observation's time as a decimal year: its period's midpoint, or for an age-dated value the year 1950 - age. */
export function timeToYear(t: { period: string | null; age_bp?: number | null }): number {
  if (t.period !== null) return periodToYear(t.period);
  if (t.age_bp === null || t.age_bp === undefined) throw new Error("timeToYear: neither a period nor an age");
  return 1950 - t.age_bp;
}
