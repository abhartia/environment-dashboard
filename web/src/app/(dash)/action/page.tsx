import type { Metadata } from "next";

import { ChapterPage } from "@/components/dash/chapter-page";
import { chapterMeta } from "@/lib/dash/meta";

export const metadata: Metadata = {
  title: chapterMeta("action").title,
  description: "Household choices ranked by the emissions they cut, who emits the most, and how much carbon is left for 1.5 °C. Every number links to its source.",
  alternates: { canonical: "/action" },
};

export default function ActionPage() {
  return <ChapterPage slug="action" />;
}
