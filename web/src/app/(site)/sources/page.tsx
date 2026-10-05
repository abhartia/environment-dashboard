import type { Metadata } from "next";
import Link from "next/link";

import { Container } from "@/components/site/container";
import { PageHeader } from "@/components/site/page-header";
import { Badge } from "@/components/ui/badge";
import { indicatorsOfSource, sources } from "@/lib/data";
import { CLASS_LABEL } from "@/lib/provenance";
import { sourcePath } from "@/lib/routes";
import { canonical } from "@/lib/site-url";

export const metadata: Metadata = {
  title: "Sources",
  description: "The organisations whose data the site uses, their licences, how each is fetched, and which sources are at risk.",
  alternates: canonical("/sources"),
};


export default function Page() {
  const all = [...sources()].sort((a, b) => a.publisher.localeCompare(b.publisher) || a.title.localeCompare(b.title));
  return (
    <>
      <PageHeader
        eyebrow="Sources"
        title="Who measured it, and on what terms"
        lede={
          <p>
            Every source we use or have registered, with the licence its producer sets (quoted from their own terms),
            how we fetch it, and whether it is at risk of being discontinued.
          </p>
        }
      />
      <Container>
        <ul className="grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2">
          {all.map((s) => {
            const used = indicatorsOfSource(s.id).length;
            return (
              <li key={s.id} className="bg-card">
                <Link href={sourcePath(s.id)} className="grid h-full gap-2 p-5 hover:bg-accent">
                  <span className="eyebrow">{s.publisher}</span>
                  <span className="font-serif text-lg leading-snug">{s.title}</span>
                  <span className="flex flex-wrap gap-1.5">
                    <Badge variant="secondary">{CLASS_LABEL[s.licence_class]}</Badge>
                    {s.status.state !== "active" ? <Badge variant="outline">{s.status.state === "at-risk" ? "At risk" : s.status.state}</Badge> : null}
                    {s.acquisition === "manual" ? <Badge variant="outline">Downloaded by hand</Badge> : null}
                    <Badge variant="outline">{used ? `${used} published number${used > 1 ? "s" : ""}` : "Registered, not yet published"}</Badge>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </Container>
    </>
  );
}
