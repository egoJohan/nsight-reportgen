/**
 * What one edit costs, typed the way a person types.
 *
 * A render is seconds of a CPU-bound pipeline (LibreOffice -> PDF -> raster),
 * and staging has one core. So the question a debounce has to answer is not
 * "does it coalesce keystrokes" — 350ms does that — but "does it coalesce the
 * PAUSES a person leaves between words". Typing a headline is not a uniform
 * stream: it is bursts with 300-900ms gaps and a second or two of thinking in
 * the middle, and every gap longer than the debounce starts a render of a
 * half-written sentence.
 *
 * This types a headline with those gaps and counts what the server was asked
 * to draw. It also does the same for a DISCRETE change (a dropdown), because
 * that is the case a long debounce makes worse: one event, nothing following
 * it, and the author waiting out the whole window before anything moves.
 *
 *   node scripts/e2e/edit_debounce.mjs --case case-xxx --report "name"
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
const SLIDE = Number(arg("slide", "12"));
const LABEL = arg("label", "run");

if (!CASE_ID || !REPORT) {
  console.error("usage: node scripts/e2e/edit_debounce.mjs --case <caseId> --report <name>");
  process.exit(2);
}

const cookie = fs.readFileSync(COOKIE_FILE, "utf8").trim();
const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
await ctx.addCookies([
  { name: "nsight_session", value: cookie, domain: new URL(BASE).hostname, path: "/" },
]);
const page = await ctx.newPage();

let renders = 0;
page.on("request", (r) => { if (/preview-chart/.test(r.url())) renders += 1; });

const busy = () => page.evaluate(() => {
  const s = window.__previewQueue.state();
  return s.active > 0 || s.queued.length > 0;
});
async function quiet(ms = 3000, cap = 180000) {
  const start = Date.now();
  let last = -1;
  while (Date.now() - start < cap) {
    await page.waitForTimeout(ms);
    if (renders === last && !(await busy())) return;
    last = renders;
  }
}

await page.goto(`${BASE}/cases/${CASE_ID}`, { waitUntil: "networkidle" });
await page.evaluate(() => localStorage.setItem("previewQueueDebug", "1"));
await page.waitForTimeout(1200);
await page.getByText(REPORT, { exact: true }).first().click();
await page.waitForTimeout(2500);
await page.getByRole("button", { name: /Design/i }).first().click({ force: true });
await quiet();
await page.locator("button:has(span.tabular-nums)").nth(SLIDE - 1).click({ force: true });
await quiet();

const titleBox = () => page
  .locator('label:has-text("Slide title")').locator("..").locator("textarea").first();
/** The picture on screen right now, or null while there is none. Compared by
 *  identity, so "moved" means a genuinely different image and not a re-layout. */
const shown = () => page.evaluate(() => {
  const img = document.querySelector('img[alt="Chart preview"]');
  const s = img?.getAttribute("src");
  return s ? s.length + ":" + s.slice(-64) : null;
});

// ── One headline, typed like a person ────────────────────────────────────────
// Words in bursts, a gap after each, and one pause to think in the middle. The
// gaps are the whole point: each one longer than the debounce is a render of a
// half-finished sentence.
const WORDS = [
  ["Private", 450], ["providers", 380], ["lead", 700], ["on", 300],
  ["trust", 1600],                       // ← thinking
  ["among", 420], ["under-45s", 600],
];

const box = titleBox();
await box.scrollIntoViewIfNeeded();
await box.click();
// Select-all, then type straight over it. NOT fill("") followed by a pause:
// that empties the field and lets the window expire on an EMPTY title, which
// is a real state with a real meaning — "no headline yet, write one" — so the
// AI title producer starts, and the run measures that instead of the edit.
await page.keyboard.press("ControlOrMeta+a");
renders = 0;
const before = await shown();
const t0 = Date.now();
for (const [word, gap] of WORDS) {
  await box.type(word + " ", { delay: 55 });
  await page.waitForTimeout(gap);
}
const typed = Date.now();
let appeared = null;
for (let i = 0; i < 240; i++) {
  await page.waitForTimeout(250);
  const now = await shown();
  if (now && now !== before) { appeared = Date.now(); break; }
}
const duringTyping = renders;
await quiet();
await page.screenshot({ path: `work/debounce-${LABEL}.png` });
{
  const trace = await page.evaluate(() => window.__previewQueue.trace());
  fs.writeFileSync(`work/debounce-${LABEL}-trace.json`, JSON.stringify(trace, null, 1));
  const tail = trace.slice(-40).filter((e) => ["enqueue","start","run","done","settled","requeue-after-run","requeue","skip","wanted","focus"].includes(e.event));
  for (const e of tail) {
    console.log(`[${LABEL}]   ${String(e.t).padStart(7)} ${e.q} ${e.event} ${e.slideId ?? ""} ${e.producer ?? ""} ${e.detail ?? ""}`);
  }
}
console.log(`[${LABEL}] TYPED HEADLINE (${((typed - t0) / 1000).toFixed(1)}s of typing, `
  + `6 pauses of 300-1600ms):`);
console.log(`[${LABEL}]   renders: ${renders} total, ${duringTyping} by the time the picture moved`);
console.log(`[${LABEL}]   first new picture: `
  + `${appeared ? ((appeared - typed) / 1000).toFixed(1) + "s" : "never"} after the last keystroke`);

// ── One discrete change: the chart type dropdown ─────────────────────────────
// Nothing follows it, so the author simply waits out the debounce window.
renders = 0;
const beforeType = await shown();
const combo = page.getByRole("combobox").nth(1);
await combo.scrollIntoViewIfNeeded();
await combo.click();
await page.waitForTimeout(600);
const current = await combo.innerText();
await page.getByRole("option").filter({ hasNotText: current }).first().click();
const clicked = Date.now();
let typeAppeared = null;
for (let i = 0; i < 240; i++) {
  await page.waitForTimeout(250);
  const now = await shown();
  if (now && now !== beforeType) { typeAppeared = Date.now(); break; }
}
await quiet();
console.log(`[${LABEL}] DROPDOWN (one discrete change):`);
console.log(`[${LABEL}]   renders: ${renders}; picture moved `
  + `${typeAppeared ? ((typeAppeared - clicked) / 1000).toFixed(1) + "s" : "never"} after the click`);

await browser.close();
