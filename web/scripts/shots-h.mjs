#!/usr/bin/env node
/**
 * shots-h.mjs — Task H screenshots.
 *
 *   h-configure-title.png  Configure preview headline = short AI slide title,
 *                          chart-type dropdown open with greyed incompatible
 *                          types (multi-response question → no pie/doughnut).
 *   h-select-disabled.png  Select step with an open-ended (non-chartable)
 *                          question disabled + "Not chartable" badge.
 *
 * Drives the running :8200 backend (egoHive up for the AI titles).
 */

import { chromium } from "playwright";
import { readFileSync, mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const SHOTS_DIR = resolve(ROOT, "shots");
const API = "http://127.0.0.1:8200";
const SPSS_PATH = resolve(
  ROOT,
  "../input/spss AttendoSuomi-Brandiseuranta_112025.sav"
);
const APP_URL =
  process.env.VITE_PREVIEW_URL ??
  process.argv.find((a) => a.startsWith("--url="))?.slice(6) ??
  "http://localhost:4173";

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

function makeChart(questionRef, chartType, slot) {
  return {
    question_ref: questionRef,
    chart_type: chartType || "vertical_bar",
    statistic: "pct",
    classifying_var: null,
    number_format: {
      mode: "auto",
      pct_decimals: 0,
      mean_decimals: 1,
      count_round_up: false,
      show_pct_sign: true,
    },
    sort: { basis: "pct", topbox_codes: [], descending: true },
    template_slot: slot,
    elements: {
      title: true,
      legend: true,
      n: true,
      axis_names: true,
      filter_var: true,
      data_labels: true,
    },
    scatter_xy: null,
    show_not_answered: false,
    show_empty_categories: false,
    not_answered_codes: null,
    category_label_overrides: [],
    slide_title: null,
    slide_description: null,
  };
}

async function main() {
  mkdirSync(SHOTS_DIR, { recursive: true });

  console.log("Seeding backend data…");
  const { case_id: caseId } = await apiFetch("/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: "Task H — chartability" }),
  });

  const fileBytes = readFileSync(SPSS_PATH);
  const form = new FormData();
  form.append(
    "file",
    new Blob([fileBytes], { type: "application/octet-stream" }),
    "AttendoSuomi-Brandiseuranta_112025.sav"
  );
  const up = await fetch(`${API}/cases/${caseId}/materials`, {
    method: "POST",
    body: form,
  });
  const { material_id: materialId } = await up.json();
  console.log(`  case=${caseId} material=${materialId}`);

  const { questions } = await apiFetch(`/materials/${materialId}/questions`);
  // Lead with a MULTI-response question so Configure greys pie/doughnut.
  const multi = questions.find(
    (q) => q.kind === "multi" && q.chartable !== false
  );
  const singles = questions.filter(
    (q) =>
      q.kind === "single" &&
      q.chartable !== false &&
      (q.values?.length ?? 0) > 0 &&
      q.suggested_chart_type !== "scatter"
  );
  const picks = [multi, singles[0], singles[1]].filter(Boolean);
  const charts = picks.map((q, i) =>
    makeChart(q.qid, q.suggested_chart_type, `s${i + 1}`)
  );
  console.log(`  lead multi chart: ${multi.qid} (${multi.suggested_chart_type})`);

  const { report_id: reportId } = await apiFetch(
    `/cases/${caseId}/reports`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "Task H report",
        render_mode: "image",
        template_ref: "",
        charts,
      }),
    }
  );
  const reportName = "Task H report";
  console.log(`  report=${reportId} (${charts.length} charts)`);

  const browser = await chromium.launch({ headless: true, channel: "chrome" });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  await page.addInitScript(() => {
    const style = document.createElement("style");
    style.textContent =
      "*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }";
    document.head.appendChild(style);
  });
  await page.addInitScript(
    ({ caseId, materialId, reportId, reportName }) => {
      localStorage.setItem(
        `nsight.ws.${caseId}`,
        JSON.stringify({
          materialId,
          reports: [{ id: reportId, name: reportName }],
        })
      );
    },
    { caseId, materialId, reportId, reportName }
  );

  // Open the report wizard (lands on Select).
  await page.goto(`${APP_URL}/cases/${caseId}`, {
    waitUntil: "networkidle",
    timeout: 30_000,
  });
  await page.waitForSelector('[role="tablist"]', { timeout: 15_000 });
  await page.getByRole("tab", { name: "Reports" }).click();
  await page.waitForTimeout(300);
  await page.getByText(reportName).first().click();
  await page.waitForSelector("text=Add selected", { timeout: 15_000 });

  // Wait for the auto AI-format pass (titles + labels) to finish so the
  // Configure preview will render the AI headline.
  console.log("Waiting for AI auto-format (egoHive)…");
  try {
    await page.waitForSelector("text=Preparing your report", {
      timeout: 10_000,
    });
  } catch {
    console.log("  (AI banner not seen — may have completed already)");
  }
  await page
    .waitForSelector("text=Preparing your report", {
      state: "detached",
      timeout: 150_000,
    })
    .catch(() => console.log("  (AI banner still present after wait)"));
  await page.waitForTimeout(1500);

  // Confirm the persisted slide_title for the lead chart.
  const saved = await apiFetch(`/cases/${caseId}/reports/${reportId}`);
  const leadTitle = saved.charts?.[0]?.slide_title;
  console.log(`  LEAD_SLIDE_TITLE=${JSON.stringify(leadTitle)}`);

  // ── Shot A: Select step with a non-chartable question disabled ───────────
  console.log("Shot: h-select-disabled…");
  const searchBox = page
    .locator('input[placeholder="Search questions…"]:visible')
    .first();
  const badge = page
    .getByText("Not chartable", { exact: true })
    .locator("visible=true");
  await searchBox.fill("Muut hoivapalvelut");
  await page.waitForTimeout(500);
  // Fallback: if nothing matched, clear and search a known free-text fragment.
  if ((await badge.count()) === 0) {
    await searchBox.fill("sanalla");
    await page.waitForTimeout(500);
  }
  await badge.first().waitFor({ state: "visible", timeout: 10_000 });
  const selectPath = resolve(SHOTS_DIR, "h-select-disabled.png");
  await page.screenshot({ path: selectPath });
  console.log(`  Saved: ${selectPath}`);
  await searchBox.fill("");
  await page.waitForTimeout(300);

  // ── Shot B: Configure — AI title headline + greyed chart types ───────────
  console.log("Shot: h-configure-title…");
  await page.getByRole("button", { name: "Configure" }).first().click();
  await page.waitForSelector('img[alt="Chart preview"]', { timeout: 30_000 });
  await page.waitForFunction(
    () => {
      const img = document.querySelector('img[alt="Chart preview"]');
      return img && img.complete && img.naturalWidth > 0;
    },
    null,
    { timeout: 30_000 }
  );
  await page.waitForTimeout(500);
  // Primary H.1 proof: full preview with the AI title as the chart headline.
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(300);
  const configurePath = resolve(SHOTS_DIR, "h-configure-title.png");
  await page.screenshot({ path: configurePath });
  console.log(`  Saved: ${configurePath}`);

  // H.3 proof: open the Chart type dropdown — pie/doughnut greyed for a
  // multi-response question.
  await page.locator('[data-slot="select-trigger"]:visible').first().click();
  await page.waitForSelector('[data-slot="select-content"]', {
    timeout: 5_000,
  });
  await page.waitForTimeout(400);
  const typesPath = resolve(SHOTS_DIR, "h-configure-types.png");
  await page.screenshot({ path: typesPath });
  console.log(`  Saved: ${typesPath}`);

  await context.close();
  await browser.close();

  console.log(`\nSCREENSHOT_H_SELECT=${selectPath}`);
  console.log(`SCREENSHOT_H_CONFIGURE=${configurePath}`);
  console.log(`SCREENSHOT_H_TYPES=${typesPath}`);
}

main().catch((err) => {
  console.error("\nshots-h.mjs failed:", err);
  process.exit(1);
});
