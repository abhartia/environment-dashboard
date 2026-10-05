import Link from "next/link";

import { Container } from "@/components/site/container";
import { Mark } from "@/components/site/wordmark";
import { Button } from "@/components/ui/button";
import { CHAPTER_META } from "@/lib/dash/meta";

/** Rendered in the root layout (no site header). Becomes out/404.html, which Pages serves with a 404 status. */
export default function NotFound() {
  return (
    <main className="grid flex-1 place-content-center py-24">
      <Container className="grid gap-5">
        <Mark className="size-8" />
        <p className="eyebrow">404 · Not found</p>
        <h1 className="text-[clamp(2.25rem,1.5rem+2.4vw,3.5rem)]">This page doesn&apos;t exist</h1>
        <nav aria-label="Where to go instead" className="flex flex-wrap gap-2">
          {CHAPTER_META.map((c) => (
            <Button key={c.slug} asChild variant="outline">
              <Link href={`/${c.slug}`}>{c.title}</Link>
            </Button>
          ))}
          <Button asChild variant="ghost">
            <Link href="/">Home</Link>
          </Button>
        </nav>
      </Container>
    </main>
  );
}
