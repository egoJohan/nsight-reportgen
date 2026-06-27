#!/usr/bin/env node
/**
 * shots-i.mjs — Task I: progressive Configure preview.
 *
 *   progressive-generating.png  Chart visible with BOTH dashed placeholder
 *                               regions: "✨ Generating title…" over the top
 *                               title band AND "✨ Shortening labels…" over the
 *                               (horizontal-bar) left label gutter. Captured by
 *                               holding the AI responses so the pending state
 *                               stays on screen while the PNG renders.
 *   progressive-done.png        The same chart after both resolved — AI title
 *                               in the title region, short labels baked into the
 *                               chart, no overlays.
 *
 * Drives the running :8200 backend (egoHive up for the AI title/labels).
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

async function waitForChartImg(page) {
  await page.waitForSelector('img[alt="Chart preview"]', { timeout: 40_000 });
  await page.waitForFunction(
    () => {
      const img = document.querySelector('img[alt="Chart preview"]');
      return img && img.complete && img.naturalWidth > 0;
    },
    null,
    { timeout: 40_000 }
  );
}

async function openConfigure(page, reportName) {
  await page.goto(`${APP_URL}/cases/${CASE_ID}`, {
    waitUntil: "networkidle",
    timeout: 30_000,
  });
  await page.waitForSelector('[role="tablist"]', { timeout: 15_000 });
  await page.getByRole("tab", { name: "Reports" }).click();
  await page.waitForTimeout(300);
  await page.getByText(reportName).first().click();
  await page.waitForSelector("text=Add selected", { timeout: 15_000 });
  // Jump straight to Configure.
  await page.getByRole("button", { name: "Configure" }).first().click();
}

let CASE_ID;

async function main() {
  mkdirSync(SHOTS_DIR, { recursive: true });

  console.log("Seeding backend data…");
  const { case_id: caseId } = await apiFetch("/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: "Task I — progressive preview" }),
  });
  CASE_ID = caseId;

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
  // Lead with a single categorical question that HAS descriptive category
  // labels (so the "Shortening labels…" region is well-motivated) — forced to
  // horizontal_bar so the label gutter is the obvious left strip. Prefer the
  // "where in Finland" geography question; fall back to any suitable single.
  const suitable = (q) =>
    q.kind === "single" &&
    q.chartable !== false &&
    (q.values?.length ?? 0) > 0 &&
    (q.category_labels?.length ?? 0) > 1 &&
    q.suggested_chart_type !== "scatter";
  const lead =
    questions.find((q) => suitable(q) && /Suomea asut/i.test(q.text ?? "")) ??
    questions.find(suitable);
  if (!lead) throw new Error("No suitable single categorical question found");
  const charts = [makeChart(lead.qid, "horizontal_bar", "s1")];
  console.log(`  lead chart: ${lead.qid} (horizontal_bar) — ${lead.text}`);

  // Canned AI success responses used ONLY for the "done" shot, because egoHive
  // may be unavailable in this environment. The frontend success path is fully
  // exercised: the title streams into the region, and the real backend
  // re-renders the PNG with these SHORT labels (the label overlay then clears).
  const shorten = (full) => {
    const map = {
      Pääkaupunkiseudulla: "Pääkaupunkiseutu",
      "Muualla Etelä-Suomessa": "Etelä-Suomi",
      "Länsi-Suomessa": "Länsi-Suomi",
      "Pohjois-Suomessa": "Pohjois-Suomi",
      "Itä-Suomessa": "Itä-Suomi",
      "Keski-Suomessa": "Keski-Suomi",
    };
    if (map[full]) return map[full];
    // Generic: drop a leading "Muualla ", normalise "…ssa/ssä" → root.
    let s = full.replace(/^Muualla\s+/i, "").replace(/ssa$|ssä$/i, "");
    return s.length > 16 ? s.slice(0, 15) + "…" : s;
  };
  const cannedOverrides = (lead.category_labels ?? [])
    .map((full) => [full, shorten(full)])
    .filter(([full, short]) => short && short !== full);
  const cannedTitle = "Vastaajien maantieteellinen jakauma Suomessa";

  const reportName = "Task I report";
  const { report_id: reportId } = await apiFetch(`/cases/${caseId}/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: reportName,
      render_mode: "image",
      template_ref: "",
      charts,
    }),
  });
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

  // ── Hold the AI responses so the pending placeholders stay on screen. ──────
  const aiRoute = "**/materials/*/ai/**";
  await page.route(aiRoute, async (route) => {
    // Delay well past the screenshot window; reload later releases these.
    await new Promise((r) => setTimeout(r, 120_000));
    await route.continue();
  });

  // ── Shot A: mid-generation (chart visible + both dashed regions) ──────────
  console.log("Shot: progressive-generating…");
  await openConfigure(page, reportName);
  await waitForChartImg(page);
  // Both dashed placeholder regions must be present.
  await page.getByText("Generating title…").first().waitFor({
    state: "visible",
    timeout: 20_000,
  });
  await page.getByText("Shortening labels…").first().waitFor({
    state: "visible",
    timeout: 20_000,
  });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
  const genPath = resolve(SHOTS_DIR, "progressive-generating.png");
  await page.screenshot({ path: genPath });
  console.log(`  Saved: ${genPath}`);

  // ── Shot B: done — resolve the AI, then capture. ──────────────────────────
  // egoHive may be 503 in this environment, so fulfill the AI endpoints with
  // canned success responses. The frontend's success path runs for real: the
  // title lands in the region and the backend re-renders the PNG with the
  // SHORT labels (clearing the label overlay).
  console.log("Shot: progressive-done… (resolving AI + reloading)");
  await page.unroute(aiRoute);
  await page.route("**/materials/*/ai/slide-title", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ title: cannedTitle }),
    })
  );
  await page.route("**/materials/*/ai/short-labels", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ overrides: cannedOverrides }),
    })
  );
  await page.reload({ waitUntil: "networkidle", timeout: 30_000 });
  // Land on Configure again.
  await openConfigure(page, reportName);
  // Wait for the auto-AI pass to finish (banner appears then detaches).
  try {
    await page.waitForSelector("text=Preparing your report", { timeout: 8_000 });
  } catch {
    console.log("  (AI banner not seen — may have completed already)");
  }
  await page
    .waitForSelector("text=Preparing your report", {
      state: "detached",
      timeout: 150_000,
    })
    .catch(() => console.log("  (AI banner still present after wait)"));
  await waitForChartImg(page);
  // The AI title must have landed in the title region.
  await page
    .getByText(cannedTitle)
    .first()
    .waitFor({ state: "visible", timeout: 20_000 })
    .catch(() => console.log("  (canned title not seen)"));
  // Overlays must be gone.
  await page
    .getByText("Generating title…")
    .first()
    .waitFor({ state: "detached", timeout: 20_000 })
    .catch(() => {});
  await page
    .getByText("Shortening labels…")
    .first()
    .waitFor({ state: "detached", timeout: 20_000 })
    .catch(() => {});
  // Let the short-label PNG re-render settle.
  await page.waitForTimeout(2500);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(300);
  const donePath = resolve(SHOTS_DIR, "progressive-done.png");
  await page.screenshot({ path: donePath });
  console.log(`  Saved: ${donePath}`);

  const saved = await apiFetch(`/cases/${caseId}/reports/${reportId}`);
  console.log(
    `  PERSISTED_SLIDE_TITLE=${JSON.stringify(saved.charts?.[0]?.slide_title)}`
  );
  console.log(
    `  PERSISTED_OVERRIDES=${(saved.charts?.[0]?.category_label_overrides ?? []).length}`
  );

  await context.close();
  await browser.close();

  console.log(`\nSCREENSHOT_GENERATING=${genPath}`);
  console.log(`SCREENSHOT_DONE=${donePath}`);
}

main().catch((err) => {
  console.error("\nshots-i.mjs failed:", err);
  process.exit(1);
});
