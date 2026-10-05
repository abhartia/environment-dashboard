import type { Metadata } from "next";

import { SectionIndex } from "@/components/site/section-index";
import { SECTIONS } from "@/lib/sections";
import { ogImages } from "@/lib/seo/og";
import { canonical } from "@/lib/site-url";

const section = SECTIONS[1];

export const metadata: Metadata = {
  title: section.label,
  description: `${section.question} ${section.intro}`,
  alternates: canonical(section.href),
  openGraph: { images: ogImages(section.href) },
};

export default function Page() {
  return <SectionIndex section={section} />;
}
