#!/usr/bin/env node
/**
 * auto-check.mjs — Verifies the DEFAULT (no manual clicks) AI formatting path.
 *
 * Seeds a fresh case + uploads the Attendo SPSS, creates an EMPTY report, then
 * drives the wizard UI to ADD a long-label question (var39, a 1–5 scale whose
 * labels include "1 - Ei vastaa lainkaan" / "5 - Vastaa erittäin hyvin").
 * WITHOUT clicking any AI button it then:
 *   1. lands on Configure and screenshots shots/auto-configure.png
 *      (preview MUST show SHORT labels via auto-applied overrides), and
 *   2. opens Slides and screenshots shots/auto-slides.png
 *      (title field MUST show the AI descriptive title, not the question text).
 *
 * Usage: node scripts/auto-check.mjs --url=http://localhost:4290
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
  "http://localhost:4290";

// The long-label question we add via the UI.
const TARGET_QID = "var39";
const QUESTION_SNIPPET = "Mahdollistaa hyvän arjen";

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

async function main() {
  mkdirSync(SHOTS_DIR, { recursive: true });

  console.log("Seeding backend data…");
  const { case_id: caseId } = await apiFetch("/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: "Auto-AI default-path check" }),
  });
  const form = new FormData();
  form.append(
    "file",
    new Blob([readFileSync(SPSS_PATH)]),
    "AttendoSuomi-Brandiseuranta_112025.sav"
  );
  const up = await (
    await fetch(`${API}/cases/${caseId}/materials`, {
      method: "POST",
      body: form,
    })
  ).json();
  const materialId = up.material_id;
  console.log(`  case=${caseId} material=${materialId}`);

  // EMPTY report — charts get added through the UI so the auto-formatter runs.
  const reportName = "Auto-AI Default Path";
  const { report_id: reportId } = await apiFetch(
    `/cases/${caseId}/reports`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: reportName,
        render_mode: "image",
        template_ref: "",
        charts: [],
      }),
    }
  );
  console.log(`  report=${reportId} (0 charts)`);

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

  // Open the report → wizard Select step.
  console.log("\nOpening wizard…");
  await page.goto(`${APP_URL}/cases/${caseId}`, {
    waitUntil: "networkidle",
    timeout: 30_000,
  });
  await page.waitForSelector('[role="tablist"]', { timeout: 15_000 });
  await page.getByRole("tab", { name: "Reports" }).click();
  await page.getByText(reportName).first().click();
  await page.waitForSelector("text=Add selected", { timeout: 15_000 });

  // Add the long-label question — NO AI button clicked.
  console.log(`Adding question ${TARGET_QID} (${QUESTION_SNIPPET})…`);
  await page
    .locator('input[placeholder="Search questions…"]:visible')
    .first()
    .fill(QUESTION_SNIPPET);
  await page.waitForTimeout(300);
  await page
    .locator("button:visible", { hasText: QUESTION_SNIPPET })
    .first()
    .click();
  await page.getByRole("button", { name: /Add selected/ }).click();

  // We should now be on Configure. The auto-formatter fires in the background.
  await page.waitForSelector('img[alt="Chart preview"]', { timeout: 30_000 });

  // Poll the backend until the auto-generated overrides + title are persisted.
  console.log("Waiting for auto AI formatting to land (egoHive ~3–8s/call)…");
  let saved = null;
  for (let i = 0; i < 60; i++) {
    const rep = await apiFetch(`/cases/${caseId}/reports/${reportId}`);
    const c = rep.charts?.[0];
    if (
      c &&
      (c.category_label_overrides?.length ?? 0) > 0 &&
      c.slide_title
    ) {
      saved = c;
      break;
    }
    await page.waitForTimeout(1000);
  }
  if (!saved) {
    throw new Error(
      "Auto formatting did NOT persist overrides + slide_title within 60s"
    );
  }
  console.log(
    `  overrides: ${JSON.stringify(saved.category_label_overrides)}`
  );
  console.log(`  slide_title: ${JSON.stringify(saved.slide_title)}`);

  // Let the live preview re-render with the short labels, then screenshot.
  await page.waitForFunction(
    () => {
      const img = document.querySelector('img[alt="Chart preview"]');
      return img && img.complete && img.naturalWidth > 0;
    },
    null,
    { timeout: 30_000 }
  );
  // Wait for the progress banner (if still visible) to clear.
  await page
    .waitForSelector("text=Preparing your report", {
      state: "detached",
      timeout: 30_000,
    })
    .catch(() => {});
  await page.waitForTimeout(800);
  const configurePath = resolve(SHOTS_DIR, "auto-configure.png");
  await page.screenshot({ path: configurePath });
  console.log(`  Saved: ${configurePath}`);

  // Navigate to Slides (Configure → Review → Slides via Next).
  console.log("\nNavigating to Slides…");
  await page.getByRole("button", { name: "Slides" }).first().click();
  await page.waitForSelector('input[data-slot="input"]:visible', {
    timeout: 15_000,
  });
  await page.waitForTimeout(500);
  const titleValue = await page
    .locator('input[data-slot="input"]:visible')
    .first()
    .inputValue();
  console.log(`  Slides title field value: ${JSON.stringify(titleValue)}`);

  await page.waitForFunction(
    () => {
      const imgs = Array.from(
        document.querySelectorAll('img[alt="Chart preview"]')
      );
      return imgs.length >= 1 && imgs.every((i) => i.complete && i.naturalWidth > 0);
    },
    null,
    { timeout: 30_000 }
  );
  const slidesPath = resolve(SHOTS_DIR, "auto-slides.png");
  await page.screenshot({ path: slidesPath });
  console.log(`  Saved: ${slidesPath}`);

  // Assertions.
  const questions = (await apiFetch(`/materials/${materialId}/questions`))
    .questions;
  const qtext = questions.find((q) => q.qid === TARGET_QID)?.text ?? "";
  const titleIsAi =
    !!titleValue && titleValue.trim() !== qtext.trim();
  const labelsShort = (saved.category_label_overrides ?? []).some(
    ([full, short]) => short && short !== full
  );

  console.log("\n── RESULT ──────────────────────────────────────────────");
  console.log(`  Configure short labels applied: ${labelsShort}`);
  console.log(`  Slides title is AI (≠ question text): ${titleIsAi}`);
  console.log(`  AI title observed: ${JSON.stringify(titleValue)}`);

  await browser.close();

  if (!labelsShort || !titleIsAi) {
    console.error("\nFAIL: default path did not show formatted version.");
    process.exit(1);
  }
  console.log("\nPASS: default path shows short labels + AI title.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
