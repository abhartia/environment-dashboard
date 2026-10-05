import type { Metadata } from "next";

import { ChapterPage } from "@/components/dash/chapter-page";
import { chapterMeta } from "@/lib/dash/meta";

export const metadata: Metadata = {
  title: chapterMeta("heat").title,
  description: "How much warmer the world is, whether independent records agree, how much people caused, and where. Every number links to its source.",
  alternates: { canonical: "/heat" },
};

export default function HeatPage() {
  return <ChapterPage slug="heat" />;
}
