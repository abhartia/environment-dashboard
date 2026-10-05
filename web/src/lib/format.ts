/**
 * The one place a published number becomes text. Values in data/ are unrounded; each indicator says how many
 * decimals it is shown with (display.decimals), and every number on the site goes through formatValue.
 */

const formatters = new Map<number, Intl.NumberFormat>();

function formatter(decimals: number): Intl.NumberFormat {
  let f = formatters.get(decimals);
  if (!f) {
    f = new Intl.NumberFormat("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    formatters.set(decimals, f);
  }
  return f;
}

/** 427.554 with 2 decimals -> "427.55"; -0.004 with 2 decimals -> "0.00" (never "-0.00"). Uses a true minus sign. */
export function formatValue(value: number, decimals: number): string {
  if (!Number.isFinite(value)) throw new Error(`formatValue: not a finite number: ${value}`);
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > 6) throw new Error(`formatValue: bad decimals ${decimals}`);
  const text = formatter(decimals).format(value);
  if (/^-0(\.0+)?$/.test(text)) return text.slice(1);
  return text.replace(/^-/, "−");
}

/** A signed change, e.g. "+1.43" / "−0.20", for anomalies and differences. */
export function formatSigned(value: number, decimals: number): string {
  const text = formatValue(value, decimals);
  return value > 0 && /[1-9]/.test(text) ? `+${text}` : text;
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** ISO 8601 period as words: "2026-08" -> "August 2026", "2025" -> "2025", "2012/2021" -> "2012–2021". */
export function formatPeriod(period: string): string {
  if (period.includes("/")) return period.split("/").map(formatPeriod).join("–");
  const m = period.match(/^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/);
  if (!m) throw new Error(`formatPeriod: not an ISO 8601 period: ${period}`);
  const [, y, mo, d] = m;
  if (!mo) return y;
  const month = MONTHS[Number(mo) - 1];
  if (!month) throw new Error(`formatPeriod: bad month in ${period}`);
  return d ? `${Number(d)} ${month} ${y}` : `${month} ${y}`;
}

/**
 * When an observation is, in words: its ISO period ("August 2026"), or for a series dated by age (an ice core) its
 * age ("12,000 years before 1950").
 */
export function formatWhen(t: { period: string | null; age_bp?: number | null }): string {
  if (t.period !== null) return formatPeriod(t.period);
  if (t.age_bp === null || t.age_bp === undefined) throw new Error("formatWhen: neither a period nor an age");
  return `${formatValue(t.age_bp, 0)} years before 1950`;
}

/** A calendar observation's period. Age-dated (years-before-1950) values have none; callers that need one fail loudly. */
export function calendarPeriod(t: { period: string | null }): string {
  if (t.period === null) throw new Error("expected a calendar period, got an age-dated (years-before-1950) value");
  return t.period;
}

/**
 * How a big value reads: 332,928,198 is shown as 332.9 million. The scale is chosen from the value (or from `scaleOf`,
 * so a counting animation keeps one word), and the shown precision is never finer than published (a tenth of a
 * million is coarser than any published decimal). Below a million the value is formatted as published.
 */
export function readable(value: number, decimals: number, scaleOf: number = value): { number: string; word: string } {
  const a = Math.abs(scaleOf);
  if (a >= 1e9) return { number: formatValue(value / 1e9, 1), word: "billion" };
  if (a >= 1e6) return { number: formatValue(value / 1e6, 1), word: "million" };
  return { number: formatValue(value, decimals), word: "" };
}

/** The same, as one string: "332.9 million". */
export function formatReadable(value: number, decimals: number): string {
  const r = readable(value, decimals);
  return r.word ? `${r.number} ${r.word}` : r.number;
}

/** Axis labels: 500,000,000 -> "500m", 1,500,000,000 -> "1.5bn"; smaller values as formatValue. */
export function formatTick(value: number, decimals: number): string {
  const a = Math.abs(value);
  const short = (v: number) => formatValue(v, Number.isInteger(v) ? 0 : 1);
  if (a >= 1e9) return `${short(value / 1e9)}bn`;
  if (a >= 1e6) return `${short(value / 1e6)}m`;
  return formatValue(value, decimals);
}
