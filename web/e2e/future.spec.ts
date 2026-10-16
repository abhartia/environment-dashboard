import { expect, test, type Page } from "@playwright/test";

import { pageScrolls, probe } from "./probe";

/**
 * Future mode in a real browser, on the built site: the story hands over to the map, every view fits one screen with
 * every word readable, every number is traced, and the map answers to a mouse, a finger, the keyboard and the back
 * button. Run after `npm run build` with `npx playwright test`.
 */

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900, touch: false },
  { name: "laptop", width: 1366, height: 657, touch: false },
  { name: "tablet", width: 768, height: 1024, touch: true },
  { name: "phone", width: 375, height: 812, touch: true },
  { name: "small phone", width: 375, height: 667, touch: true },
];

/** The world, a large country, a small one, one with many states, one across the 180° line, and a region (Delhi). */
const PLACES: { name: string; c?: string; r?: string }[] = [
  { name: "world" },
  { name: "India", c: "IND" },
  { name: "Latvia", c: "LVA" },
  { name: "United States of America", c: "USA" },
  { name: "Fiji", c: "FJI" },
  { name: "Delhi", c: "IND", r: "IND.11510" },
];

type RootNode = { future: { measures: { key: string }[] } };

function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  return errors;
}

/** Links and buttons inside one another (invalid, and a screen reader cannot reach the inner one). */
async function nestedInteractive(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll("a a, a button, button a, button button")].map((el) => `${el.tagName} "${(el.textContent ?? "").trim().slice(0, 40)}"`),
  );
}

/**
 * Numbers in the panel that are not traced: every run of digits in its text must sit inside an a[data-indicator]
 * (the window chart's axis and a window's own years, "2040–2059", are labels, not values).
 */
async function untracedNumbers(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    const panel = document.querySelector("section[data-probe]");
    if (!panel) return ["no panel"];
    const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const text = (n.textContent ?? "").replace(/\b\d{4}[–-]\d{4}\b/g, "");
      if (!/\d/.test(text)) continue;
      const el = n.parentElement;
      if (!el || el.closest("a[data-indicator]") || el.closest("svg")) continue;
      // A unit label carries its threshold ("35 °C or more"): words of the measure, not a value.
      if (/°C or more|heat index of|less than \d+ mm|warmer than the \d{4}/.test(text)) continue;
      // Which percentiles the models' range runs between is the definition of the range, read from the data.
      if (/from the \d+th to the \d+th percentile/.test(text)) continue;
      // An emissions path's name ("SSP2-4.5, middle emissions") is a name, not a value.
      if (/^SSP\d-\d\.\d, [a-z ]+$/.test(text.trim())) continue;
      out.push(text.trim());
    }
    return out;
  });
}

async function measures(page: Page): Promise<string[]> {
  const res = await page.request.get("/dash-data/future/root.json");
  expect(res.ok()).toBeTruthy();
  return ((await res.json()) as RootNode).future.measures.map((m) => m.key);
}

function futureUrl(m: string, c?: string, r?: string): string {
  const q = new URLSearchParams({ mode: "future", p: "2040-2059", s: "ssp245", m });
  if (c) q.set("c", c);
  if (r) q.set("r", r);
  return `/?${q}`;
}

/** The panel has its place and its traced number, and the map is drawn. */
async function settled(page: Page, place: string) {
  await expect(page.locator("section[data-probe] nav [aria-current=page]")).toHaveText(place, { timeout: 15_000 });
  await expect(page.locator("section[data-probe] a[data-indicator]").first()).toBeVisible();
  await expect(page.locator("svg[role=group] g[data-id]").first()).toBeAttached();
  await page.waitForTimeout(900);
}

