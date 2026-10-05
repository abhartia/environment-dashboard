import type { Metadata } from "next";

import { StoryPage } from "@/components/site/story-page";
import { ogImages } from "@/lib/seo/og";
import { canonical } from "@/lib/site-url";
import { STORIES, story } from "@/lib/stories";

export const dynamicParams = false;

export function generateStaticParams() {
  return STORIES.filter((s) => s.section === "causes").map((s) => ({ slug: s.slug }));
}

export async function generateMetadata({ params }: PageProps<"/causes/[slug]">): Promise<Metadata> {
  const s = story("causes", (await params).slug);
  return { title: s.title, description: s.description, alternates: canonical(`/causes/${s.slug}`), openGraph: { images: ogImages(`/causes/${s.slug}`) } };
}

export default async function Page({ params }: PageProps<"/causes/[slug]">) {
  return <StoryPage section="causes" slug={(await params).slug} />;
}
