import { makeCite } from "@/components/data/cite";
import { JsonLd } from "@/components/site/json-ld";
import { Container } from "@/components/site/container";
import { PageHeader } from "@/components/site/page-header";
import { Badge } from "@/components/ui/badge";
import { source } from "@/lib/data";
import { CLASS_LABEL } from "@/lib/provenance";
import { sourcePath } from "@/lib/routes";
import { SECTIONS } from "@/lib/sections";
import { absoluteUrl } from "@/lib/site-url";
import { story } from "@/lib/stories";

/**
 * A story page: the question as the h1, the MDX body (whose first paragraph is the answer), and the numbered sources
 * its <Cite> marks point to. The body is loaded by path, so a missing MDX file fails the build.
 */
export async function StoryPage({ section, slug }: { section: "causes" | "consequences" | "action"; slug: string }) {
  const s = story(section, slug);
  const sectionLabel = SECTIONS.find((x) => x.href === `/${section}`)!.label;
  const { default: Content } = await import(`@/content/stories/${section}/${slug}.mdx`);
  const Cite = makeCite(s.sources);
  const path = `/${section}/${slug}`;
  return (
    <>
      <PageHeader eyebrow={`${sectionLabel} · ${s.title}`} title={s.question} />
      <Container className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <article className="prose article-ed min-w-0 [&_.lead]:text-xl [&_.lead]:leading-relaxed [&_figure]:not-prose [&_figure]:my-8">
          <Content components={{ Cite }} />
        </article>
        <aside aria-labelledby="sources" className="grid content-start gap-3 lg:sticky lg:top-20">
          <h2 id="sources" className="eyebrow font-sans">
            Sources
          </h2>
          <ol className="grid gap-3 text-sm">
            {s.sources.map((id, i) => {
              const src = source(id);
              return (
                <li key={id} id={`source-${id}`} className="grid grid-cols-[1.75rem_minmax(0,1fr)] scroll-mt-24 items-baseline">
                  <span className="num text-xs text-faint">[{i + 1}]</span>
                  <span className="grid gap-1">
                    <a href={sourcePath(id)} className="leading-snug text-link underline">
                      {src.publisher}: {src.title}
                    </a>
                    <span>
                      <Badge variant="outline" className="font-normal">
                        {CLASS_LABEL[src.licence_class]}
                      </Badge>
                    </span>
                  </span>
                </li>
              );
            })}
          </ol>
        </aside>
      </Container>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "Article",
          headline: s.question,
          description: s.description,
          url: absoluteUrl(path),
          datePublished: s.published,
          dateModified: s.updated,
          citation: s.sources.map((id) => ({ "@type": "CreativeWork", name: source(id).citation.text, url: source(id).landing_url })),
        }}
      />
    </>
  );
}
