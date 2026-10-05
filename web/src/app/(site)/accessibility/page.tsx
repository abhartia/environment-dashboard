import type { Metadata } from "next";

import { ProsePage } from "@/components/site/prose-page";
import { BRAND } from "@/lib/site";
import { canonical } from "@/lib/site-url";

export const metadata: Metadata = {
  title: "Accessibility",
  description: "The accessibility standard this site aims for, and how to tell us when it falls short.",
  alternates: canonical("/accessibility"),
};

export default function Page() {
  return (
    <ProsePage eyebrow="Accessibility" title="Accessibility">
      <p>
        The site aims to meet the Web Content Accessibility Guidelines (WCAG) 2.2 at level AA. Every chart has a
        written takeaway and can be shown as a table. Colour is never the only way a chart carries meaning, and the
        palettes are chosen to stay distinct for common forms of colour blindness. Pages work without JavaScript, and
        motion is turned off if your device asks for reduced motion.
      </p>
      <h2>Known gaps</h2>
      <p>
        Maps are hard to use with a keyboard or screen reader, so every map has a table listing the same values, and
        country pages can be reached by search.
      </p>
      <p>
        If something is hard to use, write to <span className="select-all">{BRAND.email}</span> and say which page.
      </p>
    </ProsePage>
  );
}
