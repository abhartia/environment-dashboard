import type { Metadata } from "next";
import Link from "next/link";

import { ProsePage } from "@/components/site/prose-page";
import { BRAND } from "@/lib/site";
import { canonical } from "@/lib/site-url";

export const metadata: Metadata = {
  title: "Methods",
  description:
    "How every number is sourced, fetched, archived, transformed, checked and licensed, and the rules that keep it traceable.",
  alternates: canonical("/methods"),
};

export default function Page() {
  return (
    <ProsePage
      eyebrow="Methods"
      title="How every number is sourced and checked"
      lede={<p>The rules this site follows, so that anyone can take a number from it and trace it to the original data.</p>}
    >
      <h2>Where the numbers come from</h2>
      <p>
        Each number comes from an organisation that measures or compiles it: national science agencies, international
        bodies, research groups and peer-reviewed papers. We use the producer&apos;s own files rather than copies on
        other sites. Where a widely used aggregator processes the same data, we still cite the producer. Every source
        is listed on <Link href="/sources">Sources</Link> with its citation, licence and current status.
      </p>
      <p>
        One series comes from one source. We never stitch two sources into one line. Where respected sources disagree,
        we show both and explain why.
      </p>

      <h2>How a number is fetched and kept</h2>
      <ol>
        <li>
          A scheduled job downloads each file from the producer&apos;s address and records the date, the server&apos;s
          version headers, and a sha256 fingerprint of the exact bytes. If the file is unchanged, nothing is rebuilt.
        </li>
        <li>
          The bytes are stored in our archive. Where the licence allows, that copy is public, and the producer&apos;s
          page is also captured by the Internet Archive&apos;s Wayback Machine, so a number stays traceable even if
          the original moves or disappears.
        </li>
        <li>
          Some producers block automated downloads. Their files are downloaded by a person and recorded the same way,
          and the data page says so.
        </li>
      </ol>

      <h2>What we do to the data</h2>
      <p>
        As little as possible, and every step is written down. Each number&apos;s data page lists the steps in plain
        words, such as “re-expressed relative to the dataset&apos;s own 1850–1900 average”, along with the code that
        did it and a fingerprint of that code. Values are stored unrounded and rounded only for display. Nothing is
        filled in: a gap in the data stays a gap.
      </p>
      <ul>
        <li>
          <strong>Temperatures</strong> are shown relative to 1850–1900 where the dataset covers that period, using
          that dataset&apos;s own average. Where it does not, the data page states the baseline used.
        </li>
        <li>
          <strong>Greenhouse gas totals</strong> state which warming factor they use to combine gases (for example
          100-year global warming potentials from the IPCC&apos;s fifth or sixth assessment) and whether land use is
          included.
        </li>
        <li>
          <strong>Preliminary values</strong>, such as the current month or a year in progress, are labelled as such.
        </li>
      </ul>

      <h2>How numbers are checked</h2>
      <p>
        Where a producer states a value in its own words (for example in a press release or report), an automated test
        compares our number with that statement for the same version of the data. Each published number is also
        re-derived independently from the stored file before it first appears on the site. Sentences that claim a
        record or a ranking are checked against the data every time it updates, so an update cannot silently make the
        text wrong.
      </p>

      <h2>Licences</h2>
      <p>
        Each producer sets the terms for its data, and the site follows them. Most data can be shown and shared with
        credit; you can download those numbers from their data page under the same terms. Some producers allow sharing
        only for non-commercial use, or ask that derived versions carry the same licence; the download says so. A few
        allow their published figures to be shown but not redistributed or recalculated. Those numbers appear with a
        citation and a link to the original, without a download. The licence of every figure is shown beside it.
      </p>

      <h2>Updates and corrections</h2>
      <p>
        The data is checked weekly. When a producer publishes a new version, the affected numbers update and their data
        pages record the new version. If a source fails to update or changes format, its numbers stay at the last
        version that passed our checks, and <Link href="/status">Status</Link> says so. Our own mistakes are fixed and
        listed on <Link href="/corrections">Corrections</Link>.
      </p>

      <h2>Reproducing the numbers</h2>
      <p>
        The pipeline that fetches, transforms and checks the data is public at <a href={BRAND.repo}>GitHub</a>. Its
        output for each number lists the fingerprints of its input files, so you can confirm you are working from the
        same bytes.
      </p>
    </ProsePage>
  );
}
