import { cn } from "@/lib/utils";

/**
 * A row of seven warming stripes as the mark. These colours are a decorative motif, not data, so they carry no
 * attribution; the real stripes figure (credited to Show Your Stripes) is drawn from HadCRUT5 on the temperature page.
 */
const STRIPES = ["#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#8e0f26", "#67001f"];

export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className={cn("size-5 rounded-[3px]", className)}>
      {STRIPES.map((c, i) => (
        <rect key={c} x={i * 2} y={0} width={2.05} height={20} fill={c} />
      ))}
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("text-lg font-bold tracking-tight whitespace-nowrap", className)}>
      Environment <span className="text-muted-foreground">Dashboard</span>
    </span>
  );
}
