#!/usr/bin/env node
/**
 * verify-config-schema.mjs — confirms the schema-driven config form:
 *   - a PIE chart (single-series) hides the "Classifying variable" field
 *   - a HORIZONTAL BAR chart shows it
 * Drives the running backend (:8200) + dev UI (--url, default :5173).
 */
import { chromium } from "playwright";
import { readFileSync, mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const SHOTS = resolve(ROOT, "shots");
const API = "http://127.0.0.1:8200";
const APP_URL =
  process.argv.find((a) => a.startsWith("--url="))?.slice(6) ??
  "http://localhost:5173";
const SPSS = resolve(ROOT, "../input/spss AttendoSuomi-Brandiseuranta_112025.sav");

const J = (b) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
async function api(path, opts) {
  const r = await fetch(`${API}${path}`, opts);
  if (!r.ok) throw new Error(`${path} → ${r.status}: ${await r.text()}`);
  return r.json();
}
function chart(qid, type, slot) {
  return {
    question_ref: qid, chart_type: type, statistic: "pct", classifying_var: null,
    number_format: { mode: "auto", pct_decimals: 0, mean_decimals: 1, count_round_up: false, show_pct_sign: true },
    sort: { basis: "pct", topbox_codes: [], descending: true }, template_slot: slot,
    elements: { title: true, legend: true, n: true, axis_names: true, filter_var: true, data_labels: true },
    scatter_xy: null, show_not_answered: false, show_empty_categories: false,
    not_answered_codes: null, category_label_overrides: [], slide_title: null, slide_description: null,
  };
}

async function main() {
  mkdirSync(SHOTS, { recursive: true });
  const { case_id } = await api("/cases", J({ name: "Verify config schema" }));
  const form = new FormData();
  form.append("file", new Blob([readFileSync(SPSS)]), "attendo.sav");
  const { material_id } = await (await fetch(`${API}/cases/${case_id}/materials`, { method: "POST", body: form })).json();
  const { questions } = await api(`/materials/${material_id}/questions`);

  const single = questions.find((q) => q.kind === "single" && (q.category_labels?.length ?? 0) > 1 && q.chartable !== false);
  const multi = questions.find((q) => q.kind === "multi");
  if (!single || !multi) throw new Error("need a single + a multi question");
  console.log(`pie chart on single: ${single.qid}; bar on multi: ${multi.qid}`);

  const { report_id } = await api(`/cases/${case_id}/reports`,
    J({ name: "schema report", render_mode: "image", template_ref: "",
        charts: [chart(single.qid, "pie", "s1"), chart(multi.qid, "horizontal_bar", "s2")] }));

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  const errors = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));

  // The UI tracks the material + reports per case in localStorage (no backend
  // list endpoint) — seed it so the report opens like a real session.
  await page.addInitScript(
    ([cid, mid, rid]) => {
      localStorage.setItem(
        `nsight.ws.${cid}`,
        JSON.stringify({ materialId: mid, reports: [{ id: rid, name: "schema report", materialId: mid }] })
      );
    },
    [case_id, material_id, report_id]
  );

  await page.goto(`${APP_URL}/cases/${case_id}`, { waitUntil: "networkidle", timeout: 30000 });
  await page.getByRole("tab", { name: "Reports" }).click();
  await page.waitForTimeout(300);
  await page.getByText("schema report").first().click();
  await page.getByRole("button", { name: "Configure" }).first().click();
  await page.waitForSelector('img[alt="Chart preview"]', { timeout: 40000 });
  await page.waitForTimeout(800);

  // Chart 1 (pie) active by default — click its left-list item to be sure.
  await page.getByText("Pie Chart").first().click().catch(() => {});
  await page.waitForTimeout(500);
  const pieHasClassifying = await page.getByText("Classifying variable").count();
  await page.screenshot({ path: resolve(SHOTS, "config-pie.png"), fullPage: true });

  // Chart 2 (horizontal bar) — select via its left-list item subtitle.
  await page.getByText("Horizontal Bar").first().click();
  await page.waitForTimeout(900);
  const barHasClassifying = await page.getByText("Classifying variable").count();
  await page.screenshot({ path: resolve(SHOTS, "config-bar.png"), fullPage: true });

  await browser.close();

  console.log(`PIE shows "Classifying variable": ${pieHasClassifying > 0}  (expect false)`);
  console.log(`BAR shows "Classifying variable": ${barHasClassifying > 0}  (expect true)`);
  if (errors.length) console.log("CONSOLE ERRORS:\n  " + errors.slice(0, 5).join("\n  "));
  const ok = pieHasClassifying === 0 && barHasClassifying > 0 && errors.length === 0;
  console.log(ok ? "RESULT: PASS" : "RESULT: FAIL");
  process.exit(ok ? 0 : 1);
}
main().catch((e) => { console.error(e); process.exit(1); });
