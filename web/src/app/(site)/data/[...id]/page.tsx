import type { Metadata } from "next";
import Link from "next/link";
import { Download, ExternalLink } from "lucide-react";

import { JsonLd } from "@/components/site/json-ld";
import { Container } from "@/components/site/container";
import { PageHeader } from "@/components/site/page-header";
import { Figure } from "@/components/viz/figure";
import { SeriesChart, type Series } from "@/components/viz/series-chart";
import type { Indicator, Observation } from "@/gen/hey-api/types.gen";
import { catalog, catalogEntry, indicator, source } from "@/lib/data";
import { formatValue, formatWhen } from "@/lib/format";
import { citeAs, licenceSentence } from "@/lib/provenance";
import { dataPath, downloadPath, idFromSegments, sourcePath, timeAnchor } from "@/lib/routes";
import { BRAND, reportProblemUrl } from "@/lib/site";
import { ogImages } from "@/lib/seo/og";
import { absoluteUrl, canonical } from "@/lib/site-url";
import { timeToYear } from "@/lib/viz/period";

export const dynamicParams = false;

export function generateStaticParams() {
  return catalog().indicators.map((e) => ({ id: e.id.split(".") }));
}

export async function generateMetadata({ params }: PageProps<"/data/[...id]">): Promise<Metadata> {
  const id = idFromSegments((await params).id);
  const entry = catalogEntry(id);
  return {
    title: entry.title,
    description: `${entry.title}: the data, where it comes from (${entry.provenance.origins[0].producer}), every step applied, and its licence.`.slice(0, 158),
    alternates: canonical(dataPath(id)),
    openGraph: { images: ogImages(dataPath(id)) },
  };
}

const MAX_SERIES = 5;
/**
 * A page holds at most this many table rows (a daily series has tens of thousands, past the host's file-size limit).
 * A longer table shows the latest rows and says so; every value is always in the CSV and JSON downloads.
 */
const MAX_TABLE_ROWS = 5000;

/** The headline entity's series: one line per combination of dimension values (at most five). */
function chartSeries(ind: Indicator): Series[] {
  const rows = ind.observations.filter((o) => o.entity === ind.headline_entity);
  const groups = new Map<string, Observation[]>();
  for (const o of rows) {
    const key = Object.entries(o.dims)
      .sort()
      .map(([k, v]) => `${k}=${v}`)
      .join(",");
    groups.set(key, [...(groups.get(key) ?? []), o]);
  }
  const label = (key: string) => {
    if (!key) return ind.title;
    return key
      .split(",")
      .map((kv) => {
        const [k, v] = kv.split("=");
        const dim = ind.dimensions.find((d) => d.id === k);
        return dim?.values.find((x) => x.id === v)?.label ?? v;
      })
      .join(", ");
  };
  return [...groups.entries()].slice(0, MAX_SERIES).map(([key, obs]) => ({
    key: key || "value",
    label: label(key),
    points: obs.map((o) => ({ x: timeToYear(o), y: o.value, lo: o.lower, hi: o.upper })),
  }));
}

