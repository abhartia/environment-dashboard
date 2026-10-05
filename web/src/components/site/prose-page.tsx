import { Container } from "@/components/site/container";
import { PageHeader } from "@/components/site/page-header";

/** A plain reading page (about, methods, privacy...): header, then long-form text. */
export function ProsePage({ eyebrow, title, lede, children }: { eyebrow?: string; title: string; lede?: React.ReactNode; children: React.ReactNode }) {
  return (
    <>
      <PageHeader eyebrow={eyebrow} title={title} lede={lede} />
      <Container>
        <div className="prose article-ed">{children}</div>
      </Container>
    </>
  );
}
