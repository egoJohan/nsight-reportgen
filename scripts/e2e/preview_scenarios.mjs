/**
 * The four things an author actually does, timed.
 *
 * Shaped on a real report — 30 slides, pies and battery stacks and word clouds,
 * not thirty copies of one bar chart. The mix matters: a word cloud costs a
 * third again what a pie does, and a deck of the cheapest chart type flatters
 * every number you take from it.
 *
 * The deck must be COLD. The backend caches a rendered slide by fingerprint, so
 * a report you have opened before warms in seconds and measures nothing. Clone
 * one with a per-slide cache-busting footer first.
 *
 *   S1  open Design cold      — first picture, and the whole deck
 *   S2  click an undrawn slide — what the author waits for, which is the
 *                                complaint "clicking a slide takes >10s"
 *   S3  what the slide DOES   — every change of the picture and of the
 *                                "Updating…" badge, so "it appears, then goes
 *                                back to Updating, then appears again" is a
 *                                sequence with timings rather than an anecdote
 *   S4  type a headline       — renders spent, and time to see it
 *
 *   node scripts/e2e/preview_scenarios.mjs --case case-xxx --report "R4 cold …"
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
const SLIDE = Number(arg("slide", "30"));
const WARM_MS = Number(arg("warm", "8000"));
const LABEL = arg("label", "run");
const SHOTS = arg("shots", `work/scenarios-${LABEL}`);

if (!CASE_ID || !REPORT) {
  console.error("usage: node scripts/e2e/preview_scenarios.mjs --case <c> --report <name>");
  process.exit(2);
}
fs.mkdirSync(SHOTS, { recursive: true });

const cookie = fs.readFileSync(arg("cookie", "work/e2e-cookie.txt"), "utf8").trim();
const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
await ctx.addCookies([
  { name: "nsight_session", value: cookie, domain: new URL(BASE).hostname, path: "/" },
]);
const page = await ctx.newPage();

let renders = 0;
let titles = 0;
page.on("request", (r) => {
  if (/preview-chart/.test(r.url())) renders += 1;
  if (/ai\/slide-title/.test(r.url())) titles += 1;
});

/** What the Design pane looks like right now: which picture, and whether it is
 *  telling the author it is still working. */
const paneState = () => page.evaluate(() => {
  const img = document.querySelector('img[alt="Chart preview"]');
  const src = img?.getAttribute("src") ?? null;
  const body = document.body.innerText;
  return {
    img: src ? src.length + ":" + src.slice(-64) : null,
    updating: /Updating…/.test(body),
    rendering: /Rendering…/.test(body),
  };
});

/** Poll the pane and return every CHANGE, with the ms it happened at. */
async function watch(ms, from = Date.now()) {
  const seen = [];
  let last = "";
  const end = Date.now() + ms;
  while (Date.now() < end) {
    const s = await paneState();
    const key = `${s.img}|${s.updating}|${s.rendering}`;
    if (key !== last) {
      seen.push({ at: Date.now() - from, ...s });
      last = key;
    }
    await page.waitForTimeout(120);
  }
  return seen;
}

const idle = () => page.evaluate(() => {
  const s = window.__previewQueue.state();
  return s.active === 0 && s.queued.length === 0;
});
async function settle(cap = 600000) {
  const start = Date.now();
  while (Date.now() - start < cap) {
    if (await idle()) return (Date.now() - start);
    await page.waitForTimeout(500);
  }
  return -1;
}

const say = (line) => console.log(`[${LABEL}] ${line}`);

// ── S1: opening a cold deck ─────────────────────────────────────────────────
await page.goto(`${BASE}/cases/${CASE_ID}`, { waitUntil: "networkidle" });
await page.evaluate(() => localStorage.setItem("previewQueueDebug", "1"));
await page.waitForTimeout(1200);
await page.getByText(REPORT, { exact: true }).first().click();
await page.waitForTimeout(2000);
renders = 0; titles = 0;
const openedAt = Date.now();
await page.getByRole("button", { name: /Design/i }).first().click({ force: true });
say(`concurrency the queue is using: `
  + `${await page.evaluate(() => window.__previewQueue.state().concurrency)}`);

// First picture on screen.
let firstPicture = null;
for (let i = 0; i < 400; i++) {
  const s = await paneState();
  if (s.img) { firstPicture = Date.now() - openedAt; break; }
  await page.waitForTimeout(250);
}
say(`S1 cold open: first picture after ${(firstPicture / 1000).toFixed(1)}s`);

