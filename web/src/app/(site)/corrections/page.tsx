import type { Metadata } from "next";

import { ProsePage } from "@/components/site/prose-page";
import { canonical } from "@/lib/site-url";

export const metadata: Metadata = {
  title: "Corrections",
  description: "Mistakes we made, and changes to how a number is calculated, with dates and before-and-after values.",
  alternates: canonical("/corrections"),
};

/** Renders data/errata.yaml (our errors and method changes) once the pipeline publishes it. */
export default function Page() {
  return (
    <ProsePage eyebrow="Corrections" title="Corrections">
      <p>
        This page lists our own mistakes and every change to how a number is calculated, each with the date, the value
        before and after, and the reason. When a producer revises its own data, that revision is noted on the
        number&apos;s data page rather than here.
      </p>
      <p>No corrections have been published.</p>
    </ProsePage>
  );
}
