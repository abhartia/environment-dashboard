import Link from "next/link";
import { ArrowDown } from "lucide-react";

import { Num } from "@/components/data/num";
import { PeriodOf } from "@/components/data/period-of";
import { Sparkline } from "@/components/viz/sparkline";
import { indicator } from "@/lib/data";

const EMISSIONS = "emissions.gcb-2025.total-co2-global";
const BUDGET_PARTS = "emissions.gcb-2025.budget-global";
const CO2 = "co2.noaa-gml.annual-global";
const WARMING = "temp.hadcrut5.annual-1850-1900";
const BUDGET = "budget.igcc-2025.remaining-1p5";

type Step = { n: string; label: string; href: string; body: React.ReactNode; spark?: string };

/**
 * The home page's chain of cause and effect, in order and in matching scopes: what we emit, what it does to the
 * air, what that does to temperature, and how much more the world can emit. Every number is a traced <Num>.
 */
export function CausalChain() {
  // Where the year's emissions went, for the same year as the emissions step (never a typed year).
  const year = indicator(EMISSIONS).latest.period;
  const part = (component: string) => <Num id={BUDGET_PARTS} period={year} dims={{ component }} decimals={1} unit="none" />;
  const steps: Step[] = [
    {
      n: "01",
      label: "We emit",
      href: "/causes",
      spark: EMISSIONS,
      body: (
        <>
          Carbon dioxide from burning fossil fuels, making cement and clearing land reached{" "}
          <Num id={EMISSIONS} decimals={1} unit="label" /> in <PeriodOf id={EMISSIONS} />.
        </>
      ),
    },
    {
      n: "02",
      label: "It builds up",
      href: "/causes",
      spark: CO2,
      body: (
        <>
          Of that, {part("atmospheric-growth")} billion tonnes stayed in the air; the oceans took up{" "}
          {part("ocean-sink")} billion and plants and soils {part("land-sink")} billion. Carbon dioxide in the air
          averaged <Num id={CO2} decimals={1} unit="label" /> in <PeriodOf id={CO2} />.
        </>
      ),
    },
    {
      n: "03",
      label: "The planet warms",
      href: "/consequences",
      spark: WARMING,
      body: (
        <>
          The extra gases trap heat. In <PeriodOf id={WARMING} /> the surface was <Num id={WARMING} decimals={1} />{" "}
          warmer than in 1850–1900.
        </>
      ),
    },
    {
      n: "04",
      label: "What is left",
      href: "/action",
      body: (
        <>
          To keep a 50% chance of limiting warming to 1.5 °C, the world could emit only{" "}
          <Num id={BUDGET} unit="label" /> more, counted from the start of 2026.
        </>
      ),
    },
  ];
  return (
    <ol className="grid gap-0">
      {steps.map((s, i) => (
        <li key={s.n} className="grid gap-4 border-t border-border py-8 sm:grid-cols-[10rem_minmax(0,1fr)_10rem] sm:items-center">
          <Link href={s.href} className="eyebrow hover:text-foreground">
            {s.n} · {s.label}
          </Link>
          <p className="font-serif text-2xl leading-snug sm:text-[1.75rem]">{s.body}</p>
          {s.spark ? <Sparkline id={s.spark} className="hidden h-12 w-40 text-muted-foreground sm:block" /> : <span className="hidden sm:block" />}
          {i < steps.length - 1 ? <ArrowDown aria-hidden="true" className="size-4 text-faint sm:hidden" /> : null}
        </li>
      ))}
    </ol>
  );
}
