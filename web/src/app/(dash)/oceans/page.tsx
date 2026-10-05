import type { Metadata } from "next";

import { ChapterPage } from "@/components/dash/chapter-page";
import { chapterMeta } from "@/lib/dash/meta";

export const metadata: Metadata = {
  title: chapterMeta("oceans").title,
  description: "Sea level rise and where the water comes from, ocean heat, Arctic sea ice and ocean acidity. Every number links to its source.",
  alternates: { canonical: "/oceans" },
};

export default function OceansPage() {
  return <ChapterPage slug="oceans" />;
}
