/**
 * Why the FIRST open of a report costs more than every one after it, and why a
 * slide that has already been drawn draws again when you click it.
 *
 * Two questions, one run, because they share a setup that is expensive to make:
 * a deck whose pictures have never been drawn.
 *
 *   A. first open vs. re-open. The same deck twice — once with no headlines, so
 *      the AI title pass has to run, and once with them already written. The
 *      difference is what headline generation actually costs, and whether it is
 *      paid in parallel with the drawing or in series with it.
 *
 *   B. clicking a slide the background pass already drew. If it draws again,
 *      something moved between the two, and the only way to tell WHAT is to
 *      compare the fingerprint the queue drew it under against the one the
 *      component is now asking for. Both are recorded; this prints them side
 *      by side rather than inferring.
 *
 *   node scripts/e2e/first_open_cost.mjs --case case-xxx --report "name" [--clicks 6]
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
const CLICKS = Number(arg("clicks", "6"));
const LABEL = arg("label", "run");

if (!CASE_ID || !REPORT) {
  console.error("usage: node scripts/e2e/first_open_cost.mjs --case <c> --report <name>");
  process.exit(2);
}

const cookie = fs.readFileSync(arg("cookie", "work/e2e-cookie.txt"), "utf8").trim();
const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
await ctx.addCookies([
  { name: "nsight_session", value: cookie, domain: new URL(BASE).hostname, path: "/" },
]);
const page = await ctx.newPage();

let renders = 0;
let titles = 0;
let titleMs = 0;
const titleStarts = new Map();
page.on("request", (r) => {
  if (/preview-chart/.test(r.url())) renders += 1;
  if (/ai\/slide-title/.test(r.url())) { titles += 1; titleStarts.set(r, Date.now()); }
});
page.on("response", async (r) => {
  const t = titleStarts.get(r.request());
  if (t) { titleMs += Date.now() - t; titleStarts.delete(r.request()); }
});

const say = (l) => console.log(`[${LABEL}] ${l}`);
const busy = () => page.evaluate(() => {
  const s = window.__previewQueue.state();
  return s.active > 0 || s.queued.length > 0;
});
/** Wait for the queue to finish — having first waited for it to START.
 *
 *  The naive version returns instantly, because at the moment Design opens the
 *  queue is idle: the wizard has not resolved its questions or run its settle
 *  window yet. "Not busy yet" and "already done" are the same reading, and only
 *  the order they happen in tells them apart. */
async function settle(cap = 900000, quietFor = 4000, startWithin = 40000) {
  const start = Date.now();
  let started = false;
  let quietSince = null;
  while (Date.now() - start < cap) {
    const b = await busy();
    if (b) { started = true; quietSince = null; }
    else if (started) {
      if (quietSince === null) quietSince = Date.now();
      else if (Date.now() - quietSince >= quietFor) return Date.now() - start - quietFor;
    } else if (Date.now() - start > startWithin) {
      return 0;                       // it genuinely had nothing to do
    }
    await page.waitForTimeout(400);
  }
  return -1;
}

await page.goto(`${BASE}/cases/${CASE_ID}`, { waitUntil: "networkidle" });
await page.evaluate(() => localStorage.setItem("previewQueueDebug", "1"));
await page.waitForTimeout(1200);
await page.getByText(REPORT, { exact: true }).first().click();
await page.waitForTimeout(2000);
renders = 0; titles = 0; titleMs = 0;
const t0 = Date.now();
await page.getByRole("button", { name: /Design/i }).first().click({ force: true });
await settle();
const openMs = Date.now() - t0;
say(`A. cold open: ${(openMs / 1000).toFixed(1)}s  `
  + `(${renders} renders, ${titles} headline calls costing ${(titleMs / 1000).toFixed(1)}s of it)`);

// ── B. click slides the background pass already drew ────────────────────────
// `renderedFor` is what the queue recorded for each slide's picture; the
// component records what it ASKS for as a `wanted` trace line. If a click
// causes a render, those two disagreed, and this prints both.
say(`B. clicking ${CLICKS} slides the deck already drew:`);
const rows = page.locator("button:has(span.tabular-nums)");
let redrew = 0;
for (let n = 1; n <= CLICKS; n++) {
  const slide = Math.max(1, Math.round((n / CLICKS) * 28));
  const row = rows.filter({ has: page.locator(`span.tabular-nums:text-is("${slide}")`) }).last();
  if (!(await row.count())) continue;

  const before = await page.evaluate(() => ({
    renderedFor: { ...window.__previewQueue.state().renderedFor },
  }));
  const rendersBefore = renders;
  const t = Date.now();
  await row.click({ force: true });
  await page.waitForTimeout(4000);          // past the 2s settle and any requeue
  await settle(120000);
  const spent = Date.now() - t;
  const after = await page.evaluate(() => {
    const s = window.__previewQueue.state();
    const t = window.__previewQueue.trace();
    const wanted = t.filter((e) => e.event === "wanted").slice(-3)
      .map((e) => `${e.slideId} ${e.detail}`);
    return { focused: s.focused, renderedFor: { ...s.renderedFor }, wanted };
  });
  const id = after.focused;
  const drew = renders - rendersBefore;
  if (drew) redrew += 1;
  say(`   slide ${String(slide).padStart(2)} (${id}): `
    + `${drew} render(s), ${(spent / 1000).toFixed(1)}s`);
  say(`        queue had drawn it for ${before.renderedFor[id] ?? "NOTHING"}, `
    + `now ${after.renderedFor[id] ?? "NOTHING"}`);
  for (const w of after.wanted) say(`        component asked: ${w}`);
}
say(`   -> ${redrew} of ${CLICKS} slides were drawn AGAIN on being clicked`);

const trace = await page.evaluate(() => window.__previewQueue.trace());
fs.writeFileSync(`work/first-open-${LABEL}-trace.json`, JSON.stringify(trace, null, 1));
await browser.close();
