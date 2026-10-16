// Post-build checks on the static export in out/ (structure and helpers from gigabiome). Fails the build on:
//  - missing robots.txt, sitemap.xml, llms.txt, 404.html or the IndexNow key file
//  - a sitemap URL without an HTML file, or whose canonical isn't itself on https://environmentdashboard.org
//  - an indexable page without exactly one <h1>, or without a link to /about; /about without the disclaimers
//  - "live"/"real-time" claims, fabricated social proof, or imperative advice ("you should") in visible text
//  - implementation vocabulary in story copy (format names are fine on /data, /sources, /methods, /status)
//  - a [data-indicator] that doesn't resolve in the catalogue, or whose indicator has no /data page
//  - a link or button nested in another, or a home "so what" band without exactly one traced number
//  - any file from a no-derivatives or display-only indicator under out/ (those values are shown, never served)
//  - a data file in out/ that doesn't match data/SHA256SUMS (proves sync-data copied exactly)
//  - a published (redistributable) indicator that no dashboard view shows
//  - any file over 20 MiB, or more than 15,000 files (Cloudflare Pages: 20,000 files, 25 MiB each)
//  - a future-map value that differs from its published observation, a future map not served, a search place that
//    opens no future view, a search index over 1 MiB, or map files whose licence forbids redistribution
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = fileURLToPath(new URL("../out/", import.meta.url));
const DATA = fileURLToPath(new URL("../../data/", import.meta.url));
const CANONICAL_ORIGIN = "https://environmentdashboard.org";
const MAX_FILE_BYTES = 20 * 1024 * 1024;
const MAX_FILES = 15_000;

const errors = [];
const fail = (m) => errors.push(m);

function walk(dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}
const files = walk(OUT);
const rel = (f) => f.replace(OUT, "");

// --- Required files, limits -----------------------------------------------------------------

for (const f of ["robots.txt", "sitemap.xml", "llms.txt", "404.html"]) {
  if (!existsSync(join(OUT, f))) fail(`missing out/${f}`);
}
if (!files.some((f) => /^[0-9a-f]{32}\.txt$/.test(rel(f)))) fail("missing the IndexNow key file out/<32 hex>.txt");
if (files.length > MAX_FILES) fail(`out/ has ${files.length} files, over the ${MAX_FILES} limit we keep below Pages' 20,000`);
for (const f of files) {
  const size = statSync(f).size;
  if (size > MAX_FILE_BYTES) fail(`${rel(f)} is ${(size / 1048576).toFixed(1)} MiB, over the 20 MiB limit`);
}

// --- Data: exact copy of data/, nothing private --------------------------------------------

const catalogPath = join(DATA, "v1/catalog.json");
const catalog = existsSync(catalogPath) ? JSON.parse(readFileSync(catalogPath, "utf8")) : null;
if (!catalog) fail("data/v1/catalog.json is missing (run the pipeline: cd pipeline && uv run envdash build)");
const indicators = new Map((catalog?.indicators ?? []).map((e) => [e.id, e]));
const privateIds = [...indicators.values()].filter((e) => !e.downloadable).map((e) => e.id);

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");
const sumsPath = join(DATA, "SHA256SUMS");
if (existsSync(sumsPath)) {
  for (const line of readFileSync(sumsPath, "utf8").split("\n").filter(Boolean)) {
    const [hash, path] = line.split(/\s+\*?/);
    if (!path.startsWith("v1/")) continue;
    const served = join(OUT, "data", path);
    if (!existsSync(served)) fail(`out/data/${path} is listed in data/SHA256SUMS but not served`);
    else if (sha256(readFileSync(served)) !== hash) fail(`out/data/${path} differs from data/${path}`);
  }
} else fail("data/SHA256SUMS is missing");
for (const f of files) {
  const r = rel(f);
  for (const id of privateIds) {
    if (r.includes(`${id}.json`) || r.includes(`${id}.csv`)) fail(`${r}: a file of ${id}, whose licence forbids redistribution, is served`);
  }
}

// --- Every published dataset is on the dashboard -------------------------------------------
// A dataset we may redistribute is published to be seen: each one must be shown by at least one dashboard view
// (out/dash-data/<chapter>/<node>.json lists the indicators it draws). No-derivatives and display-only values never go
// into those files, so they are exempt and stay on their server-rendered data pages.

