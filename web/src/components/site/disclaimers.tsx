import { BRAND } from "@/lib/site";
import { cn } from "@/lib/utils";

/** What the site is not, and the licences. On /about and in the menu (the site has no footer). */
export function Disclaimers({ className }: { className?: string }) {
  return (
    <div className={cn("grid gap-2 text-xs text-muted-foreground", className)} data-disclaimers>
      <p>
        Not advice: the site describes evidence and its uncertainty; it does not tell anyone what to do with their money.
        Calculators show averages from their cited sources, not your personal footprint. Showing a producer&apos;s data
        does not mean they endorse this site. Country boundaries on maps do not imply any position on disputed territory.
      </p>
      <p>
        Site text CC BY 4.0. Figures and data carry the licence of their source, named under each view and on each data
        page. Code MIT, at{" "}
        <a href={BRAND.repo} rel="noopener" className="underline hover:text-foreground">
          GitHub
        </a>
        . Contact <span className="select-all">{BRAND.email}</span>.
      </p>
    </div>
  );
}
