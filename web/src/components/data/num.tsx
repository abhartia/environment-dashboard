import { indicator, observation, type Pick } from "@/lib/data";
import { dataPath } from "@/lib/routes";
import { formatSigned, formatValue } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * A published number in running text or a figure. It renders from data/ (never a typed numeral) as a link to the
 * number's data page, so it can be traced without JavaScript; the page-level Trace island turns the link into a
 * source panel. Values not marked final say so next to the number.
 */
export function Num({
  id,
  entity,
  period,
  dims,
  decimals,
  signed = false,
  unit = "short",
  className,
}: Pick & {
  id: string;
  /** Fewer decimals than the indicator's own, for reading ("about 1.4"). Never more. */
  decimals?: number;
  signed?: boolean;
  unit?: "short" | "label" | "none";
  className?: string;
}) {
  const ind = indicator(id);
  const obs = observation(id, { entity, period, dims });
  const places = decimals ?? ind.display.decimals;
  if (places > ind.display.decimals) {
    throw new Error(`<Num id="${id}"> asks for ${places} decimals; the indicator is published to ${ind.display.decimals}`);
  }
  const value = obs.value as number;
  const text = signed ? formatSigned(value, places) : formatValue(value, places);
  const unitText = unit === "none" ? "" : unit === "label" ? ` ${ind.unit.label}` : unitSpacing(ind.unit.short);
  return (
    <a
      href={dataPath(id, obs.period)}
      data-indicator={id}
      data-period={obs.period}
      data-entity={obs.entity}
      aria-label={`${text}${unitText}, show source`}
      aria-haspopup="dialog"
      className={cn("traced whitespace-nowrap", className)}
    >
      {text}
      {unitText}
      {obs.status !== "final" ? <span className="ml-1 align-[0.1em] text-[0.7em] font-medium tracking-wide text-muted-foreground uppercase">{obs.status === "projection" ? "projected" : "preliminary"}</span> : null}
    </a>
  );
}

/** "°C" and "%" sit next to the number; word units get a space. */
function unitSpacing(short: string): string {
  return /^(°|%|‰)/.test(short) ? short : ` ${short}`;
}
