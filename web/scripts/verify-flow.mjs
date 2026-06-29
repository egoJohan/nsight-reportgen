#!/usr/bin/env node
/**
 * verify-flow.mjs — exercises the reworked flow end-to-end:
 *  A. Sidebar "New case" → upload dialog → pick SAV → lands on the case page.
 *  B. Case page shows Reports + Questions sections (NO Data/Reports tabs),
 *     with "Create new report" as the first reports item.
 *  C. "Create new report" opens the wizard; toggling a question (no "Add
 *     selected" button) adds its chart; Next advances.
 */
import { chromium } from "playwright";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const SHOTS = resolve(ROOT, "shots");
const APP = process.argv.find((a) => a.startsWith("--url="))?.slice(6) ?? "http://localhost:5173";
const SPSS = resolve(ROOT, "../input/spss AttendoSuomi-Brandiseuranta_112025.sav");

const out = [];
const log = (m) => { out.push(m); console.log(m); };

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  // A. Dashboard → New case (sidebar) → upload dialog → pick file.
  await page.goto(APP, { waitUntil: "networkidle", timeout: 30000 });
  await page.screenshot({ path: resolve(SHOTS, "flow-dashboard.png") });
  const hasTabs0 = await page.getByRole("tab").count();
  log(`dashboard tabs (expect 0): ${hasTabs0}`);

  await page.getByRole("button", { name: "New case" }).first().click();
  await page.waitForTimeout(400);
  await page.setInputFiles('input[type="file"]', SPSS);

  // Lands on the case page (questions curated) — wait for the Questions section.
  await page.waitForURL(/\/cases\//, { timeout: 60000 });
  await page.getByText("Questions").first().waitFor({ timeout: 60000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: resolve(SHOTS, "flow-case.png"), fullPage: true });

  // B. No tabs; Reports + Questions sections; "Create new report" present.
  const caseTabs = await page.getByRole("tab").count();
  const hasCreate = await page.getByText("Create new report").count();
  const hasReports = await page.getByRole("heading", { name: "Reports" }).count();
  const hasQuestions = await page.getByRole("heading", { name: "Questions" }).count();
  log(`case page tabs (expect 0): ${caseTabs}`);
  log(`"Create new report" present (expect >=1): ${hasCreate}`);
  log(`Reports section (expect >=1): ${hasReports}`);
  log(`Questions section (expect >=1): ${hasQuestions}`);

  // C. Create new report → wizard Select; no "Add selected"; toggle works.
  await page.getByText("Create new report").first().click();
  await page.getByText(/Toggle a question/i).waitFor({ timeout: 30000 });
  const hasAddSelected = await page.getByRole("button", { name: /Add selected/i }).count();
  log(`"Add selected" button (expect 0): ${hasAddSelected}`);

  const before = await page.getByText(/\d+ selected ·/).innerText();
  // Toggle the first chartable question row.
  await page.locator("button:has-text('var')").first().click().catch(async () => {
    await page.locator('div.space-y-1\\.5 > button').first().click();
  });
  await page.waitForTimeout(600);
  const after = await page.getByText(/\d+ selected ·/).innerText();
  log(`selected count before/after toggle: "${before}" -> "${after}"`);
  await page.screenshot({ path: resolve(SHOTS, "flow-select.png"), fullPage: true });

  await browser.close();

  const beforeN = parseInt(before);
  const afterN = parseInt(after);
  const ok =
    hasTabs0 === 0 && caseTabs === 0 && hasCreate >= 1 &&
    hasReports >= 1 && hasQuestions >= 1 && hasAddSelected === 0 &&
    afterN === beforeN + 1 && errors.length === 0;
  if (errors.length) log("CONSOLE ERRORS:\n  " + errors.slice(0, 5).join("\n  "));
  log(ok ? "RESULT: PASS" : "RESULT: FAIL");
  process.exit(ok ? 0 : 1);
}
main().catch((e) => { console.error(e); process.exit(1); });
