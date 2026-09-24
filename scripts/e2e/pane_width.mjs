/** Does the right-hand pane stay inside the window? Prints what overflows it. */
import { chromium } from "../../web/node_modules/playwright-core/index.mjs";
import fs from "node:fs";

const BASE = process.env.BASE ?? "http://localhost:5180";
const PATHS = process.argv.slice(2);
const cookie = fs.readFileSync("work/e2e-cookie.txt", "utf8").trim();

const browser = await chromium.launch({ channel: "chrome", headless: true });
const WIDTHS = (process.env.WIDTHS ?? "1280").split(",").map(Number);
const ctx = await browser.newContext({ viewport: { width: WIDTHS[0], height: 900 } });
await ctx.addCookies([{ name: "nsight_session", value: cookie,
                        domain: new URL(BASE).hostname, path: "/" }]);
const page = await ctx.newPage();
for (const path of PATHS) {
 for (const width of WIDTHS) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(BASE + path, { waitUntil: "domcontentloaded" });
  // The wizard loads the study, its questions and the first preview; measure
  // only once something real is on the page.
  try {
    await page.waitForFunction(
      () => (document.querySelector("main h1")?.textContent ?? "").trim().length > 0,
      { timeout: 90000 });
  } catch { /* measured as it stands */ }
  await page.waitForTimeout(4000);
  const report = await page.evaluate(() => {
    const doc = document.documentElement;
    const main = document.querySelector("main") ?? doc;
    const out = {
      window: window.innerWidth,
      documentScrollWidth: doc.scrollWidth,
      mainClientWidth: main.clientWidth,
      mainScrollWidth: main.scrollWidth,
      offenders: [],
      heading: (document.querySelector("main h1")?.textContent ?? "").slice(0, 60),
    };
    const limit = window.innerWidth + 1;
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.right > limit) {
        const cs = getComputedStyle(el);
        if (cs.position === "fixed") continue;   // fixed boxes do not scroll the page
        out.offenders.push({
          tag: el.tagName.toLowerCase(),
          cls: (el.className?.baseVal ?? el.className ?? "").toString().slice(0, 70),
          right: Math.round(r.right), width: Math.round(r.width),
          text: (el.textContent ?? "").trim().slice(0, 40),
        });
      }
    }
    out.offenders = out.offenders.slice(0, 6);
    return out;
  });
  console.log(`${path} @${width}`, JSON.stringify(report));
  await page.screenshot({ path: `work/ops/pane-${width}.png`, fullPage: false });
 }
}
await browser.close();
