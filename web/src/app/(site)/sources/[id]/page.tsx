import type { Metadata } from "next";
import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { Container } from "@/components/site/container";
import { PageHeader } from "@/components/site/page-header";
import { Badge } from "@/components/ui/badge";
import { indicatorsOfSource, source, sources, status } from "@/lib/data";
import { CLASS_LABEL } from "@/lib/provenance";
import { dataPath, sourcePath } from "@/lib/routes";
import { canonical } from "@/lib/site-url";

export const dynamicParams = false;

export function generateStaticParams() {
  return sources().map((s) => ({ id: s.id }));
}

export async function generateMetadata({ params }: PageProps<"/sources/[id]">): Promise<Metadata> {
  const s = source((await params).id);
  return {
    title: s.title,
    description: `${s.publisher}: ${s.title}. Licence, citation, files, update schedule and status.`.slice(0, 158),
    alternates: canonical(sourcePath(s.id)),
  };
}

function Row({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-t border-border py-3 sm:grid-cols-[12rem_minmax(0,1fr)]">
      <dt className="text-sm text-muted-foreground">{term}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

export default async function Page({ params }: PageProps<"/sources/[id]">) {
  const s = source((await params).id);
  const used = indicatorsOfSource(s.id);
  const run = status().sources[s.id];
  const ob = s.obligations;
  return (
    <>
      <PageHeader eyebrow={s.publisher} title={s.title} lede={<p>{s.description}</p>} />
      <Container className="grid max-w-4xl gap-10">
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="secondary">{CLASS_LABEL[s.licence_class]}</Badge>
          <Badge variant="outline">{s.status.state === "at-risk" ? "At risk" : s.status.state}</Badge>
          {s.status.us_federal ? <Badge variant="outline">US federal programme</Badge> : null}
          <Badge variant="outline">{s.acquisition === "manual" ? "Downloaded by hand" : "Fetched automatically"}</Badge>
        </div>

        <section aria-labelledby="published">
          <h2 id="published" className="mb-3 text-2xl">
            Numbers published from it
          </h2>
          {used.length ? (
            <ul className="grid gap-1.5">
              {used.map((e) => (
                <li key={e.id}>
                  <Link href={dataPath(e.id)} className="text-link underline">
                    {e.title}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">None yet: this source is registered and its licence checked, and its numbers are being prepared.</p>
          )}
        </section>

        <section aria-labelledby="terms">
          <h2 id="terms" className="mb-2 text-2xl">
            Licence and credit
          </h2>
          <dl>
            <Row term="Licence">
              {s.licence.url ? (
                <a href={s.licence.url} rel="noopener" className="text-link underline">
                  {s.licence.name}
                </a>
              ) : (
                s.licence.name
              )}
            </Row>
            <Row term="What the terms say">
              <blockquote className="border-l-2 border-border pl-3 italic">“{s.evidence.licence_quote}”</blockquote>
              <p className="mt-1 text-xs text-muted-foreground">
                From{" "}
                <a href={s.evidence.terms_url} rel="noopener" className="text-link underline">
                  the producer&apos;s terms
                </a>
                , checked {s.evidence.checked_on}
                {s.evidence.terms_check === "manual" ? " by a person (the page blocks automated checks)" : "; re-checked automatically every week"}.
              </p>
            </Row>
            <Row term="Credit we give">{ob.attribution}</Row>
            {ob.notice ? <Row term="Notice">{ob.notice}</Row> : null}
            {ob.rounding ? <Row term="Rounding rule">{ob.rounding}</Row> : null}
            <Row term="Copy of the raw file">
              {ob.mirror_raw ? "Allowed: we keep a public copy of every version we use." : "Not allowed: we keep a private copy for our own checks and publish its fingerprint."}
            </Row>
            <Row term="Cite as">{s.citation.text}</Row>
          </dl>
        </section>

        <section aria-labelledby="files">
          <h2 id="files" className="mb-2 text-2xl">
            Files
          </h2>
          <ul className="grid gap-3">
            {s.artifacts.map((a) => (
              <li key={a.id} className="rounded-xl border border-border bg-card p-4 text-sm">
                <p>{a.description}</p>
                {a.url ? (
                  <a href={a.url} rel="noopener" className="code-id mt-1 inline-flex items-center gap-1 text-link underline">
                    {a.url} <ExternalLink aria-hidden="true" className="size-3 shrink-0" />
                  </a>
                ) : (
                  <p className="mt-1 text-muted-foreground">Downloaded by hand (no stable direct link).</p>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="state">
          <h2 id="state" className="mb-2 text-2xl">
            Status
          </h2>
          <dl>
            <Row term="Programme">{s.status.note}</Row>
            <Row term="Updates">{s.update_cadence}</Row>
            {s.next_release ? (
              <Row term="Next release">
                {s.next_release.expected}: {s.next_release.note}
              </Row>
            ) : null}
            <Row term="Last check">
              {run ? (
                <>
                  {run.state === "failed" ? `Failed: ${run.reason}` : run.state === "manual" ? `Downloaded by hand${run.manual_last_verified ? `, last verified ${run.manual_last_verified}` : ""}` : run.state === "unchanged" ? "Unchanged since the last fetch" : "Fetched"}{" "}
                  ({run.checked_at})
                </>
              ) : (
                "Not yet checked by the scheduled run."
              )}
            </Row>
            {s.twins.length ? (
              <Row term="Independent sources measuring the same thing">
                {s.twins.map((t) => {
                  const twin = sources().find((x) => x.id === t);
                  if (!twin) throw new Error(`${s.id}: twin "${t}" is not a registered source`);
                  return (
                    <Link key={t} href={sourcePath(t)} className="mr-3 text-link underline">
                      {twin.title}
                    </Link>
                  );
                })}
              </Row>
            ) : null}
          </dl>
        </section>
      </Container>
    </>
  );
}
