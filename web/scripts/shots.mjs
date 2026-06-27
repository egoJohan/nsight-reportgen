#!/usr/bin/env node
/**
 * shots.mjs — Takes Playwright screenshots of the nSight React app.
 *
 * Usage:
 *   node scripts/shots.mjs [--url=http://localhost:4173]
 *
 * Expects:
 *  - A preview/dev server at VITE_PREVIEW_URL or --url (default: http://localhost:4173).
 *  - The FastAPI backend running at http://127.0.0.1:8200.
 *
 * Seeds a fresh case + uploads the Attendo SPSS file via the API, then
 * screenshots both the Cases page and the Case → Data page.
 */

import { chromium } from "playwright";
import { readFileSync, mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const SHOTS_DIR = resolve(ROOT, "shots");
const API = "http://127.0.0.1:8200";

// SPSS test fixture — shipped with the project
const SPSS_PATH = resolve(
  ROOT,
  "../input/spss AttendoSuomi-Brandiseuranta_112025.sav"
);

// App URL — override via env or --url= flag
const APP_URL =
  process.env.VITE_PREVIEW_URL ??
  process.argv.find((a) => a.startsWith("--url="))?.slice(6) ??
  "http://localhost:4173";

// ── Helpers ──────────────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

async function seedCase() {
  const { case_id } = await apiFetch("/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: "Attendo Suomi — Brand 2025" }),
  });
  console.log(`  Created case: ${case_id}`);
  return case_id;
}

async function uploadMaterial(caseId) {
  const fileBytes = readFileSync(SPSS_PATH);
  const blob = new Blob([fileBytes], { type: "application/octet-stream" });
  const form = new FormData();
  form.append("file", blob, "AttendoSuomi-Brandiseuranta_112025.sav");

  const res = await fetch(`${API}/cases/${caseId}/materials`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`Upload failed: ${res.status} ${text}`);
  }
  const result = await res.json();
  console.log(
    `  Uploaded material: ${result.material_id} (${result.question_count} questions)`
  );
  return result.material_id;
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
    slide_title: null,
    slide_description: null,
  };
}

