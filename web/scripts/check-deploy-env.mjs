// Production builds must carry real public config (pattern from gigabiome). A NEXT_PUBLIC_* value is baked in at
// build time, so a missing one fails silently in production; simmerlist lost weeks of analytics that way.
const need = {
  NEXT_PUBLIC_SITE_URL: (v) => v === "https://environmentdashboard.org",
  NEXT_PUBLIC_CF_BEACON_TOKEN: (v) => /^[0-9a-f]{32}$/.test(v ?? ""),
};
const bad = Object.entries(need).filter(([k, ok]) => !ok(process.env[k]));
if (bad.length) {
  console.error(`check-deploy-env: invalid or missing ${bad.map(([k]) => k).join(", ")}`);
  process.exit(1);
}
console.log("check-deploy-env: ok");
