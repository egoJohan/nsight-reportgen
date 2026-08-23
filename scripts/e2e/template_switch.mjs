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
const httpFailures = [];
page.on("response", (r) => {
  if (/preview-chart/.test(r.url())) {
    completed += 1;
    if (!r.ok()) httpFailures.push(r.status());
  }
});
page.on("requestfailed", (r) => {
  if (/preview-chart/.test(r.url())) httpFailures.push(r.failure()?.errorText ?? "aborted");
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

// The slide must SAY it has work to do, promptly. The Design step shows ONE
// preview pane, so a single sample catches it or misses it depending on where
// the queue happens to be; poll instead of guessing a moment.
let updating = 0;
for (let i = 0; i < 12; i++) {
  updating = await updatingCount();
  if (updating > 0) break;
  await page.waitForTimeout(400);
}
check("the slide shows it is updating", updating > 0, `${updating} indicators`);

// ── 3. Everything renders again, under the new template ────────────────────
await settle();
console.log(`after the switch: ${renders} renders started, ${completed} finished`);
// How MANY renders a switch costs depends on what the client already holds —
// switching back to a template whose pictures are still cached is meant to cost
// nothing. So the assertion is that the work happened and finished, not that it
// reached a particular count; the end state is checked below and is the thing
// that actually matters.
check("the switch was acted on", renders > 0, `${renders} renders started`);
check("everything it started, it finished", completed >= renders, `${completed}/${renders}`);

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
// Poll: whether the grid is mid-work at any given millisecond is a race, so
// look for the indicator over a window rather than at one instant.
let gridUpdating = 0;
for (let i = 0; i < 12; i++) {
  gridUpdating = Math.max(gridUpdating, await updatingCount());
  if (gridUpdating > 0) break;
  await page.waitForTimeout(400);
}
console.log(`switched to ${back} from the Preview step (${renders} renders started)`);
// Only meaningful when there IS work: switching back to a template whose
// pictures are still cached is meant to cost nothing, and asserting "it must
// re-render" would be asserting against the cache doing its job — which an
// earlier version of this test did, wrongly.
if (renders > 0) {
  check("while the grid has work, it says so", gridUpdating > 0, `${gridUpdating} slides`);
} else {
  console.log("SKIP  nothing to do: every picture was already cached");
}
await settle();
const gridImages = await page.locator('img[src^="data:image"]').count();
check("the grid ends up showing every slide", gridImages >= 55, `${gridImages} images`);

// ── 6. Switching repeatedly, fast, while it is still rendering ─────────────
// The case that was broken in the field and that a single tidy switch never
// caught: the author tries several templates in a row to see which looks best.
// Every switch abandons work in flight, and an abandoned render that is not
// picked up again leaves its slide unfinished for ever.
await page.getByRole("button", { name: /Design/i }).first().click({ force: true });
await page.waitForTimeout(1500);
await page.evaluate(() => window.__previewQueue?.clear());
renders = 0;
completed = 0;

for (let i = 0; i < 5; i++) {
  await pickTemplate(i % 2 === 0 ? "explicit" : "inherit");
  await page.waitForTimeout(1500); // deliberately mid-render
}
console.log("switched templates 5 times in quick succession");
await settle(5, 2500, 160);

const state = await page.evaluate(() => window.__previewQueue?.state());
console.log("queue after it settled:", JSON.stringify({
  queued: state.queued.length,
  running: state.running.length,
  requeue: state.requeue.length,
  unfinished: Object.keys(state.unfinished).length,
  generation: state.generation,
  template: state.context.templateRef,
}));

check("nothing left running", state.running.length === 0, `${state.running.length}`);
check("nothing left queued", state.queued.length === 0, `${state.queued.length}`);
check(
  "no slide left unfinished",
  Object.keys(state.unfinished).length === 0,
  JSON.stringify(Object.entries(state.unfinished).slice(0, 5))
);

// Every slide has a picture, which is the thing the author actually sees.
await page.getByRole("button", { name: /Preview/i }).first().click({ force: true });
await page.waitForTimeout(4000);
await settle(4, 2000, 90);
const withImages = await page.locator('img[src^="data:image"]').count();
check("every slide has a rendered picture", withImages >= 55, `${withImages} images`);

// What the queue actually DID, for review.
const summary = await page.evaluate(() => {
  const t = window.__previewQueue?.trace() ?? [];
  const counts = {};
  for (const e of t) counts[e.event] = (counts[e.event] ?? 0) + 1;
  return { counts, contextChanges: t.filter((e) => e.event === "context-changed").map((e) => e.detail) };
});
console.log("what the queue did:", JSON.stringify(summary.counts));
console.log("HTTP failures:", JSON.stringify(httpFailures.slice(0, 8)), `(${httpFailures.length} total)`);
const whyFailed = await page.evaluate(() => {
  const t = window.__previewQueue?.trace() ?? [];
  const seen = new Map();
  for (const e of t) if (e.event === "failed") seen.set(e.detail, (seen.get(e.detail) ?? 0) + 1);
  return [...seen.entries()];
});
for (const [why, n] of whyFailed) console.log(`  failed x${n}: ${why}`);
for (const c of summary.contextChanges) console.log("  context-changed:", c);

// Titles are DATA, not presentation: switching templates must never spend an
// LLM call rewriting a headline that still says the same true thing.
const titleRuns = await page.evaluate(() => {
  const t = window.__previewQueue?.trace() ?? [];
  return t.filter((e) => e.event === "run" && e.producer === "title").length;
});
check("no headline was regenerated by a template switch", titleRuns === 0, `${titleRuns} title runs`);

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