async function seedReport(caseId, materialId) {
  // Pick a few questions to pre-populate the report's charts. Avoid chart
  // types that need extra config to render (stacked → classifying var; scatter).
  const STACKED = new Set(["stacked_vertical_bar", "stacked_horizontal_bar"]);
  const { questions } = await apiFetch(`/materials/${materialId}/questions`);
  const safe = questions.filter(
    (q) =>
      !STACKED.has(q.suggested_chart_type) &&
      q.suggested_chart_type !== "scatter"
  );
  const picks = (safe.length >= 3 ? safe : questions).slice(0, 3);
  const charts = picks.map((q, i) =>
    makeChart(q.qid, q.suggested_chart_type, `s${i + 1}`)
  );

  const name = "Brand Tracker — Q4 2025";
  const { report_id } = await apiFetch(`/cases/${caseId}/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      render_mode: "image",
      template_ref: "",
      charts,
    }),
  });
  console.log(`  Created report: ${report_id} (${charts.length} charts)`);
  return { reportId: report_id, name };
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  mkdirSync(SHOTS_DIR, { recursive: true });

  console.log("Seeding backend data…");
  const caseId = await seedCase();
  const materialId = await uploadMaterial(caseId);
  const { reportId, name: reportName } = await seedReport(caseId, materialId);

  console.log(`\nLaunching browser → ${APP_URL}`);
  // Use the full Chrome channel (new headless) — the bundled headless shell
  // lacks the PDF viewer, so the Download step's embedded PDF would be blank.
  const browser = await chromium.launch({ headless: true, channel: "chrome" });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  // Disable CSS transitions/animations for stable screenshots
  await page.addInitScript(() => {
    const style = document.createElement("style");
    style.textContent =
      "*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }";
    document.head.appendChild(style);
  });

  // Seed the per-case workspace (localStorage) so the Reports tab and the
  // DataTab question browser are populated on load (no UI upload needed).
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

  // ── Screenshot 1: Cases page ─────────────────────────────────────────────
  console.log("\nShot 1: Cases page…");
  await page.goto(`${APP_URL}/`, { waitUntil: "networkidle", timeout: 30_000 });
  // Wait for sidebar and case list to render
  await page.waitForSelector("[data-slot=sidebar-menu-button]", { timeout: 15_000 });
  await page.waitForTimeout(400);
  const casesPath = resolve(SHOTS_DIR, "cases.png");
  await page.screenshot({ path: casesPath });
  console.log(`  Saved: ${casesPath}`);

  // ── Screenshot 2: Case → Data tab (question browser) ─────────────────────
  // Inject the materialId into localStorage so DataTab shows the question table
  // immediately when the page loads (avoiding the need to drive the file upload
  // through the browser, which is flaky in headless).
  console.log("\nShot 2: Case → Data tab…");

  // Navigate to the case detail page first
  await page.goto(`${APP_URL}/cases/${caseId}`, {
    waitUntil: "networkidle",
    timeout: 30_000,
  });
  await page.waitForSelector('[role="tablist"]', { timeout: 15_000 });

  // The DataTab keeps materialId in local React state. To show the question
  // browser, we call the upload API again (or reuse the existing materialId)
  // and simulate a successful upload response by triggering the component's
  // "upload" path via a hidden file input — but that requires a real file pick.
  //
  // Simplest stable approach: use page.evaluate to locate the React fiber and
  // fire the onUploaded callback. If that's too fragile, we screenshot the
  // upload state (which is polished) and add the question table via a second
  // navigation approach.
  //
  // Preferred: use Playwright to upload the file through the hidden input.
  const fileInput = page.locator('input[type="file"]');
  if (await fileInput.count() > 0) {
    await fileInput.setInputFiles(SPSS_PATH);
    // Wait for upload to complete and question table to appear
    await page.waitForSelector('[data-slot="table"]', { timeout: 60_000 });
    await page.waitForTimeout(600);
  } else {
    console.warn("  File input not found — screenshotting upload state instead");
    await page.waitForTimeout(400);
  }

  const dataPath = resolve(SHOTS_DIR, "data.png");
  await page.screenshot({ path: dataPath });
  console.log(`  Saved: ${dataPath}`);

  // ── Screenshot 3: Reports tab ────────────────────────────────────────────
  console.log("\nShot 3: Reports tab…");
  await page.goto(`${APP_URL}/cases/${caseId}`, {
    waitUntil: "networkidle",
    timeout: 30_000,
  });
  await page.waitForSelector('[role="tablist"]', { timeout: 15_000 });
  await page.getByRole("tab", { name: "Reports" }).click();
  await page.waitForTimeout(400);
  const reportsPath = resolve(SHOTS_DIR, "reports.png");
  await page.screenshot({ path: reportsPath });
  console.log(`  Saved: ${reportsPath}`);

  // ── Screenshot 4: Wizard → Select ────────────────────────────────────────
  console.log("\nShot 4: Wizard Select step…");
  // Open the seeded report by clicking its card.
  await page.getByText(reportName).first().click();
  // Select step shows the searchable checklist of questions.
  await page.waitForSelector("text=Add selected", { timeout: 15_000 });
  await page.waitForTimeout(500);
  const selectPath = resolve(SHOTS_DIR, "wizard-select.png");
  await page.screenshot({ path: selectPath });
  console.log(`  Saved: ${selectPath}`);

  // ── Screenshot 5: Wizard → Configure (large live preview) ────────────────
  console.log("\nShot 5: Wizard Configure step…");
  await page.getByRole("button", { name: "Configure" }).first().click();
  // Wait for the live preview <img> to actually finish loading the PNG.
  await page.waitForSelector('img[alt="Chart preview"]', { timeout: 30_000 });
  await page.waitForFunction(
    () => {
      const img = document.querySelector('img[alt="Chart preview"]');
      return img && img.complete && img.naturalWidth > 0;
    },
    null,
    { timeout: 30_000 }
  );
  await page.waitForTimeout(400);
  const configurePath = resolve(SHOTS_DIR, "wizard-configure.png");
  await page.screenshot({ path: configurePath });
  console.log(`  Saved: ${configurePath}`);

  // ── Screenshot 6: Wizard → Review (grid of live thumbnails) ──────────────
  console.log("\nShot 6: Wizard Review step…");
  await page.getByRole("button", { name: "Next" }).click();
  await page.waitForSelector("text=/Review —/", { timeout: 15_000 });
  // Wait for all chart thumbnails to actually finish loading.
  await page.waitForFunction(
    () => {
      const imgs = Array.from(
        document.querySelectorAll('img[alt="Chart preview"]')
      );
      return (
        imgs.length >= 3 &&
        imgs.every((img) => img.complete && img.naturalWidth > 0)
      );
    },
    null,
    { timeout: 60_000 }
  );
  await page.waitForTimeout(400);
  const reviewPath = resolve(SHOTS_DIR, "wizard-review.png");
  await page.screenshot({ path: reviewPath });
  console.log(`  Saved: ${reviewPath}`);

  // ── Screenshot 7: Wizard → Slides (title/description + reorder) ──────────
  console.log("\nShot 7: Wizard Slides step…");
  await page.getByRole("button", { name: "Next" }).click();
  await page.waitForSelector('textarea[data-slot="textarea"]', {
    timeout: 15_000,
  });
  // Type a sample title/description into the first slide for a richer shot.
  const firstTitle = page.locator('input[data-slot="input"]').first();
  await firstTitle.fill("Brand awareness keeps climbing");
  const firstDesc = page.locator('textarea[data-slot="textarea"]').first();
  await firstDesc.fill(
    "Prompted awareness rose again this quarter, led by the 25–44 segment."
  );
  // Wait for slide thumbnails to load.
  await page.waitForFunction(
    () => {
      const imgs = Array.from(
        document.querySelectorAll('img[alt="Chart preview"]')
      );
      return (
        imgs.length >= 3 &&
        imgs.every((img) => img.complete && img.naturalWidth > 0)
      );
    },
    null,
    { timeout: 60_000 }
  );
  await page.waitForTimeout(400);
  const slidesPath = resolve(SHOTS_DIR, "wizard-slides.png");
  await page.screenshot({ path: slidesPath });
  console.log(`  Saved: ${slidesPath}`);

  // ── Screenshot 8: Wizard → Download (after a successful Generate) ────────
  console.log("\nShot 8: Wizard Download step (rendering, can take ~30s)…");
  await page.getByRole("button", { name: "Next" }).click();
  await page.waitForSelector('button:has-text("Generate deck")', {
    timeout: 15_000,
  });
  await page.getByRole("button", { name: "Generate deck" }).click();
  // The render chain (PPTX → PDF → raster) is slow — wait generously.
  await page.waitForSelector('iframe[title="Report PDF preview"]', {
    timeout: 90_000,
  });
  // Give the embedded PDF (PDFium) a moment to paint inside the iframe.
  await page.waitForTimeout(6000);
  const downloadPath = resolve(SHOTS_DIR, "wizard-download.png");
  await page.screenshot({ path: downloadPath });
  console.log(`  Saved: ${downloadPath}`);

  // Cleanup
  await context.close();
  await browser.close();

  console.log(`
Done!
  shots/cases.png            → ${casesPath}
  shots/data.png             → ${dataPath}
  shots/reports.png          → ${reportsPath}
  shots/wizard-select.png    → ${selectPath}
  shots/wizard-configure.png → ${configurePath}
  shots/wizard-review.png    → ${reviewPath}
  shots/wizard-slides.png    → ${slidesPath}
  shots/wizard-download.png  → ${downloadPath}
`);

  // Log paths for the controller
  console.log(`SCREENSHOT_CASES=${casesPath}`);
  console.log(`SCREENSHOT_DATA=${dataPath}`);
  console.log(`SCREENSHOT_REPORTS=${reportsPath}`);
  console.log(`SCREENSHOT_WIZARD_SELECT=${selectPath}`);
  console.log(`SCREENSHOT_WIZARD_CONFIGURE=${configurePath}`);
  console.log(`SCREENSHOT_WIZARD_REVIEW=${reviewPath}`);
  console.log(`SCREENSHOT_WIZARD_SLIDES=${slidesPath}`);
  console.log(`SCREENSHOT_WIZARD_DOWNLOAD=${downloadPath}`);
}

main().catch((err) => {
  console.error("\nshots.mjs failed:", err);
  process.exit(1);
});