function DescriptionRow({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-t border-border py-3 sm:grid-cols-[12rem_minmax(0,1fr)]">
      <dt className="text-sm text-muted-foreground">{term}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

export default async function Page({ params }: PageProps<"/data/[...id]">) {
  const id = idFromSegments((await params).id);
  const entry = catalogEntry(id);
  const ind = indicator(id);
  const p = entry.provenance;
  const latest = ind.latest;
  const series = ind.kind === "published-value" ? [] : chartSeries(ind);
  const dec = ind.display.decimals;
  const notes = [...new Set(ind.observations.map((o) => o.note).filter((n): n is string => Boolean(n)))];
  const rows = ind.observations.filter((o) => o.entity === ind.headline_entity);
  const dimCols = ind.dimensions.map((d) => d.label);
  const hasRange = rows.some((o) => o.lower !== null);
  const sourcesUsed = [...new Set(p.origins.map((o) => o.source_id))].map((s) => source(s));

  return (
    <>
      <PageHeader eyebrow="Data" title={entry.title} lede={<p>{p.description}</p>} />
      <Container className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="grid min-w-0 content-start gap-8 [overflow-wrap:anywhere]">
          <section aria-labelledby="latest" className="grid gap-1">
            <h2 id="latest" className="eyebrow font-sans">
              Latest value
            </h2>
            <p className="font-semibold tracking-tight text-4xl num">
              {formatValue(latest.value, dec)}
              <span className="ml-2 text-xl text-muted-foreground">{ind.unit.short}</span>
            </p>
            <p className="text-sm text-muted-foreground">
              {p.scope.geography}, {formatWhen(latest)}
              {latest.status !== "final" ? ` (${latest.status})` : ""}. Version {ind.vintage}.
            </p>
          </section>

          {p.published_value ? (
            <section aria-labelledby="quoted" className="grid gap-3">
              <h2 id="quoted" className="text-2xl">
                As published
              </h2>
              <blockquote className="border-l-2 border-foreground pl-4 font-semibold tracking-tight text-lg">“{p.published_value.quote}”</blockquote>
              <p className="text-sm text-muted-foreground">
                {source(p.published_value.document).title}, {p.published_value.locator}. Checked word for word against
                the stored copy of the document every time the data is rebuilt.
              </p>
            </section>
          ) : null}

          {!series.length && rows.length > 1 ? (
            <section aria-labelledby="values" className="grid gap-3">
              <h2 id="values" className="text-2xl">
                Every value
              </h2>
              <div className="overflow-x-auto rounded-xl border border-border bg-card">
                <table className="w-full text-sm">
                  <caption className="sr-only">{entry.title}, every published value</caption>
                  <thead className="bg-muted text-left">
                    <tr>
                      {[...dimCols, "Period", `Value (${ind.unit.short})`, ...(hasRange ? ["Range"] : []), "Status"].map((c) => (
                        <th key={c} className="px-3 py-2 font-medium">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((o, i) => (
                      <tr key={i} className="border-t border-border align-top">
                        {ind.dimensions.map((d) => (
                          <td key={d.id} className="px-3 py-2">
                            {d.values.find((v) => v.id === o.dims[d.id])?.label ?? o.dims[d.id]}
                            {o.note ? <span className="mt-1 block text-xs text-muted-foreground">{o.note}</span> : null}
                          </td>
                        ))}
                        <td className="num px-3 py-2">{o.period}</td>
                        <td className="num px-3 py-2 text-right">{o.value === null ? `none (${o.missing_reason})` : formatValue(o.value, dec)}</td>
                        {hasRange ? (
                          <td className="num px-3 py-2 text-right">
                            {o.lower === null ? "" : `${formatValue(o.lower, dec)} to ${formatValue(o.upper as number, dec)}`}
                          </td>
                        ) : null}
                        <td className="px-3 py-2">{o.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {series.length ? (
            <Figure
              id="series"
              title={`${entry.title} (${ind.unit.label})`}
              takeaway={
                <>
                  {rows.length} values from {formatWhen(rows[0])} to {formatWhen(rows[rows.length - 1])}.
                  {series.length > 1 ? ` Lines: ${series.map((s) => s.label).join(", ")}.` : ""}
                  {hasRange ? " The shaded band is the uncertainty range the producer gives." : ""}
                </>
              }
              source={
                <>
                  {p.attribution} {p.licence.name}.
                </>
              }
              table={{
                caption: rows.length > MAX_TABLE_ROWS ? `${entry.title}, the latest values` : `${entry.title}, every value`,
                note:
                  rows.length > MAX_TABLE_ROWS
                    ? `The latest ${formatValue(MAX_TABLE_ROWS, 0)} of ${formatValue(rows.length, 0)} values. Every value is in the CSV and JSON downloads.`
                    : undefined,
                columns: ["Period", ...dimCols, `Value (${ind.unit.short})`, ...(hasRange ? ["Range"] : []), "Status"],
                rows: rows.slice(-MAX_TABLE_ROWS).map((o) => [
                  <span key="p" id={timeAnchor(o)}>
                    {o.period ?? formatWhen(o)}
                  </span>,
                  ...ind.dimensions.map((d) => d.values.find((v) => v.id === o.dims[d.id])?.label ?? o.dims[d.id]),
                  o.value === null ? `none (${o.missing_reason})` : formatValue(o.value, dec),
                  ...(hasRange ? [o.lower === null ? "" : `${formatValue(o.lower, dec)} to ${formatValue(o.upper as number, dec)}`] : []),
                  o.status,
                ]),
              }}
            >
              <SeriesChart series={series} decimals={dec} unit={ind.unit.short} />
            </Figure>
          ) : null}

          {notes.length > 0 && series.length > 0 ? (
            <section aria-labelledby="notes" className="grid gap-2">
              <h2 id="notes" className="text-2xl">
                Notes on individual values
              </h2>
              <ul className="list-disc pl-5 text-sm text-muted-foreground">
                {notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section aria-labelledby="where" className="grid gap-4">
            <h2 id="where" className="text-2xl">
              Where it comes from
            </h2>
            {p.origins.map((o) => (
              <dl key={o.sha256} className="rounded-xl border border-border bg-card px-4">
                <DescriptionRow term="Producer">
                  <Link href={sourcePath(o.source_id)} className="text-link underline">
                    {o.producer}
                  </Link>{" "}
                  · {o.title}
                </DescriptionRow>
                <DescriptionRow term="Version">{o.version_producer ?? "not stated by the producer"}</DescriptionRow>
                <DescriptionRow term="File">
                  {o.url_download ? (
                    <a href={o.url_download} rel="noopener" className="code-id text-link underline">
                      {o.url_download}
                    </a>
                  ) : (
                    <>Downloaded by hand from <a href={o.url_main} rel="noopener" className="text-link underline">{o.url_main}</a></>
                  )}
                </DescriptionRow>
                <DescriptionRow term="Fetched">
                  {o.date_accessed} ({o.acquisition === "manual" ? "by a person" : "automatically"}),{" "}
                  {o.bytes.toLocaleString("en-US")} bytes
                </DescriptionRow>
                <DescriptionRow term="Fingerprint">
                  <span className="code-id select-all">sha256 {o.sha256}</span>
                  {o.etag || o.last_modified ? (
                    <span className="block text-xs text-muted-foreground">
                      {o.etag ? `ETag ${o.etag}` : ""} {o.last_modified ? `· Last-Modified ${o.last_modified}` : ""}
                    </span>
                  ) : null}
                </DescriptionRow>
                <DescriptionRow term="Copies">
                  {o.wayback_url ? (
                    <a href={o.wayback_url} rel="noopener" className="inline-flex items-center gap-1 text-link underline">
                      Archived copy (Wayback Machine) <ExternalLink aria-hidden="true" className="size-3" />
                    </a>
                  ) : (
                    <span className="text-muted-foreground">No Wayback copy recorded yet.</span>
                  )}
                  {o.r2_url ? (
                    <a href={o.r2_url} rel="noopener" className="ml-3 inline-flex items-center gap-1 text-link underline">
                      Our copy of the exact file <ExternalLink aria-hidden="true" className="size-3" />
                    </a>
                  ) : null}
                </DescriptionRow>
                <DescriptionRow term="Cite the producer">{o.citation_full}</DescriptionRow>
              </dl>
            ))}
          </section>

          <section aria-labelledby="steps" className="grid gap-3">
            <h2 id="steps" className="text-2xl">
              What was done to it
            </h2>
            <ol className="grid gap-3">
              {p.processing.map((s, i) => (
                <li key={i} className="rounded-xl border border-border bg-card p-4 text-sm">
                  <p>{s.description}</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Code:{" "}
                    <a href={`${BRAND.repo}/blob/main/${s.script}`} rel="noopener" className="code-id text-link underline">
                      {s.script}
                    </a>{" "}
                    · <span className="code-id">code sha256 {s.transform_sha256.slice(0, 16)}…</span> · inputs{" "}
                    {s.inputs.map((h) => (
                      <span key={h} className="code-id">
                        {h.slice(0, 12)}…{" "}
                      </span>
                    ))}
                  </p>
                </li>
              ))}
            </ol>
          </section>

          <section aria-labelledby="scope">
            <h2 id="scope" className="mb-2 text-2xl">
              What it covers
            </h2>
            <dl>
              <DescriptionRow term="Geography">{p.scope.geography}</DescriptionRow>
              {p.scope.baseline ? <DescriptionRow term="Baseline">{p.scope.baseline}</DescriptionRow> : null}
              {p.scope.gwp ? <DescriptionRow term="Gases combined with">{p.scope.gwp}</DescriptionRow> : null}
              {p.scope.lulucf ? <DescriptionRow term="Land use, land-use change and forestry">{p.scope.lulucf}</DescriptionRow> : null}
              {p.scope.basis ? <DescriptionRow term="Basis">{p.scope.basis}</DescriptionRow> : null}
              <DescriptionRow term="Unit">
                {ind.unit.label} ({ind.unit.short})
              </DescriptionRow>
            </dl>
          </section>
        </div>

        <aside className="grid min-w-0 content-start gap-6 [overflow-wrap:anywhere] lg:sticky lg:top-20">
          <section aria-labelledby="get" className="grid gap-2 rounded-xl border border-border bg-card p-4">
            <h2 id="get" className="eyebrow font-sans">
              Get the numbers
            </h2>
            {entry.downloadable ? (
              <>
                <a href={downloadPath(id, "csv")} download className="inline-flex items-center gap-2 text-sm text-link underline">
                  <Download aria-hidden="true" className="size-4" /> CSV
                </a>
                <a href={downloadPath(id, "json")} className="inline-flex items-center gap-2 text-sm text-link underline">
                  <Download aria-hidden="true" className="size-4" /> JSON, with full provenance
                </a>
                <p className="text-xs text-muted-foreground">
                  Licence: {licenceSentence(entry)}. Credit: {p.attribution}
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                The producer&apos;s terms allow these values to be shown but not redistributed, so there is no download.
                Get them from the original file listed under “Where it comes from”.
              </p>
            )}
            {p.notice ? <p className="text-xs text-muted-foreground">{p.notice}</p> : null}
          </section>
          <section aria-labelledby="cite" className="grid gap-2 rounded-xl border border-border bg-card p-4">
            <h2 id="cite" className="eyebrow font-sans">
              How to cite
            </h2>
            <p className="text-xs whitespace-pre-line select-all">{citeAs(entry)}</p>
          </section>
          <section aria-labelledby="used" className="grid gap-2 rounded-xl border border-border bg-card p-4">
            <h2 id="used" className="eyebrow font-sans">
              Sources
            </h2>
            {sourcesUsed.map((s) => (
              <Link key={s.id} href={sourcePath(s.id)} className="text-sm text-link underline">
                {s.title}
              </Link>
            ))}
            <a href={reportProblemUrl(id, dataPath(id))} rel="noopener" className="mt-2 text-sm text-link underline">
              Report a problem with this number
            </a>
          </section>
        </aside>
      </Container>
      {entry.downloadable ? (
        <JsonLd
          data={{
            "@context": "https://schema.org",
            "@type": "Dataset",
            name: entry.title,
            description: p.description,
            url: absoluteUrl(dataPath(id)),
            version: ind.vintage,
            license: p.licence.url ?? undefined,
            creditText: p.attribution,
            isAccessibleForFree: true,
            creator: sourcesUsed.map((s) => ({ "@type": "Organization", name: s.publisher, url: s.landing_url })),
            isBasedOn: p.origins.map((o) => o.url_download ?? o.url_main),
            variableMeasured: `${entry.title} (${ind.unit.label})`,
            temporalCoverage: `${rows[0]?.period}/${rows[rows.length - 1]?.period}`,
            distribution: [
              { "@type": "DataDownload", encodingFormat: "text/csv", contentUrl: absoluteUrl(downloadPath(id, "csv")) },
              { "@type": "DataDownload", encodingFormat: "application/json", contentUrl: absoluteUrl(downloadPath(id, "json")) },
            ],
          }}
        />
      ) : null}
    </>
  );
}
