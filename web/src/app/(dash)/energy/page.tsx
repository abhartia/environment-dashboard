import type { Metadata } from "next";

import { ChapterPage } from "@/components/dash/chapter-page";
import { chapterMeta } from "@/lib/dash/meta";

export const metadata: Metadata = {
  title: chapterMeta("energy").title,
  description: "Clean electricity, the energy mix, country by country, renewable power and electric cars. Every number links to its source.",
  alternates: { canonical: "/energy" },
};

export default function EnergyPage() {
  return <ChapterPage slug="energy" />;
}
