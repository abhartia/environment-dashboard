import Link from "next/link";

import { Container } from "@/components/site/container";
import { Mark, Wordmark } from "@/components/site/wordmark";
import { BRAND, FOOTER_NAV, NAV } from "@/lib/site";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-border bg-paper">
      <Container className="grid gap-10 py-12 md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="grid content-start gap-3">
          <div className="flex items-center gap-2.5">
            <Mark />
            <Wordmark />
          </div>
          <p className="max-w-sm text-sm text-muted-foreground">{BRAND.description}</p>
        </div>
        <nav aria-label="Explore" className="grid content-start gap-2 text-sm">
          <p className="eyebrow">Explore</p>
          {NAV.map((l) => (
            <Link key={l.href} href={l.href} className="text-muted-foreground hover:text-foreground">
              {l.label}
            </Link>
          ))}
        </nav>
        <nav aria-label="About the data" className="grid content-start gap-2 text-sm">
          <p className="eyebrow">About the data</p>
          {FOOTER_NAV.map((l) => (
            <Link key={l.href} href={l.href} className="text-muted-foreground hover:text-foreground">
              {l.label}
            </Link>
          ))}
        </nav>
      </Container>
      <div className="border-t border-border">
        <Container className="grid gap-2 py-5 text-xs text-muted-foreground" data-footer-disclaimers>
          <p>
            Not advice: the site describes evidence and its uncertainty; it does not tell anyone what to do with their
            money. Calculators show averages from their cited sources, not your personal footprint. Showing a
            producer&apos;s data does not mean they endorse this site. Country boundaries on maps do not imply any
            position on disputed territory.
          </p>
          <p>
            Site text CC BY 4.0. Figures and data carry the licence in their footer. Code MIT, at{" "}
            <a href={BRAND.repo} rel="noopener" className="underline hover:text-foreground">
              GitHub
            </a>
            . Contact <span className="select-all">{BRAND.email}</span>.
          </p>
        </Container>
      </div>
    </footer>
  );
}
