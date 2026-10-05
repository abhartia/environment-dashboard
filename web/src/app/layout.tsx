import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Newsreader } from "next/font/google";

import { JsonLd } from "@/components/site/json-ld";
import { siteGraph } from "@/lib/seo/structured-data";
import { BRAND } from "@/lib/site";
import { SITE_URL } from "@/lib/site-url";
import "./globals.css";

// Headings: Newsreader (variable serif with optical sizes), for an editorial voice.
const newsreader = Newsreader({ variable: "--font-newsreader", subsets: ["latin"], axes: ["opsz"], display: "swap" });
// Body and UI: Inter (variable), with tabular figures for numbers.
const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" });
// Hashes and ids on provenance pages only; never the LCP element, so not preloaded.
const jetbrains = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"], display: "swap", preload: false });

export const viewport: Viewport = { themeColor: "#faf9f6" };

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: `${BRAND.name} · ${BRAND.tagline}`, template: `%s · ${BRAND.name}` },
  description: BRAND.description,
  applicationName: BRAND.name,
  openGraph: { type: "website", siteName: BRAND.name, locale: "en_US", images: [{ url: "/og/home.png", width: 1200, height: 630 }] },
  twitter: { card: "summary_large_image" },
  alternates: { canonical: SITE_URL },
};

// Cloudflare Web Analytics: cookieless, no consent banner needed. Empty token = off (check-deploy-env requires it).
const CF_BEACON = process.env.NEXT_PUBLIC_CF_BEACON_TOKEN;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${newsreader.variable} ${inter.variable} ${jetbrains.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <JsonLd data={siteGraph()} />
        {children}
        {CF_BEACON ? (
          <script
            defer
            src="https://static.cloudflareinsights.com/beacon.min.js"
            data-cf-beacon={JSON.stringify({ token: CF_BEACON })}
          />
        ) : null}
      </body>
    </html>
  );
}
