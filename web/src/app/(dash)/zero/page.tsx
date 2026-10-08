import type { Metadata } from "next";

import { ChapterPage } from "@/components/dash/chapter-page";
import { chapterMeta } from "@/lib/dash/meta";

export const metadata: Metadata = {
  title: chapterMeta("zero").title,
  description:
    "The world's emissions in the five activities of Bill Gates's How to Avoid a Climate Disaster, and his five questions: how much of the total, the plan for cement, how much power, how much space, and how much it costs. Every number links to its source.",
  alternates: { canonical: "/zero" },
};

export default function ZeroPage() {
  return <ChapterPage slug="zero" />;
}
