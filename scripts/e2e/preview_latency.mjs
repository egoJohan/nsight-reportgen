/**
 * What the author actually waits for.
 *
 * `preview_pipeline.mjs` counts requests — how many renders, headlines and
 * saves an action costs. That is the wrong instrument for "the preview got
 * slow": the counts can all be right while the author still sits looking at a
 * stale picture, because the work for the slide they are LOOKING AT is behind
 * the work for the fifty they are not.
 *
 * So this measures ORDER and LATENCY. It opens a report whose pictures have
 * never been drawn, waits for the deck to start warming, selects a slide in
 * the middle of it, types a headline, and then reports:
 *
 *   - where that slide sits in the queue the moment the edit lands
 *   - how many other slides render before the author's own edit does
 *   - wall-clock from the last keystroke to that slide's picture arriving
 *
 * It reads the queue's own trace (`window.__previewQueue`) rather than
 * inferring, so the answer names the decision that caused the wait.
 *
 *   node scripts/e2e/preview_latency.mjs --case case-xxx --report "Cold deck …"
 *
 * The report must be COLD — never rendered. The backend caches rendered
 * slides, so a report you have already opened warms in seconds and measures
 * nothing. `--slide` is the 1-based row to edit.
 */
import { chromium } from "../../web/node_modules/playwright-core/index.mjs";
import fs from "fs";

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 ? process.argv[i + 1] : fallback;
};

const CASE_ID = arg("case");
const REPORT = arg("report");
const BASE = arg("base", "http://localhost:5180");
const COOKIE_FILE = arg("cookie", "work/e2e-cookie.txt");
const SHOTS = arg("shots", "work/queue-shots");
const SLIDE = Number(arg("slide", "12"));
const WARM_MS = Number(arg("warm", "6000"));

if (!CASE_ID || !REPORT) {
  console.error("usage: node scripts/e2e/preview_latency.mjs --case <caseId> --report <name>");
  process.exit(2);
}
fs.mkdirSync(SHOTS, { recursive: true });

const cookie = fs.readFileSync(COOKIE_FILE, "utf8").trim();
const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
await ctx.addCookies([
  { name: "nsight_session", value: cookie, domain: new URL(BASE).hostname, path: "/" },
]);
const page = await ctx.newPage();

const t0 = Date.now();
let renders = 0;
let titles = 0;
const renderStarts = [];
page.on("request", (r) => {
  if (/preview-chart/.test(r.url())) { renders += 1; renderStarts.push(Date.now() - t0); }
  if (/ai\/slide-title/.test(r.url())) titles += 1;
});
const reset = () => { renders = 0; titles = 0; renderStarts.length = 0; };

const state = () => page.evaluate(() => {
  const s = window.__previewQueue.state();
  return { queued: s.queued, running: s.running, active: s.active, generation: s.generation };
});

const slideRows = () => page.locator("button:has(span.tabular-nums)");
const titleBox = () => page
  .locator('label:has-text("Slide title")').locator("..").locator("textarea").first();

/** Which slide the app promoted last — the queue's own record of the click. */
const focusedSlide = () => page.evaluate(() => {
  const t = window.__previewQueue.trace();
  for (let i = t.length - 1; i >= 0; i--) if (t[i].event === "promote") return t[i].slideId;
  return null;
});

/** The image the Design pane is showing, as a cheap fingerprint. */
const shownImage = () => page.evaluate(() => {
  const img = document.querySelector('img[alt="Chart preview"]');
  if (!img) return null;
  const s = img.getAttribute("src") ?? "";
  return s.length + ":" + s.slice(-48);
});

async function settle(quietMs = 4000, capMs = 420000) {
  const start = Date.now();
  let last = -1;
  while (Date.now() - start < capMs) {
    await page.waitForTimeout(quietMs);
    const busy = await page.evaluate(() => {
      const s = window.__previewQueue.state();
      return s.active > 0 || s.queued.length > 0;
    });
    if (renders === last && !busy) return true;
    last = renders;
  }
  return false;
}

