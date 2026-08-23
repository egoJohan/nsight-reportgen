/**
 * The preview pipeline's acceptance run.
 *
 * The frontend's unit tests cover the pure parts — the fingerprints, the queue's
 * ordering and failure rules. What they cannot tell you is how many times the
 * app actually asks the server to write a headline, draw a picture, or save the
 * document, and those counts ARE the requirement: opening a report used to cost
 * seventeen saves and render every slide twice.
 *
 * So this drives the real app in a real browser and counts real requests.
 *
 *   ./scripts/dev-stack.sh up
 *   TOKEN=$(python3 -c "import json;d=json.load(open('work/datahive_creds.json'));print(d.get('bearer_admin') or d['bearer'])")
 *   NSIGHT_DATAHIVE_URL=http://127.0.0.1:7910 NSIGHT_DATAHIVE_TOKEN="$TOKEN" PYTHONPATH=src \
 *     .venv/bin/python scripts/e2e/mint_session.py you@example.com > work/e2e-cookie.txt
 *   node scripts/e2e/preview_pipeline.mjs --case case-xxxx --report "My 60-slide report"
 *
 * Expected, against a report of any size (n = its slide count):
 *
 *   cold open of an untitled report   n titles, n renders, 1 save
 *   reopen of a titled report         0 titles,          , 0 saves
 *   change one chart's type           1 render,  0 titles
 *   type in a slide title             1 render,  0 titles, 1 save
 *   Design -> Preview                 0 extra renders
 *   every AI title failing            n renders anyway, each slide keeps its
 *                                     question text, warning button explains it
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

if (!CASE_ID || !REPORT) {
  console.error("usage: node scripts/e2e/preview_pipeline.mjs --case <caseId> --report <name>");
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
let titles = 0;
let saves = 0;
page.on("request", (r) => {
  if (/preview-chart/.test(r.url())) renders += 1;
  if (/ai\/slide-title/.test(r.url())) titles += 1;
  if (r.method() === "PUT" && /\/reports\//.test(r.url())) saves += 1;
});
const reset = () => {
  renders = 0;
  titles = 0;
  saves = 0;
};

/** Wait until no new render has started for one full interval. */
async function settle() {
  let last = -1;
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(2500);
    if (renders === last) return;
    last = renders;
  }
}

const results = [];
const check = (name, got, want) => {
  const ok = Object.entries(want).every(([k, v]) => got[k] === v);
  results.push({ name, got, want, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}: ${JSON.stringify(got)}`);
};

await page.goto(`${BASE}/cases/${CASE_ID}`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.getByText(REPORT, { exact: true }).first().click();
await page.waitForTimeout(2500);
await page.getByRole("button", { name: /Design/i }).first().click({ force: true });
await settle();
console.log(`opened Design: ${renders} slides, ${titles} headlines written`);
// The requirement is "the generation phase is ONE save", not "a save happens":
// a report whose headlines are already written has nothing to write down, and
// saving anyway would be the very churn this replaced. Which case this run is
// depends on the report you point it at, so the check covers both.
check(
  titles > 0 ? "generation phase saves exactly once" : "nothing to do, nothing saved",
  { saves },
  { saves: titles > 0 ? 1 : 0 }
);

// Change one chart's type: a presentation edit. It must re-render, and must not
// spend an LLM call rewriting a headline that still says the same true thing.
reset();
const typeCombo = page.getByRole("combobox").nth(1); // [0] is the template picker
await typeCombo.scrollIntoViewIfNeeded();
await typeCombo.click();
await page.waitForTimeout(700);
const option = page.getByRole("option").filter({ hasNotText: await typeCombo.innerText() });
await option.first().click();
await page.waitForTimeout(8000);
check("chart type change", { renders, titles }, { renders: 1, titles: 0 });

// Typing a headline by hand: renders, saves, and never regenerates over the
// author's own words.
reset();
const titleBox = page
  .locator('label:has-text("Slide title")')
  .locator("..")
  .locator("textarea")
  .first();
await titleBox.scrollIntoViewIfNeeded();
await titleBox.click();
await titleBox.type(" EDITED", { delay: 30 });
await page.waitForTimeout(9000);
check("hand-typed title", { renders, titles, saves }, { renders: 1, titles: 0, saves: 1 });

// Design -> Preview shows the SAME images. This is the requirement that the two
// views must not disagree, expressed as a number.
reset();
await page.getByRole("button", { name: /Preview/i }).first().click({ force: true });
await page.waitForTimeout(12000);
check("Design -> Preview reuses the images", { renders }, { renders: 0 });

await browser.close();

const failed = results.filter((r) => !r.ok);
if (failed.length) {
  console.error(`\n${failed.length} of ${results.length} checks failed`);
  process.exit(1);
}
console.log(`\nall ${results.length} checks passed`);