// ── S2 + S3: click a slide nothing has drawn yet ────────────────────────────
await page.waitForTimeout(Math.max(0, WARM_MS - (Date.now() - openedAt)));
const beforeClick = await paneState();
const rendersAtClick = renders;
// Scoped by the row's own NUMBER, not by its index among every button that
// happens to use tabular numerals — three others on the page do, and they come
// first in the DOM, so an index selected a different slide than it named.
const rows = page.locator("button:has(span.tabular-nums)");
const rowCount = await rows.count();
const row = rows.filter({ has: page.locator(`span.tabular-nums:text-is("${SLIDE}")`) }).last();
const rowNumber = (await row.locator("span.tabular-nums").first().innerText()).trim();
const clickedAt = Date.now();
await row.click({ force: true });
await page.waitForTimeout(1200);
// Which slide the app actually selected, from the queue rather than from the
// DOM: a row index is an assumption, and this run exists to remove those.
const focusedNow = await page.evaluate(() => window.__previewQueue.state().focused);
const drawnAlready = await page.evaluate((id) => {
  const s = window.__previewQueue.state();
  return Boolean(s.renderedFor[id]);
}, focusedNow);
say(`    clicked row ${rowNumber} of ${rowCount}; the queue says the author is on `
  + `${focusedNow} (already drawn: ${drawnAlready})`);
const timeline = await watch(90000, clickedAt);
say(`S2/S3 clicked slide ${SLIDE} (was showing ${beforeClick.img ? "another slide" : "nothing"}):`);
for (const e of timeline) {
  const what = e.img ? `picture ${e.img.slice(0, 12)}…` : "NO PICTURE";
  const badge = e.rendering ? " [Rendering…]" : e.updating ? " [Updating…]" : "";
  say(`    ${(e.at / 1000).toFixed(1).padStart(6)}s  ${what}${badge}`);
}
const pictures = timeline.filter((e) => e.img).map((e) => e.img);
const distinct = [...new Set(pictures)];
say(`    -> ${distinct.length} distinct picture(s) shown, `
  + `${renders - rendersAtClick} render request(s) while watching`);
await page.screenshot({ path: `${SHOTS}/s2-clicked.png` });

// ── S4: type a headline on that slide ───────────────────────────────────────
await settle(240000);
const box = page.locator('label:has-text("Slide title")').locator("..")
  .locator("textarea").first();
await box.scrollIntoViewIfNeeded();
await box.click();
await page.keyboard.press("ControlOrMeta+a");
renders = 0; titles = 0;
const beforeEdit = (await paneState()).img;
const typeStart = Date.now();
for (const [word, gap] of [["Julkiset", 450], ["palvelut", 380], ["johtavat", 700],
                           ["luottamuksessa", 1600], ["alle", 420], ["45-vuotiailla", 600]]) {
  await box.type(word + " ", { delay: 55 });
  await page.waitForTimeout(gap);
}
const typedAt = Date.now();
let editShown = null;
for (let i = 0; i < 400; i++) {
  const s = await paneState();
  if (s.img && s.img !== beforeEdit) { editShown = Date.now(); break; }
  await page.waitForTimeout(250);
}
await settle(240000);
say(`S4 typed a headline (${((typedAt - typeStart) / 1000).toFixed(1)}s of typing, 6 pauses):`);
say(`    ${renders} render(s), ${titles} headline call(s); the author saw their words `
  + `${editShown ? ((editShown - typedAt) / 1000).toFixed(1) + "s" : "NEVER"} after the last keystroke`);
await page.screenshot({ path: `${SHOTS}/s4-edited.png` });

// ── S1 (tail): the whole deck ───────────────────────────────────────────────
const deckDone = Date.now() - openedAt;
say(`S1 whole deck settled ${(deckDone / 1000).toFixed(1)}s after opening Design `
  + `(includes the click and the edit above)`);

const trace = await page.evaluate(() => window.__previewQueue.trace());
fs.writeFileSync(`${SHOTS}/trace.json`, JSON.stringify(trace, null, 1));
const chartRuns = {};
for (const e of trace) {
  if (e.event === "run" && e.producer === "chart") chartRuns[e.slideId] = (chartRuns[e.slideId] ?? 0) + 1;
}
const twice = Object.entries(chartRuns).filter(([, n]) => n > 1);
say(`drawn more than once: ${twice.length ? JSON.stringify(twice) : "none"}`);
say(`trace -> ${SHOTS}/trace.json`);

await browser.close();
