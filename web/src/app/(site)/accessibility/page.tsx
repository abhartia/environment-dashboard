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
        Maps are hard to use with a keyboard or screen reader. The map of the future on the home page is one stop for
        the Tab key: the arrow keys move to the nearest place in that direction, Enter opens a country or a state, and
        Escape goes back up. The panel beside it reads the chosen place&apos;s values as text, and every country, and
        every state and province the World Bank names, can be found by search. The map needs JavaScript, and it has no table listing every value yet;
        each value is in its published data file, linked from every number.
      </p>
      <p>
        If something is hard to use, write to <span className="select-all">{BRAND.email}</span> and say which page.
      </p>
    </ProsePage>
  );
}
