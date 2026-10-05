// Copy the pipeline's output into the site before `next build` (the one data door: web never computes a number).
//   ../data/v1/**                 -> public/data/v1/** (served, downloadable) and .generated/v1/** (read at build)
//   ../data-private/v1/indicators -> .generated/v1/indicators (read at build only; never served)
// Every public file is checked against data/SHA256SUMS, and every catalogue entry that is not downloadable must have
// its private export with the sha256 the catalogue records. Anything missing fails the build: no fallbacks.
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../../", import.meta.url));
const WEB = fileURLToPath(new URL("../", import.meta.url));
const DATA = join(ROOT, "data");
const PRIVATE = join(ROOT, "data-private");
const PUBLIC_OUT = join(WEB, "public/data");
const GEN = join(WEB, ".generated");

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");
const die = (m) => {
  console.error(`sync-data: ${m}`);
  process.exit(1);
};

if (!existsSync(join(DATA, "v1/catalog.json"))) die("data/v1/catalog.json missing; run `cd pipeline && uv run envdash build`");
if (!existsSync(join(DATA, "SHA256SUMS"))) die("data/SHA256SUMS missing");

for (const line of readFileSync(join(DATA, "SHA256SUMS"), "utf8").split("\n").filter(Boolean)) {
  const [hash, path] = line.split(/\s+\*?/);
  const file = join(DATA, path);
  if (!existsSync(file)) die(`data/${path} listed in SHA256SUMS but missing`);
  if (sha256(readFileSync(file)) !== hash) die(`data/${path} does not match SHA256SUMS`);
}

rmSync(PUBLIC_OUT, { recursive: true, force: true });
rmSync(GEN, { recursive: true, force: true });
mkdirSync(PUBLIC_OUT, { recursive: true });
cpSync(join(DATA, "v1"), join(PUBLIC_OUT, "v1"), { recursive: true });
cpSync(join(DATA, "v1"), join(GEN, "v1"), { recursive: true });

const catalog = JSON.parse(readFileSync(join(DATA, "v1/catalog.json"), "utf8"));
let privateCount = 0;
for (const entry of catalog.indicators) {
  if (entry.downloadable) continue;
  const src = join(PRIVATE, "v1/indicators", `${entry.id}.json`);
  if (!existsSync(src)) {
    die(`${entry.id} (${entry.licence_class}) has no private export at data-private/v1/indicators/${entry.id}.json. ` +
      "Run the pipeline locally, or `uv run envdash private pull` with R2 credentials.");
  }
  const bytes = readFileSync(src);
  if (sha256(bytes) !== entry.export_sha256) die(`data-private/v1/indicators/${entry.id}.json does not match the catalogue`);
  mkdirSync(join(GEN, "v1/indicators"), { recursive: true });
  cpSync(src, join(GEN, "v1/indicators", `${entry.id}.json`));
  privateCount++;
}
console.log(`sync-data: ${catalog.indicators.length} indicators (${privateCount} shown but not redistributed)`);
