import { indicator } from "@/lib/data";
import { formatPeriod } from "@/lib/format";

/** The period of an indicator's latest headline value, in words ("2025", "August 2026"), from data/, never typed. */
export function PeriodOf({ id }: { id: string }) {
  return <>{formatPeriod(indicator(id).latest.period)}</>;
}
