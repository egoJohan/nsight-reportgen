/**
 * What ONE slide actually costs the renderer, by chart type.
 *
 * Before asking whether the queue orders work well, ask how big a unit of work
 * is. This posts each of a report's slides to /preview-chart on its own, one at
 * a time, with a cache-busting footer so nothing is served from the render
 * cache, and reports the wall clock per chart type.
 *
 * Serial on purpose: it measures the COST of a render, not the throughput of
 * the pool. The pool sizes itself to the core count (one, locally and on
 * staging), so four concurrent renders do not go four times faster — they take
 * four times as long each, which is what makes a queue's ordering matter.
 *
 *   node scripts/e2e/render_cost.mjs --case case-xxx --report rep-xxx --material mat-xxx
 */
import fs from "fs";

const arg = (n, d) => {
  const i = process.argv.indexOf(`--${n}`);
  return i > -1 ? process.argv[i + 1] : d;
};
const API = arg("api", "http://127.0.0.1:8200");
const CASE_ID = arg("case");
const REPORT_ID = arg("report");
const MATERIAL = arg("material");
const COOKIE = fs.readFileSync(arg("cookie", "work/e2e-cookie.txt"), "utf8").trim();
const CONCURRENCY = Number(arg("concurrency", "1"));
const LIMIT = Number(arg("limit", "0"));
const QUIET = process.argv.includes("--quiet");
// The app draws the title in the DOM over a composited image; pass
// --render-title to measure the baked-in LibreOffice path instead.
const RENDER_TITLE = process.argv.includes("--render-title");

if (!CASE_ID || !REPORT_ID || !MATERIAL) {
  console.error("usage: node scripts/e2e/render_cost.mjs --case <c> --report <r> --material <m>");
  process.exit(2);
}

const headers = { Cookie: `nsight_session=${COOKIE}`, "Content-Type": "application/json" };

const doc = await (await fetch(
  `${API}/cases/${CASE_ID}/reports/${REPORT_ID}`, { headers })).json();
let charts = doc.charts ?? doc.report?.charts ?? [];
if (LIMIT) charts = charts.slice(0, LIMIT);
console.log(`${charts.length} slides in ${doc.name ?? REPORT_ID}, ${CONCURRENCY} at a time, render_title=${RENDER_TITLE}`);

const stamp = Date.now();
async function render(chart, i) {
  // A footer nothing has ever rendered, so the server cache cannot answer.
  // render_title:false — the path the APP uses. The endpoint defaults it to
  // true, which rasterises the whole slide through LibreOffice and costs
  // roughly three times as much; measuring that and calling it "what a slide
  // costs" describes a road the product never takes.
  const body = {
    ...chart,
    footer_note: `cost ${stamp} ${i}`,
    report_id: REPORT_ID,
    render_title: RENDER_TITLE,
  };
  const t = Date.now();
  const r = await fetch(`${API}/materials/${MATERIAL}/preview-chart`,
                        { method: "POST", headers, body: JSON.stringify(body) });
  const ms = Date.now() - t;
  if (!r.ok) return { i, chart, ms, error: `${r.status} ${(await r.text()).slice(0, 120)}` };
  await r.arrayBuffer();
  return { i, chart, ms };
}

const results = [];
const wallStart = Date.now();
for (let i = 0; i < charts.length; i += CONCURRENCY) {
  const batch = charts.slice(i, i + CONCURRENCY);
  results.push(...await Promise.all(batch.map((c, k) => render(c, i + k))));
  const last = results[results.length - 1];
  if (!QUIET) {
    process.stdout.write(`  ${results.length}/${charts.length} `
      + `${last.chart.chart_type} ${last.error ? "ERROR " + last.error : last.ms + "ms"}\n`);
  }
}
const wall = Date.now() - wallStart;

const byType = new Map();
for (const r of results) {
  if (r.error) continue;
  const a = byType.get(r.chart.chart_type) ?? [];
  a.push(r.ms);
  byType.set(r.chart.chart_type, a);
}
const pct = (a, p) => a.slice().sort((x, y) => x - y)[Math.floor((a.length - 1) * p)];
console.log(`\nrender cost, ${CONCURRENCY} at a time:`);
console.log("  type                        n    min   median      max");
for (const [type, a] of [...byType].sort((x, y) => pct(y[1], 0.5) - pct(x[1], 0.5))) {
  console.log(`  ${type.padEnd(24)} ${String(a.length).padStart(3)} `
    + `${String(pct(a, 0)).padStart(6)}ms ${String(pct(a, 0.5)).padStart(6)}ms `
    + `${String(pct(a, 1)).padStart(6)}ms`);
}
const all = results.filter((r) => !r.error).map((r) => r.ms);
console.log(`  ${"ALL".padEnd(24)} ${String(all.length).padStart(3)} `
  + `${String(pct(all, 0)).padStart(6)}ms ${String(pct(all, 0.5)).padStart(6)}ms `
  + `${String(pct(all, 1)).padStart(6)}ms`);
console.log(`  deck wall-clock: ${(wall / 1000).toFixed(1)}s  `
  + `(throughput ${(all.length / (wall / 1000)).toFixed(2)} slides/s)`);
const errs = results.filter((r) => r.error);
if (errs.length) {
  console.log(`\n${errs.length} failed:`);
  for (const e of errs) console.log(`  slide ${e.i + 1} ${e.chart.chart_type}: ${e.error}`);
}
