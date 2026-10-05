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
