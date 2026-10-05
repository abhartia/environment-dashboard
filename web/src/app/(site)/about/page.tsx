import type { Metadata } from "next";
import Link from "next/link";

import { ProsePage } from "@/components/site/prose-page";
import { BRAND } from "@/lib/site";
import { canonical } from "@/lib/site-url";

export const metadata: Metadata = {
  title: "About",
  description: "Why this site exists, who it is for, and how it is kept honest.",
  alternates: canonical("/about"),
};

export default function Page() {
  return (
    <ProsePage eyebrow="About" title="Why this site exists">
      <p>
        Climate change is easier to act on when the chain from cause to consequence is clear. This site lays out that
        chain with public data: what people burn, farm and clear; what that does to the air, the oceans and the
        temperature; what that does to people and nature; and which choices change the outcome.
      </p>
      <p>
        It is built so that anyone can check it. Every number links to the file it came from, the version of that
        file, when it was fetched, what was done to it, and the terms it is shared under. The code that fetches and
        transforms the data is public at <a href={BRAND.repo}>GitHub</a>, so the steps can be repeated.
      </p>
      <h2>What it is not</h2>
      <ul>
        <li>It sells nothing, has no accounts and asks for no personal details.</li>
        <li>
          It does not give advice. It describes what the evidence says about each option, with its range, and leaves
          the choice to the reader.
        </li>
        <li>
          It is not affiliated with the organisations whose data it shows. Showing their data does not mean they
          endorse the site.
        </li>
      </ul>
      <h2>How it is kept honest</h2>
      <p>
        The rules are written down in <Link href="/methods">Methods</Link>. Mistakes are fixed in the open and listed on{" "}
        <Link href="/corrections">Corrections</Link>. If a number looks wrong, open its data page and use “Report a
        problem”, or write to <span className="select-all">{BRAND.email}</span>.
      </p>
    </ProsePage>
  );
}
