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

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  mkdirSync(SHOTS_DIR, { recursive: true });

  console.log("Seeding backend data…");
  const caseId = await seedCase();
  const materialId = await uploadMaterial(caseId);

  console.log(`\nLaunching browser → ${APP_URL}`);
  const browser = await chromium.launch({ headless: true });
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

  // Cleanup
  await context.close();
  await browser.close();

  console.log(`
Done!
  shots/cases.png → ${casesPath}
  shots/data.png  → ${dataPath}
`);

  // Log paths for the controller
  console.log(`SCREENSHOT_CASES=${casesPath}`);
  console.log(`SCREENSHOT_DATA=${dataPath}`);
}

main().catch((err) => {
  console.error("\nshots.mjs failed:", err);
  process.exit(1);
});