const shown = new Set();
for (const f of files.filter((f) => rel(f).startsWith("dash-data/") && f.endsWith(".json"))) {
  for (const id of JSON.parse(readFileSync(f, "utf8")).indicators ?? []) shown.add(id);
}
for (const e of indicators.values()) {
  if (e.downloadable && !shown.has(e.id)) fail(`${e.id} is published but no dashboard view shows it (add it to a node in web/src/lib/dash/)`);
}

// --- The future map: every value is the published one, every map and place is served ---------------------------
// A future node (out/dash-data/future/<node>.json) carries every value a reader can choose (lib/dash/future-tree.ts).
// Each cell [median, 10th, 90th percentile] must equal its observation in the indicator the panel traces it to (the
// regions' file for a region, the countries' file otherwise), and a cell must be null exactly where no row exists.

const SEARCH_MAX_BYTES = 1024 * 1024;
const FUTURE_NODE_MAX_BYTES = 2 * 1024 * 1024;
const tables = new Map();
function rowsOf(id) {
  if (tables.has(id)) return tables.get(id);
  const path = join(DATA, "v1/indicators", `${id}.json`);
  const out = new Map();
  if (!existsSync(path)) fail(`future: ${id} is not in data/v1/indicators`);
  else {
    const t = JSON.parse(readFileSync(path, "utf8")).table;
    for (let i = 0; i < t.entity.length; i++) {
      out.set(`${t.entity[i]}|${t.period[i]}|${t.dims.scenario[i]}`, [t.value[i], t.lower?.[i] ?? null, t.upper?.[i] ?? null]);
    }
  }
  tables.set(id, out);
  return out;
}
// The map files are public downloads like any data file: shapes whose terms forbid redistribution are never served.
{
  const geoIndex = join(DATA, "v1/geo/index.json");
  if (existsSync(geoIndex)) {
    const cls = JSON.parse(readFileSync(geoIndex, "utf8")).licence_class;
    if (!["open", "share-alike", "noncommercial"].includes(cls) && existsSync(join(OUT, "data/v1/geo"))) {
      fail(`data/v1/geo is ${cls}: map files whose terms forbid redistribution are served`);
    }
  }
}
const futureDir = join(OUT, "dash-data/future");
const futureNodes = new Map();
for (const f of files.filter((f) => rel(f).startsWith("dash-data/future/"))) {
  const r = rel(f);
  if (statSync(f).size > FUTURE_NODE_MAX_BYTES) fail(`${r}: ${statSync(f).size} bytes, over ${FUTURE_NODE_MAX_BYTES}`);
  const node = JSON.parse(readFileSync(f, "utf8"));
  futureNodes.set(node.id, node);
  const p = node.future;
  if (!p) {
    fail(`${r}: a future node without its payload`);
    continue;
  }
  if (p.geo !== null && !existsSync(join(OUT, "data", p.geo))) fail(`${r}: its map ${p.geo} is not served`);
  for (const m of p.measures) {
    for (const [slice, cells] of Object.entries(p.values[m.key] ?? {})) {
      const [period, scenario] = slice.split("|");
      if (cells.length !== p.places.length) fail(`${r}: ${m.key} ${slice} has ${cells.length} cells for ${p.places.length} places`);
      p.places.forEach((place, i) => {
        const id = place.kind === "region" ? m.regions : m.countries;
        const want = rowsOf(id).get(`${place.entity}|${period}|${scenario}`) ?? null;
        const got = cells[i];
        if (JSON.stringify(want) !== JSON.stringify(got)) {
          fail(`${r}: ${m.key} ${place.entity} ${slice} is ${JSON.stringify(got)}, published ${JSON.stringify(want)} in ${id}`);
        }
      });
    }
  }
}
if (existsSync(futureDir) && !futureNodes.has("root")) fail("dash-data/future/root.json is missing");
{
  const index = join(OUT, "search-index.json");
  if (!existsSync(index)) fail("search-index.json is missing");
  else {
    if (statSync(index).size > SEARCH_MAX_BYTES) fail(`search-index.json: ${statSync(index).size} bytes, over ${SEARCH_MAX_BYTES}`);
    // Every place the search offers opens a future view that has it.
    for (const item of JSON.parse(readFileSync(index, "utf8")).filter((i) => i.kind === "place")) {
      const q = new URLSearchParams(item.href.replace(/^\/\?/, ""));
      const node = futureNodes.get(`c-${q.get("c")}`);
      if (q.get("mode") !== "future" || !node) fail(`search: ${item.title} opens ${item.href}, which has no future view`);
      else if (q.get("r") && !node.future.places.some((p) => p.entity === q.get("r"))) fail(`search: ${item.title} names a region c-${q.get("c")} does not have`);
    }
  }
}

