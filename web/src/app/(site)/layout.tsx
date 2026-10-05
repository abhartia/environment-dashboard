import { TraceListener } from "@/components/data/trace-listener";
import { SiteHeader } from "@/components/site/site-header";

/** Reference pages (data, sources, methods, about): the header, then the page. No footer; the menu holds the links. */
export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main id="main" tabIndex={-1} className="flex-1 focus:outline-none">
        {children}
      </main>
      <TraceListener />
    </>
  );
}
