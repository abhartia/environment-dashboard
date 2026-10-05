import type { NextConfig } from "next";
import createMDX from "@next/mdx";
import path from "node:path";

/**
 * Static export: the whole site is HTML/CSS/JS on Cloudflare Pages (pattern from gigabiome). There is no server,
 * so no headers(), redirects(), rewrites or proxies here: headers live in public/_headers, and the .com and www
 * hosts are 301ed to https://environmentdashboard.org by Cloudflare Single Redirect rules.
 */
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: false,
  images: { unoptimized: true },
  pageExtensions: ["ts", "tsx", "md", "mdx"],
  turbopack: { root: path.resolve(__dirname, "..") },
};

const withMDX = createMDX({
  options: {
    remarkPlugins: ["remark-gfm"],
  },
});

export default withMDX(nextConfig);
