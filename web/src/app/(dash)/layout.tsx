import { TraceListener } from "@/components/data/trace-listener";
import { SiteHeader } from "@/components/site/site-header";

/**
 * The dashboard (home and chapters): exactly one screen. The header and the view share the viewport height and the
 * page never scrolls; each view lays itself out in the space left (h-full), not in a guessed calc().
 */
export default function DashLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-svh flex-col overflow-hidden">
      <SiteHeader />
      <main id="main" tabIndex={-1} className="min-h-0 flex-1 focus:outline-none">
        {children}
      </main>
      <TraceListener />
    </div>
  );
}
