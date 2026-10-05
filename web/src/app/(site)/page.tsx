import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Container } from "@/components/site/container";
import { SECTIONS } from "@/lib/sections";

/**
 * Home. The causal chain (emissions → concentrations → warming → sea level → budget left) renders here from data/
 * once those indicators are published; until then the page states what the site does and links the three questions.
 */
export default function Home() {
  return (
    <>
      <section className="border-b border-border">
        <Container className="grid gap-8 py-16 sm:py-24">
          <p className="eyebrow">Climate data, traced to its source</p>
          <h1 className="max-w-4xl text-[clamp(2.5rem,1.6rem+4vw,5rem)]">
            What is changing the climate, what it is doing, and what can be done
          </h1>
          <p className="max-w-2xl text-lg text-muted-foreground sm:text-xl">
            Follow the evidence from cause to consequence to choice. Every number links to the file it came from: who
            published it, which version, when we fetched it, what we did to it, and the terms it is shared under.
          </p>
        </Container>
      </section>

      <Container className="py-16">
        <h2 className="sr-only">Three questions</h2>
        <ol className="grid gap-6 md:grid-cols-3">
          {SECTIONS.map((s, i) => (
            <li key={s.href}>
              <Link
                href={s.href}
                className="group grid h-full content-start gap-3 rounded-xl border border-border bg-card p-6 transition-colors hover:bg-accent"
              >
                <span className="eyebrow">
                  {String(i + 1).padStart(2, "0")} · {s.label}
                </span>
                <span className="font-serif text-2xl leading-tight">{s.question}</span>
                <span className="text-muted-foreground">{s.intro}</span>
                <span className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-link">
                  Explore <ArrowRight aria-hidden="true" className="size-4 transition-transform group-hover:translate-x-0.5" />
                </span>
              </Link>
            </li>
          ))}
        </ol>
      </Container>

      <Container className="grid gap-6 border-t border-border py-16 md:grid-cols-[1fr_2fr]">
        <h2 className="text-3xl">How to check any number</h2>
        <ol className="grid gap-4 text-muted-foreground">
          <li>
            <strong className="text-foreground">Select it.</strong> Every figure on the site is a link. It opens a
            short note naming the organisation that measured it and the version of their data.
          </li>
          <li>
            <strong className="text-foreground">Open its data page.</strong> You will find the exact file we used,
            when we fetched it, its sha256 fingerprint, an archived copy, each step we applied, and the licence.
          </li>
          <li>
            <strong className="text-foreground">Check it yourself.</strong> Download the numbers, or go to the original
            file and repeat the steps. If something does not match, tell us; corrections are published.
          </li>
        </ol>
      </Container>
    </>
  );
}
