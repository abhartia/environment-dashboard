import { DrillCanvas } from "@/components/dash/drill-canvas";
import { Container } from "@/components/site/container";
import { CHAPTERS } from "@/lib/dash/chapters";
import type { ChapterSlug } from "@/lib/dash/meta";

/** A chapter: the drill-down canvas opened on the chapter's first node, filling the screen below the header. */
export function ChapterPage({ slug }: { slug: ChapterSlug }) {
  return (
    <Container>
      <DrillCanvas chapter={slug} initial={CHAPTERS[slug].node("root")} />
    </Container>
  );
}
