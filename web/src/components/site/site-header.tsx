import Link from "next/link";

import { Container } from "@/components/site/container";
import { MobileNav } from "@/components/site/mobile-nav";
import { NavLinks } from "@/components/site/nav-links";
import { SiteSearch } from "@/components/site/site-search";
import { Mark, Wordmark } from "@/components/site/wordmark";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur supports-[backdrop-filter]:bg-background/75">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:text-primary-foreground"
      >
        Skip to content
      </a>
      <Container className="flex h-14 items-center gap-8">
        <Link href="/" className="flex items-center gap-2.5" aria-label="Environment Dashboard home">
          <Mark />
          <Wordmark />
        </Link>
        <NavLinks />
        <div className="ml-auto flex items-center gap-1">
          <SiteSearch />
          <MobileNav />
        </div>
      </Container>
    </header>
  );
}