// --- Sitemap and canonicals -----------------------------------------------------------------

const sitemap = existsSync(join(OUT, "sitemap.xml")) ? readFileSync(join(OUT, "sitemap.xml"), "utf8") : "";
const urls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
for (const url of urls) {
  const { pathname, origin } = new URL(url);
  if (origin !== CANONICAL_ORIGIN) fail(`sitemap URL on ${origin}, expected ${CANONICAL_ORIGIN}`);
  const file = pathname === "/" ? join(OUT, "index.html") : join(OUT, `${pathname}.html`);
  if (!existsSync(file)) {
    fail(`sitemap URL has no page: ${url}`);
    continue;
  }
  const html = readFileSync(file, "utf8");
  const canon = html.match(/<link rel="canonical" href="([^"]+)"/)?.[1];
  const expected = pathname === "/" ? origin : url;
  if (canon !== expected) fail(`${pathname}: canonical is ${canon}, expected ${expected}`);
}

// --- HTML helpers ---------------------------------------------------------------------------

/** The page's markup without inline scripts (JSON-LD, the RSC payload) or styles. */
const markupOf = (html) => html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "").replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, "");
const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
function decodeEntities(s) {
  return s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, (_, e) => {
    const k = e.toLowerCase();
    if (k.startsWith("#x")) return String.fromCodePoint(parseInt(k.slice(2), 16));
    if (k.startsWith("#")) return String.fromCodePoint(parseInt(k.slice(1), 10));
    return ENTITIES[k];
  });
}
const norm = (s) => s.replace(/\s+/g, " ").trim();
const wordsOf = (markup) => norm(decodeEntities(markup.replace(/<!--[\s\S]*?-->/g, " ").replace(/<[^>]*>/g, " ")));
const ATTR_TEXT = /\s(?:alt|aria-label|title|placeholder)="([^"]*)"/g;
/** Everything a visitor reads on the page: the body's text plus its readable attributes, title and descriptions. */
function visibleText(markup) {
  const body = markup.match(/<body[\s>][\s\S]*<\/body>/)?.[0] ?? "";
  const head = markup.match(/<title>([\s\S]*?)<\/title>/)?.[1] ?? "";
  const meta = [...markup.matchAll(/<meta\s+(?:name|property)="(?:description|og:title|og:description|twitter:title|twitter:description)"\s+content="([^"]*)"/g)].map((m) => m[1]);
  const attrs = [...body.matchAll(ATTR_TEXT)].map((m) => m[1]);
  return norm([decodeEntities(head), ...meta.map(decodeEntities), wordsOf(body), ...attrs.map(decodeEntities)].join(" "));
}
const textOf = (markup) => norm(decodeEntities(markup.replace(/<[^>]*>/g, " ")));
const count = (s, re) => (s.match(re) ?? []).length;

// --- Per-page checks ------------------------------------------------------------------------

const BANNED = [
  ...[/aggregateRating/i, /"@type":"Review"/i, /trusted by/i, /testimonial/i].map((re) => ({ re, why: "no fabricated social proof" })),
  ...[/\bLIVE\b/, /live (data|feed|updates?)/i, /real[- ]time/i].map((re) => ({
    re,
    why: "the site shows the latest published data, never a live feed",
  })),
];
/** Options are described by their measured effect, never as instructions (docs/style.md). */
const IMPERATIVE = /\byou (?:should|must|need to|have to)\b/i;
/** How the site is built, not what it means for the reader. Allowed on the pages whose job is to describe the data files. */
const IMPLEMENTATION_WORDS = [/\bPython\b/, /\bpipeline\b/i, /\bregex\b/i, /\bschema\b/i, /\bpolars\b/i, /\bpydantic\b/i];
const TECHNICAL_PAGES = /^(data|sources|methods|status)(\/|\.html$)/;
for (const id of indicators.keys()) if (id.startsWith("v1.")) fail(`indicator id ${id} would collide with /data/v1/`);
const NOINDEX = '<meta name="robots" content="noindex';

