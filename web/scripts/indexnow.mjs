// Tell IndexNow (Bing, Yandex, Seznam, Naver...) which URLs a deploy added or changed.
// The key file is public/<key>.txt, as the protocol requires.
//
// Only URLs that are new, or whose <lastmod> moved, against the sitemap that was live before this deploy
// (`node scripts/indexnow.mjs <previous-sitemap.xml>`). Re-posting unchanged URLs on every deploy is how
// simmerlist taught bingbot to stop reading its submissions (its 2026-09-29 worklog entry). A previous
// sitemap with no URLs means a first deploy, which submits everything.
import { readdirSync, readFileSync } from "node:fs";

const previousPath = process.argv[2];
if (!previousPath) throw new Error("usage: node scripts/indexnow.mjs <previous-sitemap.xml>");

/** url -> lastmod for every <url> entry. */
function entries(xml) {
  return new Map(
    [...xml.matchAll(/<url>([\s\S]*?)<\/url>/g)].map((m) => [
      m[1].match(/<loc>([^<]+)<\/loc>/)[1],
      m[1].match(/<lastmod>([^<]+)<\/lastmod>/)?.[1] ?? null,
    ]),
  );
}

const publicDir = new URL("../public/", import.meta.url);
const keyFile = readdirSync(publicDir).find((f) => /^[0-9a-f]{32}\.txt$/.test(f));
if (!keyFile) throw new Error("No IndexNow key file in public/");
const key = keyFile.replace(".txt", "");

const current = entries(readFileSync(new URL("../out/sitemap.xml", import.meta.url), "utf8"));
const previous = entries(readFileSync(previousPath, "utf8"));
const urlList = [...current].filter(([url, lastmod]) => previous.get(url) !== lastmod).map(([url]) => url);
if (urlList.length === 0) {
  console.log(`indexnow: nothing new or changed among ${current.size} URLs; not submitting`);
  process.exit(0);
}
const host = new URL(urlList[0]).host;

const res = await fetch("https://api.indexnow.org/indexnow", {
  method: "POST",
  headers: { "Content-Type": "application/json; charset=utf-8" },
  body: JSON.stringify({ host, key, keyLocation: `https://${host}/${keyFile}`, urlList }),
});
console.log(`indexnow: ${res.status} for ${urlList.length} of ${current.size} URLs`);
for (const url of urlList) console.log(`  ${url}`);
if (res.status >= 400 && res.status !== 429) process.exit(1);
