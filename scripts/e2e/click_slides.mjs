/**
 * Clicking through slides in Design — including right after a template switch.
 *
 * The pane is expected to follow the selection: click slide 7 and you see slide
 * 7. That broke in a way no counting test would catch, because the counts were
 * all correct — every slide really was being re-rendered. The pane simply kept
 * showing the picture of the slide you had just left, because the client is
 * told to hold the previous image while a new one loads, and after a template
 * switch NOTHING is loaded yet. Clicking through the deck showed one
 * unchanging image, and the app looked frozen while it was in fact busy.
 *
 * So this asserts on the PICTURE, not on the request count: the image the pane
 * shows has to change when the selection changes, or say it is working on it.
 *
 *   node scripts/e2e/click_slides.mjs --case <caseId> --report <name>
 */
import { chromium } from "../../web/node_modules/playwright-core/index.mjs";
import fs from "fs";
import crypto from "crypto";

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 ? process.argv[i + 1] : fallback;
};

const CASE_ID = arg("case");
const REPORT = arg("report");
const BASE = arg("base", "http://localhost:5180");
const COOKIE_FILE = arg("cookie", "work/e2e-cookie.txt");

if (!CASE_ID || !REPORT) {
  console.error("usage: node scripts/e2e/click_slides.mjs --case <caseId> --report <name>");
  process.exit(2);
}

const cookie = fs.readFileSync(COOKIE_FILE, "utf8").trim();
const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
await ctx.addCookies([
  { name: "nsight_session", value: cookie, domain: new URL(BASE).hostname, path: "/" },
]);
const page = await ctx.newPage();

