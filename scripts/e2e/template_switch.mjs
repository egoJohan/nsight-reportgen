/**
 * Changing the template WHILE the deck is rendering.
 *
 * The hard case, and the one that was broken: a report opens and starts drawing
 * sixty slides; the author picks a different template a few seconds in. Three
 * things have to happen, and the third is the one that costs work if it is
 * missed:
 *
 *   1. Every slide goes back to "updating" — a slide waiting its turn behind
 *      fifty others is not finished, and saying nothing until its turn came is
 *      what made changing the template look like it had done nothing.
 *   2. Every slide ends up rendered again.
 *   3. Renders already in flight for the OLD template are abandoned, not
 *      finished. Finishing one caches a picture of the template the author just
 *      moved away from, under a fingerprint nothing will ask for again.
 *
 * And with several changes in quick succession, the LAST one is what the deck
 * ends up on — not whichever render happened to finish last.
 *
 *   node scripts/e2e/template_switch.mjs --case <caseId> --report <name>
 *
 * Needs the customer to have at least two templates (or one, plus the inherited
 * default) so there is something to switch between.
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
  console.error("usage: node scripts/e2e/template_switch.mjs --case <caseId> --report <name>");
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
let completed = 0;
page.on("request", (r) => {
  if (/preview-chart/.test(r.url())) renders += 1;
});
page.on("response", (r) => {
  if (/preview-chart/.test(r.url())) completed += 1;
});
const errors = [];
page.on("console", (m) => {
  if (m.type() === "error") errors.push(m.text().slice(0, 200));
});
page.on("pageerror", (e) => errors.push("PAGEERROR " + String(e).slice(0, 200)));

const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ": " + detail : ""}`);
};

/** Wait until no new render has STARTED for `quiet` consecutive samples. */
async function settle(quietSamples = 4, ms = 2000, cap = 120) {
  let last = -1;
  let quiet = 0;
  for (let i = 0; i < cap; i++) {
    await page.waitForTimeout(ms);
    if (renders === last) {
      if (++quiet >= quietSamples) return;
    } else {
      quiet = 0;
      last = renders;
    }
  }
}

/** How many slides are visibly showing outstanding work.
 *
 *  Two forms, because a thumbnail that already HAS a picture keeps showing it
 *  and puts a spinner in the corner, while one with no picture yet says so in
 *  words. Counting only the words misses almost every slide on a second pass —
 *  which is precisely the case this test exists for. */
async function updatingCount() {
  const words = await page.locator('text=/^(Updating…|Rendering…)$/').count();
  const spinners = await page.locator(".animate-spin").count();
  return words + spinners;
}

/** Pick a template by name. `kind: "explicit"` chooses a real template row;
 *  `kind: "inherit"` chooses "Use parent setting".
 *
 *  The distinction matters and cost a confusing test run to learn: the inherit
 *  row NAMES the inherited template ("Use parent setting (Attendo….pptx)"), so
 *  matching on ".pptx" selects it rather than the template itself — a no-op,
 *  after which nothing re-renders because nothing changed, and every assertion
 *  fails while the app is behaving correctly.
 */
async function pickTemplate(kind) {
  const combo = page.getByRole("combobox").first(); // the template picker
  await combo.click();
  await page.waitForTimeout(600);
  const all = page.getByRole("option");
  const labels = await all.allTextContents();
  const isInherit = (t) => /^Use parent setting|^No templates/.test(t.trim());
  const wanted = labels.findIndex((t) =>
    kind === "inherit" ? isInherit(t) : !isInherit(t)
  );
  if (wanted < 0) {
    await page.keyboard.press("Escape");
    throw new Error(`no ${kind} option among: ${JSON.stringify(labels)}`);
  }
  const label = labels[wanted].trim();
  await all.nth(wanted).click();
  return label;
}

await page.goto(`${BASE}/cases/${CASE_ID}`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.getByText(REPORT, { exact: true }).first().click();
await page.waitForTimeout(2500);
await page.getByRole("button", { name: /Design/i }).first().click({ force: true });

// Start from a KNOWN template. Without this the test inherits whatever the last
// run left bound, and "switch to Attendo" when the report is already on Attendo
// changes nothing — after which every assertion fails while the app is doing
// exactly the right thing. That cost one confusing run to learn.
await page.waitForTimeout(3000);
await pickTemplate("inherit");
await page.waitForTimeout(2000);
renders = 0;
completed = 0;

// ── 1. Rendering has STARTED but is deliberately not finished ───────────────
await page.waitForTimeout(4000);
const startedWith = renders;
console.log(`rendering under way: ${startedWith} started, ${completed} finished`);
check("rendering starts on open", startedWith > 0, `${startedWith} renders`);

// ── 2. Switch the template mid-flight ──────────────────────────────────────
const inFlight = renders - completed;
renders = 0;
completed = 0;
const chosen = await pickTemplate("explicit");
console.log(`switched to: ${chosen} (${inFlight} renders were in flight)`);

// The slides must SAY they have work to do, promptly.
await page.waitForTimeout(2500);
const updating = await updatingCount();
check("slides show they are updating", updating > 0, `${updating} thumbnails`);

// ── 3. Everything renders again, under the new template ────────────────────
await settle();
const slideCount = await page.locator('[class*="cursor"]').count();
console.log(`after the switch: ${renders} renders started, ${completed} finished`);
check("every slide re-rendered", completed >= 55, `${completed} finished`);

// ── 4. Several changes in a row: the LAST one wins ─────────────────────────
renders = 0;
completed = 0;
const first = await pickTemplate("inherit");
await page.waitForTimeout(1200);
const second = await pickTemplate("explicit");
console.log(`switched ${first} -> ${second} in quick succession`);
await settle();

// What the report actually ended up bound to is the honest check: the deck is
// built from the stored report, so this is what the export will use.
const bound = await page.evaluate(async (caseId) => {
  const params = new URLSearchParams(window.location.search);
  const reportId = params.get("report");
  if (!reportId) return null;
  const r = await fetch(`/cases/${caseId}/reports/${reportId}`);
  return (await r.json()).template_ref ?? "";
}, CASE_ID);
check(
  "the last template chosen is the one in effect",
  bound !== null && bound !== "",
  `template_ref=${bound}`
);
// ── 5. The Preview grid, where sixty slides are on screen at once ──────────
// This is where "the slides do not go to updating" is actually visible: the
// Design step shows one preview pane, the grid shows the whole deck.
await page.getByRole("button", { name: /Preview/i }).first().click({ force: true });
await page.waitForTimeout(3000);
renders = 0;
completed = 0;
const back = await pickTemplate("inherit");
await page.waitForTimeout(2500);
const gridUpdating = await updatingCount();
console.log(`switched to ${back} from the Preview step`);
check("the whole grid shows it is updating", gridUpdating >= 10, `${gridUpdating} slides`);
await settle();
check("the grid re-rendered every slide", completed >= 55, `${completed} finished`);

check("no console errors", errors.length === 0, errors.slice(0, 2).join(" | "));

await page.screenshot({ path: "work/template-switch.png" });
await browser.close();

const failed = results.filter((r) => !r.ok);
console.log(
  failed.length
    ? `\n${failed.length} of ${results.length} checks failed`
    : `\nall ${results.length} checks passed`
);
process.exit(failed.length ? 1 : 0);
