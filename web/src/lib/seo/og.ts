import type { Metadata } from "next";

/** The OpenGraph image for a page path ("/" → /og/home.png; "/causes/x" → /og/causes/x.png). */
export function ogImages(path: string): NonNullable<Metadata["openGraph"]>["images"] {
  const file = path === "/" ? "home" : path.replace(/^\//, "");
  return [{ url: `/og/${file}.png`, width: 1200, height: 630 }];
}
