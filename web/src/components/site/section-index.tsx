import Link from "next/link";

import { Container } from "@/components/site/container";
import { PageHeader } from "@/components/site/page-header";
import type { Section } from "@/lib/sections";

/** A section's landing page: its question, then each story as a question of its own. */
export function SectionIndex({ section }: { section: Section }) {
  return (
    <>
      <PageHeader eyebrow={section.label} title={section.question} lede={<p>{section.intro}</p>} />
      <Container>
        <ol className="grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2">
          {section.stories.map((story, i) => {
            const body = (
              <>
                <p className="eyebrow">
                  {String(i + 1).padStart(2, "0")} · {story.title}
                </p>
                <p className="mt-2 font-semibold tracking-tight text-xl leading-snug">{story.question}</p>
                {story.ready ? null : <p className="mt-3 text-sm text-muted-foreground">Being built</p>}
              </>
            );
            return (
              <li key={story.slug} className="bg-card">
                {story.ready ? (
                  <Link href={`${section.href}/${story.slug}`} className="block h-full p-6 hover:bg-accent">
                    {body}
                  </Link>
                ) : (
                  <div className="h-full p-6">{body}</div>
                )}
              </li>
            );
          })}
        </ol>
      </Container>
    </>
  );
}
