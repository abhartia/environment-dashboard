import type { Page } from "@playwright/test";

/**
 * The layout probe: every element with its own text inside a [data-probe] region must show all of it. Its content may
 * not overflow its own box (a cut line, an ellipsis that hides words), and its box may not stick out of any ancestor
 * that clips (overflow other than visible) or out of the viewport. Returns one line per problem, empty when all is read.
 */
export async function probe(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const problems: string[] = [];
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const describe = (el: Element) => `${el.tagName.toLowerCase()} "${(el.textContent ?? "").trim().slice(0, 50)}"`;
    // A region that scrolls up and down must not also scroll sideways, unless it is marked as a strip that does
    // (data-scroll="x"): its computed overflow-x is "auto" either way, so the intent is declared in the markup.
    for (const region of document.querySelectorAll("[data-probe]")) {
      for (const el of [region, ...region.querySelectorAll<HTMLElement>("*")]) {
        const s = getComputedStyle(el);
        const scrolls = ["auto", "scroll"].includes(s.overflowX) || ["auto", "scroll"].includes(s.overflowY);
        if (scrolls && el.scrollWidth > el.clientWidth + 1 && el.getAttribute("data-scroll") !== "x") {
          problems.push(`${describe(el)} scrolls sideways`);
        }
      }
    }
    for (const region of document.querySelectorAll("[data-probe]")) {
      for (const el of region.querySelectorAll<HTMLElement>("*")) {
        const ownText = [...el.childNodes].some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() !== "");
        if (!ownText) continue;
        const style = getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden" || el.closest("[inert]")) continue;
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) continue;
        if (el.scrollWidth > el.clientWidth + 1 && style.overflowX !== "visible") problems.push(`${describe(el)} is cut sideways`);
        if (el.scrollHeight > el.clientHeight + 1 && style.overflowY !== "visible") problems.push(`${describe(el)} is cut short`);
        // Inside a region that scrolls on purpose, the region itself must be on the screen; what it holds is reached
        // by scrolling it (the outermost such region: a strip that scrolls sideways inside a panel that scrolls down
        // is reached by scrolling the panel).
        const scroller = (() => {
          let outer: HTMLElement | null = null;
          for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
            const s = getComputedStyle(a);
            if (["auto", "scroll"].includes(s.overflowX) || ["auto", "scroll"].includes(s.overflowY)) outer = a;
          }
          return outer;
        })();
        const box = scroller ? scroller.getBoundingClientRect() : r;
        if (box.right > vw + 1 || box.bottom > vh + 1 || box.left < -1 || box.top < -1) {
          problems.push(`${scroller ? `the scrolling ${scroller.tagName.toLowerCase()} holding ${describe(el)}` : describe(el)} runs off the screen`);
        }
        for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
          const s = getComputedStyle(a);
          if (s.overflowX === "visible" && s.overflowY === "visible") continue;
          // A region that scrolls on purpose (a card row, a panel on a short screen) does not hide what it holds.
          if (s.overflowX === "auto" || s.overflowY === "auto" || s.overflowX === "scroll" || s.overflowY === "scroll") break;
          const ar = a.getBoundingClientRect();
          if (r.right > ar.right + 1 || r.bottom > ar.bottom + 1 || r.left < ar.left - 1 || r.top < ar.top - 1) {
            problems.push(`${describe(el)} is clipped by ${a.tagName.toLowerCase()}`);
            break;
          }
        }
      }
    }
    return problems;
  });
}

/** The page never scrolls: its document is exactly the viewport's height. */
export async function pageScrolls(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollHeight > window.innerHeight + 1);
}