await page.goto(`${BASE}/cases/${CASE_ID}`, { waitUntil: "networkidle" });
await page.evaluate(() => localStorage.setItem("previewQueueDebug", "1"));
await page.waitForTimeout(1200);
await page.getByText(REPORT, { exact: true }).first().click();
await page.waitForTimeout(2500);
await page.getByRole("button", { name: /Design/i }).first().click({ force: true });

// The deck starts warming. This is the ordinary state of a report someone has
// just opened, and the state the customer is in when they edit a headline.
await page.waitForTimeout(WARM_MS);
await slideRows().nth(SLIDE - 1).click({ force: true });
await page.waitForTimeout(2500);            // the selection promotes the slide
await page.screenshot({ path: `${SHOTS}/01-selected-while-warming.png` });

const before = await shownImage();
const stateBeforeEdit = await state();
const focused = await focusedSlide();
console.log(`\nslide ${SLIDE} selected (${focused}); queue: `
  + `${stateBeforeEdit.queued.length} waiting, ${stateBeforeEdit.active} running`);
console.log(`  it sits at position ${stateBeforeEdit.queued.indexOf(focused)} of `
  + `${stateBeforeEdit.queued.length} after being promoted`);

reset();
const box = titleBox();
await box.scrollIntoViewIfNeeded();
await box.click();
await box.fill("");
await box.type("EDITED — the headline the author typed", { delay: 40 });
const typed = Date.now();

// The wizard debounces for 350ms before it tells the queue anything.
await page.waitForTimeout(900);
const atEdit = await state();
const pos = atEdit.queued.indexOf(focused);
console.log(`\nAFTER THE EDIT: ${focused} sits at position ${pos} of ${atEdit.queued.length}`
  + ` (running: ${atEdit.running.join(",") || "-"})`);
console.log(`  queue order: ${atEdit.queued.join(" ")}`);

let shown = null;
for (let i = 0; i < 400; i++) {
  await page.waitForTimeout(500);
  const now = await shownImage();
  if (now && now !== before) { shown = Date.now(); break; }
}
console.log(`\nthe author's own edit appeared `
  + `${shown ? ((shown - typed) / 1000).toFixed(1) + "s" : "NEVER (timed out)"} `
  + `after their last keystroke, behind ${renders - 1} other renders`);
await page.screenshot({ path: `${SHOTS}/02-edit-appeared.png` });

console.log("\n=== letting the rest of the deck finish ===");
const rest = Date.now();
const ok = await settle();
console.log(`settled=${ok} after a further ${((Date.now() - rest) / 1000).toFixed(1)}s; `
  + `${renders} renders and ${titles} headlines since the edit`);
await page.screenshot({ path: `${SHOTS}/03-deck-settled.png` });

const trace = await page.evaluate(() => window.__previewQueue.trace());
fs.writeFileSync(`${SHOTS}/trace.json`, JSON.stringify(trace, null, 1));
const counts = {};
for (const e of trace) counts[e.event] = (counts[e.event] ?? 0) + 1;
console.log(`\ntrace: ${trace.length} events -> ${SHOTS}/trace.json`);
console.log("events:", JSON.stringify(counts));
// The order the queue actually STARTED slides in, which is the answer.
console.log("start order:", trace.filter((e) => e.event === "start")
  .map((e) => e.slideId).join(" "));
// Anything rendered more than once is wasted work.
const perSlide = {};
for (const e of trace) {
  if (e.event === "run" && e.producer === "chart") perSlide[e.slideId] = (perSlide[e.slideId] ?? 0) + 1;
}
const twice = Object.entries(perSlide).filter(([, n]) => n > 1);
console.log(`slides rendered more than once: ${twice.length ? JSON.stringify(twice) : "none"}`);

await browser.close();
