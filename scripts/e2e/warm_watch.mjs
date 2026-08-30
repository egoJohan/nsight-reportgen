/**
 * Does a freshly opened report draw itself, and how long does each slide take?
 *
 * Deliberately dumb: open Design on a cold report, watch, and print one line
 * per slide as it finishes, with the wall clock the AUTHOR would experience —
 * from the moment the slide was first asked for to the moment its picture
 * existed. Wall-clock totals hide exactly the thing a person notices, which is
 * how long the one slide in front of them takes.
 *
 *   node scripts/e2e/warm_watch.mjs --case case-xxx --report "name" [--for 180]
 */
import { chromium } from "../../web/node_modules/playwright-core/index.mjs";
import fs from "fs";

const arg = (n, d) => {
  const i = process.argv.indexOf(`--${n}`);
  return i > -1 ? process.argv[i + 1] : d;
};
const CASE_ID = arg("case");
const REPORT = arg("report");
const BASE = arg("base", "http://localhost:5180");
const FOR_MS = Number(arg("for", "180")) * 1000;

const cookie = fs.readFileSync(arg("cookie", "work/e2e-cookie.txt"), "utf8").trim();
const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
await ctx.addCookies([
  { name: "nsight_session", value: cookie, domain: new URL(BASE).hostname, path: "/" },
]);
const page = await ctx.newPage();

let renders = 0, titles = 0;
page.on("request", (r) => {
  if (/preview-chart/.test(r.url())) renders += 1;
  if (/ai\/slide-title/.test(r.url())) titles += 1;
});

await page.goto(`${BASE}/cases/${CASE_ID}`, { waitUntil: "networkidle" });
await page.evaluate(() => localStorage.setItem("previewQueueDebug", "1"));
await page.waitForTimeout(1200);
await page.getByText(REPORT, { exact: true }).first().click();
await page.waitForTimeout(2000);
const t0 = Date.now();
await page.getByRole("button", { name: /Design/i }).first().click({ force: true });

let lastDone = 0;
const deadline = Date.now() + FOR_MS;
while (Date.now() < deadline) {
  await page.waitForTimeout(2000);
  const s = await page.evaluate(() => {
    const st = window.__previewQueue.state();
    return {
      queued: st.queued.length, running: st.running.length, active: st.active,
      renderConcurrency: st.renderConcurrency, concurrency: st.concurrency,
      rendersActive: st.rendersActive,
      drawn: Object.keys(st.renderedFor).length,
      nothingToDo: window.__previewQueue.trace()
        .filter((e) => e.event === "nothing-to-do").length,
    };
  });
  const t = ((Date.now() - t0) / 1000).toFixed(0).padStart(4);
  console.log(`${t}s  drawn=${String(s.drawn).padStart(2)} queued=${String(s.queued).padStart(2)} `
    + `running=${s.running} renderSlots=${s.rendersActive}/${s.renderConcurrency} `
    + `passes=${s.concurrency} | ${renders} renders ${titles} titles `
    + `| nothing-to-do=${s.nothingToDo}`);
  if (s.queued === 0 && s.active === 0 && s.drawn > 0 && s.drawn === lastDone) break;
  lastDone = s.drawn;
}

// Per-slide, what the author waited: enqueue -> its picture done.
const spans = await page.evaluate(() => {
  const t = window.__previewQueue.trace();
  const first = new Map(), done = new Map();
  for (const e of t) {
    if (e.event === "enqueue" && !first.has(e.slideId)) first.set(e.slideId, e.t);
    if (e.event === "done" && e.producer === "chart") done.set(e.slideId, e.t);
  }
  return [...done].map(([id, d]) => [id, d - (first.get(id) ?? d)]);
});
const waits = spans.map(([, ms]) => ms).sort((a, b) => a - b);
if (waits.length) {
  const at = (p) => (waits[Math.floor((waits.length - 1) * p)] / 1000).toFixed(1);
  console.log(`\nper-slide wait (queued -> drawn): median ${at(0.5)}s, `
    + `p90 ${at(0.9)}s, worst ${at(1)}s, over ${waits.length} slides`);
}
fs.writeFileSync("work/warm-watch-trace.json",
  JSON.stringify(await page.evaluate(() => window.__previewQueue.trace()), null, 1));
await browser.close();