const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ": " + detail : ""}`);
};

/** What the big preview pane is showing right now: the image, or the words it
 *  shows instead while there is nothing to show. */
async function paneShows() {
  const img = page.locator("img[alt='Chart preview'], img[alt='']").first();
  if (await img.count()) {
    const src = await img.getAttribute("src");
    if (src && src.startsWith("data:image")) {
      return { kind: "image", id: crypto.createHash("sha1").update(src).digest("hex").slice(0, 12) };
    }
  }
  // The exact words the pane uses. Matching loosely on "Rendering…" missed
  // "Rendering preview…" and reported an empty pane where the app was in fact
  // saying, correctly, that it was working — a test bug that looked like an
  // app bug for an embarrassingly long time.
  const words = await page
    .locator("text=/Rendering preview|Updating…|Generating/")
    .first()
    .count();
  return { kind: words ? "working" : "empty", id: words ? "working" : "empty" };
}

/** Click the nth slide in the Design list. */
async function clickSlide(n) {
  const rows = page.locator("text=/Horizontal Bar|Pie Chart|Vertical Bar|Themes|Word Cloud/");
  const row = rows.nth(n);
  await row.scrollIntoViewIfNeeded();
  await row.click();
}

async function settle(ms = 2000, quietNeeded = 3, cap = 90) {
  let last = -1;
  let quiet = 0;
  for (let i = 0; i < cap; i++) {
    await page.waitForTimeout(ms);
    const busy = await page.evaluate(() => {
      const s = window.__previewQueue?.state();
      return s ? s.queued.length + s.running.length : 0;
    });
    if (busy === 0 && busy === last) {
      if (++quiet >= quietNeeded) return;
    } else {
      quiet = 0;
      last = busy;
    }
  }
}

await page.goto(`${BASE}/cases/${CASE_ID}`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.getByText(REPORT, { exact: true }).first().click();
await page.waitForTimeout(2500);
await page.getByRole("button", { name: /Design/i }).first().click({ force: true });
await settle();

// ── Clicking through slides on a settled deck ──────────────────────────────
const seen = [];
for (const n of [1, 2, 3, 4]) {
  await clickSlide(n);
  await page.waitForTimeout(1800);
  seen.push((await paneShows()).id);
}
check(
  "the pane follows the selection",
  new Set(seen).size === seen.length,
  seen.join(" ")
);

// ── The reported case: switch the template, then click around ──────────────
const combo = page.getByRole("combobox").first();
await combo.click();
await page.waitForTimeout(600);
const labels = await page.getByRole("option").allTextContents();
const wanted = labels.findIndex((t) => !/^Use parent setting|^No templates/.test(t.trim()));
await page.getByRole("option").nth(wanted >= 0 ? wanted : 0).click();
console.log(`switched to: ${labels[wanted >= 0 ? wanted : 0].trim()}`);
await page.waitForTimeout(1500);

const afterSwitch = [];
for (const n of [5, 6, 7]) {
  await clickSlide(n);
  await page.waitForTimeout(2500);
  afterSwitch.push(await paneShows());
}
console.log("pane after each click:", JSON.stringify(afterSwitch));

// Either a different picture, or an honest "working on it" — never the picture
// of the slide you just left, and never nothing at all.
const distinctOrWorking = afterSwitch.every(
  (s, i) => s.kind === "working" || afterSwitch.findIndex((o) => o.id === s.id) === i
);
check("mid-switch, the pane never shows another slide's picture", distinctOrWorking);
check(
  "mid-switch, the pane always shows something",
  afterSwitch.every((s) => s.kind !== "empty")
);

// ── And once it settles, each slide shows its own picture ──────────────────
await settle();
const settled = [];
for (const n of [5, 6, 7]) {
  await clickSlide(n);
  await page.waitForTimeout(1500);
  settled.push((await paneShows()).id);
}
check(
  "once settled, every slide shows its own picture",
  new Set(settled).size === settled.length && settled.every((s) => s !== "working"),
  settled.join(" ")
);

// ── The clicked slide is rendered FIRST, not in deck order ────────────────
// This is what makes a re-rendering deck usable: the author clicks slide 40 and
// waits for one render, not for the thirty-nine in front of it.
await page.evaluate(() => window.__previewQueue?.clear());
const combo2 = page.getByRole("combobox").first();
await combo2.click();
await page.waitForTimeout(600);
const labels2 = await page.getByRole("option").allTextContents();
const inheritIdx = labels2.findIndex((t) => /^Use parent setting|^No templates/.test(t.trim()));
await page.getByRole("option").nth(inheritIdx).click();
await page.waitForTimeout(800); // the whole deck is now queued

const target = 30;
await clickSlide(target);
const clickedAt = Date.now();
let shownAfter = null;
for (let i = 0; i < 40; i++) {
  await page.waitForTimeout(500);
  const s = await paneShows();
  if (s.kind === "image") { shownAfter = Date.now() - clickedAt; break; }
}
check(
  "a slide clicked mid-rerender appears within a few seconds",
  shownAfter !== null && shownAfter < 12000,
  shownAfter === null ? "never appeared" : `${(shownAfter / 1000).toFixed(1)}s`
);

await settle();
const state = await page.evaluate(() => window.__previewQueue?.state());
check("the queue drained", state.queued.length === 0 && state.running.length === 0);
check(
  "no slide left unfinished",
  Object.keys(state.unfinished).length === 0,
  JSON.stringify(Object.entries(state.unfinished).slice(0, 4))
);

// What the queue rendered, against what the pane asked for.
const diag = await page.evaluate(() => {
  const t = window.__previewQueue?.trace() ?? [];
  const ran = t.filter((e) => e.event === "run" && e.producer === "chart");
  const wanted = t.filter((e) => e.event === "wanted");
  return {
    context: window.__previewQueue?.state().context,
    lastRan: ran.slice(-6).map((e) => `${e.slideId} ${e.detail}`),
    lastWanted: wanted.slice(-8).map((e) => `${e.slideId} ${e.detail}`),
    misses: wanted.filter((e) => /MISS/.test(e.detail ?? "")).length,
    hits: wanted.filter((e) => /hit/.test(e.detail ?? "")).length,
  };
});
console.log("queue context:", JSON.stringify(diag.context));
console.log(`pane asks: ${diag.hits} hits, ${diag.misses} misses`);
console.log("last rendered:", diag.lastRan);
console.log("last asked  :", diag.lastWanted);

await browser.close();
const failed = results.filter((r) => !r.ok);
console.log(
  failed.length
    ? `\n${failed.length} of ${results.length} checks failed`
    : `\nall ${results.length} checks passed`
);
process.exit(failed.length ? 1 : 0);
