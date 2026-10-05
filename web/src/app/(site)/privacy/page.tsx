import type { Metadata } from "next";

import { ProsePage } from "@/components/site/prose-page";
import { canonical } from "@/lib/site-url";

export const metadata: Metadata = {
  title: "Privacy",
  description: "What this site collects (aggregate, cookieless page counts) and what it does not.",
  alternates: canonical("/privacy"),
};

export default function Page() {
  return (
    <ProsePage eyebrow="Privacy" title="Privacy">
      <p>
        The site has no accounts, no forms, no cookies and no advertising. It counts page views with Cloudflare Web
        Analytics, which does not use cookies or local storage and does not fingerprint visitors. It records which page
        was viewed, the referring site, the country and the browser type, in aggregate.
      </p>
      <p>
        Calculators run entirely in your browser. What you type into them is not sent anywhere, stored, or put in the
        page address. The country you last picked in a chart is remembered in your own browser only, so the next chart
        can show it too; clearing your browser data removes it.
      </p>
      <p>
        “Report a problem” links open GitHub, which has its own privacy policy. Email to the site address is read by
        the person who runs it and is not shared.
      </p>
    </ProsePage>
  );
}
