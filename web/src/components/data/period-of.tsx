import { indicator } from "@/lib/data";
import { formatWhen } from "@/lib/format";

/** When an indicator's latest headline value is, in words ("2025", "August 2026"), from data/, never typed. */
export function PeriodOf({ id }: { id: string }) {
  return <>{formatWhen(indicator(id).latest)}</>;
}