for (const f of files.filter((f) => f.endsWith(".html"))) {
  const html = readFileSync(f, "utf8");
  const page = rel(f);
  const markup = markupOf(html);
  const text = visibleText(markup);
  // Producers' own words (licence terms, quoted statements) are shown verbatim in <blockquote>; voice rules apply to ours.
  const ownText = visibleText(markup.replace(/<blockquote\b[\s\S]*?<\/blockquote>/gi, " "));

  for (const { re, why } of BANNED) if (re.test(ownText)) fail(`${page}: matches ${re} (${why})`);
  const imperative = ownText.match(IMPERATIVE);
  if (imperative) fail(`${page}: '${imperative[0]}' (describe options by their effect; see docs/style.md)`);
  if (!TECHNICAL_PAGES.test(page)) {
    for (const re of IMPLEMENTATION_WORDS) {
      const hit = text.match(re);
      if (hit) fail(`${page}: visible text contains '${hit[0]}' (implementation vocabulary)`);
    }
  }

  // Invalid nesting breaks hydration (React rebuilds the tree on the client): no <p> inside a <p>.
  for (const m of markup.matchAll(/<p[\s>](?:(?!<\/p>)[\s\S])*?<p[\s>]/g)) {
    fail(`${page}: a <p> is nested in another <p> near "${textOf(m[0]).slice(0, 60)}"`);
    break;
  }
  if (page !== "404.html" && !html.includes(NOINDEX)) {
    const h1s = count(markup, /<h1[\s>]/g);
    if (h1s !== 1) fail(`${page}: ${h1s} <h1> elements, expected exactly 1`);
    // No footer: every page links to /about, which carries the disclaimers (checked below).
    if (!/<a\b[^>]*\shref="\/about"/.test(markup)) fail(`${page}: no link to /about (where the disclaimers are)`);
  }

  // Internal links must land on a page or a file in the export (no links to stories that do not exist yet).
  for (const [, href] of markup.matchAll(/<a\b[^>]*\shref="(\/[^"#?]*)/g)) {
    const p = decodeURIComponent(href).replace(/\/$/, "");
    const target = p === "" ? "index.html" : p.slice(1);
    if (![target, `${target}.html`, `${target}/index.html`].some((t) => existsSync(join(OUT, t)))) fail(`${page}: links to ${href}, which is not in the export`);
  }
  for (const [, id] of markup.matchAll(/\sdata-indicator="([^"]+)"/g)) {
    if (!indicators.has(id)) fail(`${page}: data-indicator="${id}" is not in data/v1/catalog.json`);
    else if (!existsSync(join(OUT, "data", `${id.split(".").join("/")}.html`))) fail(`${page}: ${id} has no data page`);
  }

  // A link or button inside another is invalid HTML: a tap's target is ambiguous and hydration rebuilds the tree.
  const open = { a: 0, button: 0 };
  for (const m of markup.matchAll(/<(\/?)(a|button)\b[^>]*>/g)) {
    const [, closing, tag] = m;
    if (closing) {
      open[tag] = Math.max(0, open[tag] - 1);
      continue;
    }
    if (open.a + open.button > 0) {
      fail(`${page}: a <${tag}> inside another link or button near "${textOf(markup.slice(m.index, m.index + 200)).slice(0, 60)}"`);
      break;
    }
    open[tag] += 1;
  }

  // Each home "so what" band shows exactly one traced number (data-sowhat-of names its band), so it has a source.
  for (const [, key] of markup.matchAll(/\sdata-sowhat="([^"]+)"/g)) {
    const numbers = [...markup.matchAll(new RegExp(`<a\\b[^>]*\\sdata-sowhat-of="${key}"[^>]*>`, "g"))];
    if (numbers.length !== 1) fail(`${page}: the "${key}" band has ${numbers.length} traced numbers, expected 1`);
    else if (!/\sdata-indicator="[^"]+"/.test(numbers[0][0])) fail(`${page}: the "${key}" band's number has no data-indicator`);
  }
}

{
  const about = join(OUT, "about.html");
  if (!existsSync(about) || !readFileSync(about, "utf8").includes("data-disclaimers")) fail("about.html: missing the disclaimers");
}

if (errors.length) {
  console.error(`check-build: ${errors.length} problem(s)\n - ${errors.join("\n - ")}`);
  process.exit(1);
}
console.log(`check-build: ok (${files.length} files, ${urls.length} sitemap URLs, ${indicators.size} indicators in the catalogue)`);
