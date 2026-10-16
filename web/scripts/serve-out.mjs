// Serve the static export (out/) the way Cloudflare Pages does, for browser tests: clean URLs (/about -> about.html,
// / -> index.html) and the response headers declared for every path in public/_headers (so a Content-Security-Policy
// violation shows up as a console error, as it would in production). Usage: node scripts/serve-out.mjs [port]
import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = fileURLToPath(new URL("../out/", import.meta.url));
const HEADERS = fileURLToPath(new URL("../public/_headers", import.meta.url));
const PORT = Number(process.argv[2] ?? process.env.PORT ?? 3210);

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".csv": "text/csv; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".woff2": "font/woff2",
  ".ico": "image/x-icon",
  ".xml": "application/xml",
};

/** The headers of the `/*` block of public/_headers (the ones every page gets). */
function globalHeaders() {
  const lines = readFileSync(HEADERS, "utf8").split("\n");
  const start = lines.findIndex((l) => l.trim() === "/*");
  const out = {};
  for (const line of lines.slice(start + 1)) {
    if (!line.startsWith(" ") && !line.startsWith("\t")) break;
    const i = line.indexOf(":");
    if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return out;
}
const COMMON = globalHeaders();

function resolve(pathname) {
  const clean = normalize(decodeURIComponent(pathname)).replace(/^(\.\.[/\\])+/, "");
  const base = join(OUT, clean);
  for (const candidate of [base, `${base}.html`, join(base, "index.html")]) {
    if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  }
  return null;
}

createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost");
  const file = url.pathname === "/" ? join(OUT, "index.html") : resolve(url.pathname);
  for (const [k, v] of Object.entries(COMMON)) if (k !== "Strict-Transport-Security") res.setHeader(k, v);
  if (!file) {
    res.statusCode = 404;
    res.setHeader("Content-Type", TYPES[".html"]);
    createReadStream(join(OUT, "404.html")).pipe(res);
    return;
  }
  res.setHeader("Content-Type", TYPES[extname(file)] ?? "application/octet-stream");
  createReadStream(file).pipe(res);
}).listen(PORT, () => console.log(`serving out/ on http://localhost:${PORT}`));
