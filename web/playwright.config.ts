import { defineConfig, devices } from "@playwright/test";

/**
 * Browser tests of the built site (out/, from `npm run build`), served the way Cloudflare Pages serves it, with the
 * production response headers. Run with `npx playwright test` after a build.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3210", ...devices["Desktop Chrome"] },
  webServer: { command: "node scripts/serve-out.mjs 3210", url: "http://localhost:3210", reuseExistingServer: true, timeout: 30_000 },
});
