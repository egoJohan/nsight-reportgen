#!/usr/bin/env node
/**
 * verify-preview-cache.mjs — confirms chart previews are formed ONCE and reused.
 * Counts POSTs to /preview-chart: many on first Review visit, ZERO when
 * navigating away (Slides) and back to Review (served from cache).
 */
import { chromium } from "playwright";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const API = "http://127.0.0.1:8200";
const APP = process.argv.find((a) => a.startsWith("--url="))?.slice(6) ?? "http://localhost:5173";
const SPSS = resolve(ROOT, "../input/spss AttendoSuomi-Brandiseuranta_112025.sav");
const J = (b) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
async function api(p, o) { const r = await fetch(`${API}${p}`, o); if (!r.ok) throw new Error(`${p} ${r.status}`); return r.json(); }
function chart(qid, type, slot) {
  return { question_ref: qid, chart_type: type, statistic: "pct", classifying_var: null,
    number_format: { mode: "auto", pct_decimals: 0, mean_decimals: 1, count_round_up: false, show_pct_sign: true },
    sort: { basis: "pct", topbox_codes: [], descending: true }, template_slot: slot,
    elements: { title: true, legend: true, n: true, axis_names: true, filter_var: true, data_labels: true },
    scatter_xy: null, show_not_answered: false, show_empty_categories: false,
    not_answered_codes: null, category_label_overrides: [], slide_title: null, slide_description: null };
}

async function main() {
  const { case_id } = await api("/cases", J({ name: "Verify preview cache" }));
  const form = new FormData();
  form.append("file", new Blob([readFileSync(SPSS)]), "attendo.sav");
  const { material_id } = await (await fetch(`${API}/cases/${case_id}/materials`, { method: "POST", body: form })).json();
  const { questions } = await api(`/materials/${material_id}/questions`);
  const singles = questions.filter((q) => q.kind === "single" && q.chartable !== false).slice(0, 3);
  const charts = singles.map((q, i) => chart(q.qid, "vertical_bar", `s${i}`));
  const { report_id } = await api(`/cases/${case_id}/reports`,
    J({ name: "cache report", render_mode: "image", template_ref: "", charts }));
  console.log(`${charts.length} charts seeded`);

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  await page.addInitScript(([cid, mid, rid]) => {
    localStorage.setItem(`nsight.ws.${cid}`,
      JSON.stringify({ materialId: mid, reports: [{ id: rid, name: "cache report", materialId: mid }] }));
  }, [case_id, material_id, report_id]);

  let previewPosts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().includes("/preview-chart")) previewPosts++;
  });

  await page.goto(`${APP}/cases/${case_id}`, { waitUntil: "networkidle", timeout: 30000 });
  await page.getByRole("tab", { name: "Reports" }).click();
  await page.waitForTimeout(300);
  await page.getByText("cache report").first().click();

  // First Review visit — previews form here.
  await page.getByRole("button", { name: "Review" }).first().click();
  await page.waitForSelector('img[alt="Chart preview"]', { timeout: 40000 });
  await page.waitForTimeout(3000);
  const afterFirst = previewPosts;
  console.log(`preview-chart POSTs after FIRST Review visit: ${afterFirst}`);

  // Navigate away (Slides) then back to Review — should be served from cache.
  await page.getByRole("button", { name: "Slides" }).first().click();
  await page.waitForTimeout(1500);
  const beforeRevisit = previewPosts;
  await page.getByRole("button", { name: "Review" }).first().click();
  await page.waitForSelector('img[alt="Chart preview"]', { timeout: 40000 });
  await page.waitForTimeout(2500);
  const onRevisit = previewPosts - beforeRevisit;
  console.log(`preview-chart POSTs added on Review REVISIT: ${onRevisit}  (expect 0)`);

  await browser.close();
  const ok = afterFirst > 0 && onRevisit === 0;
  console.log(ok ? "RESULT: PASS — previews formed once, reused" : "RESULT: FAIL");
  process.exit(ok ? 0 : 1);
}
main().catch((e) => { console.error(e); process.exit(1); });
