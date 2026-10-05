import type { Metadata } from "next";

import { ChapterPage } from "@/components/dash/chapter-page";
import { chapterMeta } from "@/lib/dash/meta";

export const metadata: Metadata = {
  title: chapterMeta("people").title,
  description: "Deaths from heat, heatwave days caused by climate change, and working hours lost to heat. Every number links to its source.",
  alternates: { canonical: "/people" },
};

export default function PeoplePage() {
  return <ChapterPage slug="people" />;
}
