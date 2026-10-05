import { Container } from "@/components/site/container";

/** The top of every non-home page: an eyebrow, the one h1, and a lede. */
export function PageHeader({ eyebrow, title, lede }: { eyebrow?: string; title: string; lede?: React.ReactNode }) {
  return (
    <Container className="pt-12 pb-8 sm:pt-16">
      {eyebrow ? <p className="eyebrow mb-3">{eyebrow}</p> : null}
      <h1 className="max-w-3xl text-[clamp(2.25rem,1.6rem+2.6vw,3.75rem)]">{title}</h1>
      {lede ? <div className="mt-5 max-w-2xl text-lg text-muted-foreground">{lede}</div> : null}
    </Container>
  );
}