for (const vp of VIEWPORTS) {
  test.describe(`${vp.name} ${vp.width}×${vp.height}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height }, hasTouch: vp.touch, isMobile: vp.width < 768 });

    test("the story flows into the map, without ever scrolling the page", async ({ page }) => {
      const errors = watchErrors(page);
      await page.goto("/");
      let scrolled = false;
      const deadline = Date.now() + 30_000;
      while (!page.url().includes("mode=future") && Date.now() < deadline) {
        if (await pageScrolls(page)) scrolled = true;
        await page.waitForTimeout(250);
      }
      expect(page.url()).toContain("mode=future");
      expect(page.url()).toContain("p=2040-2059");
      expect(page.url()).toContain("s=ssp245");
      expect(scrolled).toBe(false);
      await expect(page.getByRole("slider")).toHaveText(/^\d{4}–\d{4}$/);
      await settled(page, await page.locator("section[data-probe] nav [aria-current=page]").innerText());
      expect(await page.locator("svg[role=group] g[data-id]").count()).toBeGreaterThanOrEqual(200);
      expect(await pageScrolls(page)).toBe(false);
      expect(await probe(page)).toEqual([]);
      expect(errors).toEqual([]);
    });

    for (const pl of PLACES) {
      test(`${pl.name}: every measure fits, every number is traced`, async ({ page }) => {
        const errors = watchErrors(page);
        for (const m of await measures(page)) {
          await page.goto(futureUrl(m, pl.c, pl.r));
          await settled(page, pl.c ? pl.name : await page.locator("section[data-probe] nav [aria-current=page]").innerText());
          expect(await pageScrolls(page), `${m}: the page scrolls`).toBe(false);
          expect(await probe(page), `${m}: words cut or off the screen`).toEqual([]);
          expect(await untracedNumbers(page), `${m}: numbers without a source`).toEqual([]);
          expect(await nestedInteractive(page), `${m}: nested links or buttons`).toEqual([]);
        }
        expect(errors).toEqual([]);
      });
    }
  });
}

test.describe("the map answers", () => {
  test("the keyboard: Tab to the map, arrows between places, Enter opens, Escape goes back", async ({ page }) => {
    await page.goto(futureUrl("hot-days-35c"));
    await settled(page, await page.locator("section[data-probe] nav [aria-current=page]").innerText());
    const map = page.locator("svg[role=group]").first();
    await map.focus();
    await page.keyboard.press("ArrowRight");
    const read = await page.locator("section[data-probe] nav [aria-current=page]").innerText();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/[?&]c=[A-Z]{3}/);
    await expect(page.locator("section[data-probe] nav [aria-current=page]")).toHaveText(read);
    await page.locator("svg[role=group]").last().focus();
    await page.keyboard.press("Escape");
    await expect(page).not.toHaveURL(/[?&]c=/);
  });

  test("the dial and the path picker move with arrow keys", async ({ page }) => {
    await page.goto(futureUrl("hot-days-35c"));
    await settled(page, await page.locator("section[data-probe] nav [aria-current=page]").innerText());
    await page.getByRole("slider").focus();
    await page.keyboard.press("ArrowRight");
    await expect(page).toHaveURL(/p=2060-2079/);
    await expect(page.getByRole("slider")).toHaveText("2060–2079");
    await page.getByRole("radio", { checked: true }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(page).toHaveURL(/s=ssp585/);
  });

  test("the back button walks from a region to its country, the world and the story", async ({ page }) => {
    await page.goto("/?mode=past");
    await page.getByRole("link", { name: /Show the future/ }).click();
    await expect(page).toHaveURL(/mode=future/);
    await settled(page, await page.locator("section[data-probe] nav [aria-current=page]").innerText());
    await page.locator('svg[role=group] g[data-id="IND"] path').click();
    await expect(page).toHaveURL(/c=IND/);
    await settled(page, "India");
    await page.locator('svg[role=group] g[data-id="IND.11510"] path').click({ force: true });
    await expect(page).toHaveURL(/r=IND\.11510/);
    await settled(page, "Delhi");
    await page.goBack();
    await expect(page).not.toHaveURL(/r=/);
    await page.goBack();
    await expect(page).not.toHaveURL(/c=/);
    await page.goBack();
    await expect(page).toHaveURL(/mode=past/);
  });

  test("an unknown place says so, and never shows another place's values", async ({ page }) => {
    await page.goto("/?mode=future&c=IND&r=IND.99999");
    await expect(page.getByText("No data for IND.99999 in the World Bank's Climate Change Knowledge Portal.")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("section[data-probe] a[data-indicator]")).toHaveCount(0);
  });

  test("a shape with no region in the source is never read into the panel", async ({ page }) => {
    await page.goto(futureUrl("hot-days-35c", "ESP"));
    await settled(page, "Spain");
    const shape = page.locator('svg[data-map="regions"] g[data-id^="V1:"]').first();
    await shape.dispatchEvent("pointerover", { pointerType: "mouse", bubbles: true });
    await shape.dispatchEvent("click");
    await expect(page.locator("section[data-probe] nav [aria-current=page]")).toHaveText("Spain");
    expect(page.url()).not.toContain("r=");
  });

  test("a tie at the top is said to be a tie", async ({ page }) => {
    // Several countries reach every night of the year in 2080–2099 on the very high path.
    await page.goto("/?mode=future&m=hot-nights-26c&p=2080-2099&s=ssp585");
    await expect(page.locator("section[data-probe] nav")).toContainText("tied for the most of any country", { timeout: 15_000 });
  });

  test.describe("a finger", () => {
    test.use({ viewport: { width: 375, height: 667 }, hasTouch: true, isMobile: true });
    test("the first tap reads a country, the second opens it", async ({ page }) => {
      await page.goto(futureUrl("hot-days-35c"));
      await settled(page, await page.locator("section[data-probe] nav [aria-current=page]").innerText());
      const india = page.locator('svg[role=group] g[data-id="IND"] path');
      await india.tap();
      await expect(page.locator("section[data-probe] nav [aria-current=page]")).toHaveText("India");
      expect(page.url()).not.toContain("c=IND");
      await india.tap();
      await expect(page).toHaveURL(/c=IND/);
    });
  });

  test.describe("reduced motion", () => {
    test.use({ reducedMotion: "reduce" });
    test("the story stays put, and the switch opens the map", async ({ page }) => {
      const errors = watchErrors(page);
      await page.goto("/");
      await page.waitForTimeout(14_000);
      expect(page.url()).not.toContain("mode=future");
      await page.getByRole("link", { name: /Show the future/ }).click();
      await expect(page).toHaveURL(/mode=future/);
      await settled(page, await page.locator("section[data-probe] nav [aria-current=page]").innerText());
      expect(errors).toEqual([]);
    });
  });
});
