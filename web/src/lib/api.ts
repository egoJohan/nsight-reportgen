import type { Me } from "@/lib/session";
import { errorMessage } from "./apiError";
// Relative by default (spec §5.4): same-origin is what makes the
// SameSite=Strict session cookie work at all, in prod (nginx) and in dev
// (the Vite proxy in vite.config.ts) alike.
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

// ---- Types ----

export interface Case {
  id: string;
  name: string;
}

export interface MissingValue {
  code: number;
  label: string;
}

export interface ValueLabel {
  code: number;
  label: string;
}

export interface Question {
  qid: string;
  kind: "single" | "multi" | "battery" | "comparison";
  // Overall measurement label: "text" / "multi" / "rating battery" / "categorical" /
  // "scale" … — shown as a tag in the browse list + details dialog.
  measurement: string;
  variables: string[];
  text: string;
  // Member qids for a comparison (overlaid parallel questions); [] otherwise.
  members?: string[];
  // Whether the question can be charted at all (false for open-ended text).
  chartable: boolean;
  // Human-readable reason when chartable === false (e.g. "Open-ended text answers").
  non_chartable_reason: string | null;
  suggested_chart_type: string;
  // Chart-type ids whose plugin suitability applies to this question.
  compatible_chart_types: string[];
  missing_values: MissingValue[];
  // All value labels incl. missing (single questions); [] for multi.
  values: ValueLabel[];
  // Base category label strings, in render order — the label-editor's list.
  category_labels: string[];
  // Endpoint gloss a stacked bar appends to its subtitle by default
  // ("1 = … · 5 = …"); "" when the question has no such rating scale.
  scale_gloss?: string;
  // Respondent-background question (age/gender/region/…) — floated to the front
  // of a new report (demographics-first convention).
  is_demographic?: boolean;
}

export interface Variable {
  name: string;
  label: string;
  measurement: string;
  n_values?: number;
  // Whether a per-category mean is meaningful (numeric/rating) — a valid combo
  // secondary variable.
  aggregatable?: boolean;
  // Whether this is a meaningful classifying/segmentation variable (background/
  // demographic categorical, not a Likert item) — drives the classifier picker.
  segmentable?: boolean;
  /** Where this sits in the classifying-variable picker: 0 background (age,
   *  region, segment flags), 1 a rating item, 2 offered only when the analyst
   *  asks to see everything. A marked variable reports 0 however it looks. */
  classifier_tier?: number;
  /** Somebody chose this deliberately for this dataset. */
  marked_classifier?: boolean;
  /** Why it is not in the default list, in an analyst's words. Empty when it
   *  is. Said out loud because silence was the actual defect: an absent
   *  variable could not be told from one the file never had. */
  not_offered_because?: string;
  // True for a BANNER classifier — a question-backed classifier (one indicator
  // column per group, e.g. Polku1+Polku2) whose segments may overlap, so it
  // supports neither a second classifier nor the "within each category" direction.
  banner?: boolean;
  // A genuine multi-response tick-box (binary 0/1) — the only kind groupable
  // into a multi-response question.
  tickbox?: boolean;
  // A rating scale (digit- or word-labelled 1..N) — groupable into a battery.
  scale?: boolean;
  // Signature of the scale; two variables can form a battery only if these match.
  scale_key?: string | null;
  // Looser signature — the scale's POINT set (1..N). Variables sharing this are
  // battery-COMPATIBLE even when worded differently (drives 'Group as battery').
  scale_compat_key?: string | null;
}

// A word-cloud value merge: variant tokens (`words`, lowercased) folded into one
// displayed word (`label`), summing their counts.
export interface WordMerge {
  label: string;
  words: string[];
}

// ---- Question details (computed summary) ----
export interface QuestionDistRow {
  category: string;
  count: number | null;
  pct: number | null;
  mean?: number | null;
}

export interface QuestionSummary {
  qid: string;
  kind: string;
  text: string;
  measurement: string;
  variables: { name: string; label: string; measurement: string }[];
  value_labels: ValueLabel[];
  missing_values: MissingValue[];
  category_labels: string[];
  scale_gloss?: string;
  chartable: boolean;
  non_chartable_reason: string | null;
  respondent_total: number;
  base_n: number | null;
  statistic: string;
  distribution: QuestionDistRow[] | null;
  mean: number | null;
  suggested_chart_type?: string;
  compatible_chart_types?: string[];
}

export interface UploadResult {
  material_id: string;
  question_count: number;
  // The SAV's embedded study title, if any (null otherwise).
  file_label?: string | null;
}

// ---- Report / ChartSpec ----

export interface NumberFormat {
  mode: "auto" | "manual";
  pct_decimals: number;
  mean_decimals: number;
  count_round_up: boolean;
  show_pct_sign: boolean;
}

export interface SortSpec {
  basis:
    | "data_order" | "pct" | "topbox_sum" | "top3_sum"
    | "bottom2_sum" | "bottom3_sum" | "mean" | "count";
  topbox_codes: number[];
  descending: boolean;
}

export interface ChartElements {
  title: boolean;
  legend: boolean;
  n: boolean;
  axis_names: boolean;
  filter_var: boolean;
  data_labels: boolean;
}

// Where the template puts its title, read off the fast preview's response
// headers (X-Title-*, X-Slide-Aspect — see routes_questions.py). Sent only on
// the fast (render_title=false) path, and only when the template's profile
// actually positions a title; null otherwise, same as a preview with no title
// info today. The frontend draws the title itself from this — never guesses
// a position — so it lands where the template's own title sits.
export interface ChartPreviewTitleMeta {
  // [left, top, width, height], each a fraction of the slide's own size.
  box: [number, number, number, number];
  font: string;
  sizePt: number;
  color: string; // "RRGGBB", no '#'
  align: "left" | "center" | "right";
  caps: boolean;
  // slide width / height, so text can be sized against the rendered box
  // without the backend also having to send an absolute slide size.
  aspect: number;
}

export interface ChartSpec {
  question_ref: string;
  chart_type: string;
  statistic: "pct" | "count" | "mean" | "median" | "sum";
  classifying_var: string | null;
  classifying_var_2?: string | null;  // secondary classifier → cross-tab combos
  number_format: NumberFormat;
  sort: SortSpec;
  template_slot: string;
  elements: ChartElements;
  scatter_xy: [string, string] | null;
  show_not_answered: boolean;
  // When false, categories that are 0% across all segments are dropped.
  show_empty_categories: boolean;
  // null = use SAV-detected missing set; an explicit list overrides it.
  not_answered_codes: number[] | null;
  // Ordered [full_label, short_label] display overrides.
  category_label_overrides: [string, string][];
  slide_title: string | null;
  // The data fingerprint the title above was generated FOR (see charts.ts::titleDataKey).
  // null/absent means either no AI title has ever been generated for this slide, OR the
  // title is hand-typed — both cases must be left alone, so this only ever GATES a
  // regeneration, it never triggers one by itself. Set together with slide_title by the
  // AI response; cleared the instant the user edits the title field by hand.
  slide_title_key?: string | null;
  slide_description: string | null;
  // Axis titles (P-C-27). Empty = no axis title. Presentation only: they land in
  // the image fingerprint, so editing one re-renders the slide, and deliberately
  // NOT in titleDataKey, so it never regenerates the headline.
  axis_x_title?: string;
  axis_y_title?: string;
  // Per-chart identity. question_ref says WHICH QUESTION a chart shows and is no
  // longer unique: a comparison section adds a second slide for a question that
  // already has a total-level one. Empty on reports saved before this existed —
  // the editor assigns one on load (the backend deliberately does not, so its
  // round-trip stays exact).
  slide_id?: string;
  // Set on a slide generated by "Compare groups", to the variable it groups by.
  // Marks it as NOT the question's primary slide, so the Step 1 question toggle
  // leaves it alone.
  compare_group?: string | null;
  // Unticked in Select: the slide stays in the report (keeping its content) but is
  // left OUT of the deck. Special slides have no catalog to be re-added from, so
  // unticking must not delete them.
  excluded?: boolean;
  // Override the methodology footer (e.g. a simpler "N = 950"); null = auto
  // ("<stat> · n = N"). "{n}" expands to the base count, "{stat}" to the stat label.
  footer_note: string | null;
  // Cross-tab percentage direction: "auto" (resolve from variable roles),
  // "classifier" (within each segment), "question" (within each base category),
  // "total" (over the grand total).
  percent_base?: "auto" | "classifier" | "question" | "total";
  // Whether the cross-tab "Total" reference series is drawn ("auto" hides it in
  // within-category % directions; "on"/"off" force it).
  show_total?: "auto" | "on" | "off";
  // Right-hand per-row summary column (stacked_horizontal_bar only). Off when
  // row_summary_fn is "none"/absent.
  row_summary_fn?:
    | "none" | "top2_sum" | "top3_sum" | "bottom2_sum" | "bottom3_sum"
    | "sum" | "mean" | "net";
  row_summary_codes?: number[];
  row_summary_pos_codes?: number[];
  row_summary_neg_codes?: number[];
  row_summary_label?: string;
  // Free-form per-chart-type options (plugin-declared config keys without a
  // first-class ChartSpec field). Optional for backward compatibility.
  options?: Record<string, unknown>;
}

// ---- Chart-type catalog (plugin-declared config schema) ----
export interface ConfigFieldOption {
  value: string;
  label: string;
}

export interface ConfigField {
  key: string;
  widget: string; // select | switch | number | variable | sort | number_format | not_answered | category_labels | scatter_xy | note
  label: string;
  help?: string;
  options?: ConfigFieldOption[];
  default?: unknown;
  required?: boolean;
}

export interface ChartTypeInfo {
  id: string;
  label: string;
  requires: string[];
  config: ConfigField[];
}

// ---- AI text generation ----

export interface AiSlideTitleBody {
  question_ref: string;
  statistic?: string;
  classifying_var?: string | null;
  number_format?: NumberFormat;
  show_not_answered?: boolean;
  not_answered_codes?: number[] | null;
  // The report's grouping, so a title for a grouped question (battery/multi) resolves.
  grouping?: GroupingOverride;
}

export interface AiShortLabelsBody {
  question_ref?: string;
  categories?: string[];
}

export interface ReportDoc {
  name: string;
  render_mode: "image";
  template_ref: string;
  charts: ChartSpec[];
  grouping?: GroupingOverride;
}

// ---- Client ----

/** Carries the HTTP status alongside the message, so a caller that needs to
 *  tell "not found" apart from "network hiccup" (the no-access customer
 *  page) does not have to parse it back out of the message text. */
/** The terms a study's own structure suggests are company or brand names, and
 *  the ones an analyst confirmed. `accepted: null` means nobody has looked —
 *  which is a different statement from an empty list, and is what the
 *  report-creation gate refuses on. */
export interface SensitiveTerms {
  proposed: string[];
  accepted: string[] | null;
  accepted_at?: string;
  accepted_by?: string;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function json<T>(res: Response): Promise<T> {
  // A session dies mid-use constantly in normal operation (idle timeout,
  // absolute expiry, a revoke from another tab) — this is the one place
  // almost every call in this file passes through, so it is the one place
  // that catches all of them and sends the browser back to sign-in instead
  // of leaving the SPA showing a broken page or looping error toasts.
  // `location.assign` (a real navigation), not `navigate()`: this module has
  // no router context, and a hard navigation also clears any in-flight
  // requests and component state that assumed a live session.
  if (res.status === 401 && !location.pathname.startsWith("/login")) {
    const next = encodeURIComponent(location.pathname + location.search);
    location.assign(`/login?next=${next}`);
    // The navigation above is async; throw so the caller's `.then` chain
    // does not go on to treat a 401 body as a success payload in the
    // meantime.
    throw new Error("401 Unauthorized: redirecting to sign-in");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    // The server's own `detail` is written for the person who made the request;
    // show that sentence rather than the JSON it arrived in.
    throw new ApiError(res.status, errorMessage(res.status, res.statusText, text));
  }
  return res.json() as Promise<T>;
}

/** Like json(), but on failure prefers the server's `detail` string over a
 *  bare status line -- the reason ("the last admin cannot be removed") IS
 *  the message the toast should show. */
async function detailedJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // not JSON — keep status text
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

async function detailedVoid(res: Response): Promise<void> {
  if (res.ok) return;
  let detail = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    // not JSON — keep status text
  }
  throw new Error(detail);
}

// All egoHive-backed AI calls (titles, short-labels, special slides) share one
// bounded concurrency gate so the title auto-batch + special-slide generation
// never collectively overload egoHive (which returns 503 under load). Transient
// 503s are retried with backoff. egoHive tolerates ~2 concurrent comfortably.
const AI_CONCURRENCY = 2;
let aiActive = 0;
const aiQueue: Array<() => void> = [];

function aiGate<T>(task: () => Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const start = () => {
      aiActive++;
      task()
        .then(resolve, reject)
        .finally(() => {
          aiActive--;
          aiQueue.shift()?.();
        });
    };
    if (aiActive < AI_CONCURRENCY) start();
    else aiQueue.push(start);
  });
}

const _sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// POST an AI request through the gate, retrying transient 503s with backoff.
// Non-503 errors are terminal. Surfaces the backend {detail} on failure.
async function aiPost<T>(path: string, body: unknown): Promise<T> {
  return aiGate(async () => {
    const backoffs = [0, 700, 1800]; // attempt 1 immediate, then back off
    let lastDetail = "AI request failed";
    for (let attempt = 0; attempt < backoffs.length; attempt++) {
      if (backoffs[attempt]) await _sleep(backoffs[attempt]);
      const res = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) return res.json() as Promise<T>;
      let detail = `${res.status} ${res.statusText}`;
      try {
        const b = await res.json();
        if (b && typeof b.detail === "string") detail = b.detail;
      } catch {
        // not JSON
      }
      lastDetail = detail;
      if (res.status !== 503) throw new Error(detail); // only 503 is retryable
    }
    throw new Error(lastDetail);
  });
}

// POST a special-slide AI request (overview/conclusion/demographics).
function postAi<T>(materialId: string, kind: string, body: unknown): Promise<T> {
  return aiPost<T>(`/materials/${materialId}/ai/${kind}`, body);
}

// The fast preview path (render_title=false) reports the template's title box
// in response headers rather than the body, which is PNG bytes — see
// routes_questions.py and title_box_headers() in fast_preview.py. Absent
// headers (slow path, or a template with no title box) mean null: the same
// "draw nothing" fallback as a preview with no title today.
function readTitleMeta(headers: Headers): ChartPreviewTitleMeta | null {
  const raw = headers.get("X-Title-Box");
  if (!raw) return null;
  const box = raw.split(",").map(Number);
  if (box.length !== 4 || box.some((n) => Number.isNaN(n))) return null;
  const aspect = Number(headers.get("X-Slide-Aspect"));
  const sizePt = Number(headers.get("X-Title-Size-Pt"));
  if (!aspect || !sizePt) return null;
  const align = headers.get("X-Title-Align");
  return {
    box: box as [number, number, number, number],
    font: headers.get("X-Title-Font") ?? "",
    sizePt,
    color: headers.get("X-Title-Color") ?? "2B2B2B",
    align: align === "center" || align === "right" ? align : "left",
    caps: headers.get("X-Title-Caps") === "1",
    aspect,
  };
}

export interface GroupSpec {
  kind: "multi" | "battery";
  variables: string[];
  label?: string | null;
}

// A Tier-2 comparison: overlay these parallel questions (by qid) as multi-series.
// The chart type (radar / grouped bar) is chosen in the Design phase, not stored here.
export interface ComparisonSpec {
  members: string[];
  label?: string | null;
}

export interface GroupingOverride {
  groups: GroupSpec[];
  singles: string[];
  comparisons?: ComparisonSpec[];
}

// A confirmable hint: a run of ≥3 contiguous same-scale variables that could be a
// battery (stacked comparison). Surfaced by /regroup; never applied automatically.
export interface BatterySuggestion {
  variables: string[];
  labels: string[];
}

// Parallel questions sharing a category set — seeds the comparison suggestions.
export interface ParallelSuggestion {
  kind: "multi" | "battery";
  qids: string[];
  labels: string[];
}

export interface CaseMaterial {
  material_id: string;
  name: string;
}

export interface CaseReportInfo {
  report_id: string;
  name: string;
  /** True once a render has been stamped for this report's CURRENT content —
   *  the deliverable a viewer may download. A report with no render behind it
   *  is the analyst's working state, not a finished report. */
  rendered: boolean;
  /** When that render happened, ISO 8601. Empty on decks rendered before the
   *  backend recorded it — absence means "unknown", not "never". */
  rendered_at?: string;
  /** A render is in progress for this report right now (server-side state —
   *  see routes_render.is_render_active). A report can be `rendering` and
   *  `rendered` at once: a fresh render of an already-finished report. */
  rendering?: boolean;
  /** When it was last saved, and by whom. From the report's sidecar, so the
   *  whole list is one request — this replaced fetching every report in full
   *  just to count its charts, which is what made the page slow. */
  modified_at?: string;
  modified_by?: string;
  /** Who has it open in the editor right now, if anyone. `locked_by_me` is
   *  what stops your own second tab looking like somebody else's lock. */
  locked_by?: string;
  locked_by_name?: string;
  locked_since?: string;
  locked_by_me?: boolean;
}

export interface Template {
  id: string;
  name: string;
  size: number;
  layout_name: string;
  palette: string[];
  heading_font: string;
  warnings?: string[];
  /** Whether the render host can supply the fonts this template names. A
   *  template only NAMES its fonts; a missing one is substituted silently
   *  unless we say otherwise. */
  fonts?: TemplateFont[];
  fonts_ok?: boolean;
}

/** Everything the template settings dialog shows. Font status here is
 *  re-resolved server-side, so a substitution chosen a moment ago is
 *  already reflected. */
export interface TemplateDetail extends Template {
  body_font: string;
  fonts: TemplateFont[];
  available_fonts: string[];
}

export interface Substitutions {
  map: Record<string, string>;
  available: string[];
}

export interface TemplateFont {
  family: string;
  state: "present" | "installed" | "substituted" | "unavailable";
  /** What it actually renders as, when a stand-in was chosen. */
  substitute?: string;
  source: string;
  reason: string;
  ok: boolean;
}

/** Which template a report resolves to, and WHERE from — the level is what lets
 *  the UI say "inherited from the customer" instead of showing a bare id. */
export interface ResolvedTemplate {
  template_id: string;
  level: "report" | "pinned" | "case" | "customer" | "default";
  name: string;
}

export interface RecentReport {
  id: string;
  case_id: string;
  customer_id: string;
  name: string;
  modified_at: string;
}

export interface ResolvedCase {
  id: string;
  name: string;
  customer_id: string;
  customer_name: string;
  /** Template bound on the CASE itself; "" when inheriting. */
  template_id?: string;
  /** Whether the signed-in user may WRITE to this case (may_write on
   *  "{customer_id}/{id}"), computed server-side. A UI courtesy for hiding
   *  editor-only controls — every write route re-checks the same grant on
   *  its own, so this flag hiding a button is not what protects the data. */
  can_edit: boolean;
}

/** The user who created a customer — its one owner (see
 *  routes_customers.py's `list_customers`). `name` is already
 *  resolved server-side to a display name, falling back to the user's email
 *  only when they have never set one — never a raw email field here on
 *  purpose, since this rides on a route any signed-in user with access to
 *  the customer can call, not the admin-only user listing. */
export interface CustomerOwner {
  id: string;
  name: string;
}

export interface Customer {
  id: string;
  name: string;
  /** Template bound AT THIS LEVEL; "" when inheriting. */
  template_id?: string;
  /** Whether the signed-in user may WRITE to this customer (may_write on the
   *  customer id), computed server-side. Creating a study, uploading/binding
   *  a template, and renaming/deleting the customer are all writes gated by
   *  this — never by is_admin, which is a different right (managing users). */
  can_edit: boolean;
  /** How many studies this customer has. Report counts live on the STUDY
   *  (CustomerCase), not here — the customer list shows studies, and the
   *  reports under one of them are one click away. */
  case_count: number;
  /** Who created this customer. One person, fixed at creation — NOT everyone
   *  who can write to it. Null for customers created before ownership was
   *  recorded, and for those the UI says nothing rather than guessing. */
  owner: CustomerOwner | null;
}

/** A case now belongs to exactly one customer, so its id alone is no longer a
 *  complete address — every customer-scoped call carries both. */
export interface CustomerCase {
  id: string;
  customer_id: string;
  name: string;
  template_id?: string;
  /** Reports with a stamped render (ReportsSection.tsx's "Generated" badge,
   *  `ReportRef.rendered` in repository.py) — the deliverable a viewer can
   *  download. */
  completed_reports: number;
  /** Every other report in this study: "Draft" (has charts, no deck) and
   *  "Empty" (no charts, no deck) folded together, since neither is a
   *  deliverable — see routes_customers.py's `_report_stats`. */
  draft_reports: number;
}

const jsonPost = (body: unknown) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const jsonPut = (body: unknown) => ({
  method: "PUT",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const jsonPatch = (body: unknown) => ({
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  /** What this backend can do, and how much of it at once.
   *
   *  `render_concurrency` is the number of slides worth asking it to draw in
   *  parallel. Drawing is CPU-bound, so the server derives it from the cores
   *  it is actually scheduled on — the client cannot see that, and guessing
   *  high is the expensive mistake: it does not finish the deck any sooner and
   *  it multiplies the wait for the one slide the author is looking at. */
  health: (): Promise<{ status: string; render_concurrency?: number }> =>
    fetch(`${API_BASE}/health`).then((r) =>
      json<{ status: string; render_concurrency?: number }>(r)
    ),

  /** Asiakas -> Case. The server filters these lists to what the caller may
   *  see, so the UI must never widen them by filtering a broader response. */
  customers: {
    list: (): Promise<Customer[]> =>
      fetch(`${API_BASE}/customers`).then((r) => json<Customer[]>(r)),

    get: (customerId: string): Promise<Customer> =>
      fetch(`${API_BASE}/customers/${customerId}`).then((r) => json<Customer>(r)),

    /** Id and name ONLY, for any signed-in user regardless of grant — the
     *  narrow, deliberate exception to the 404-for-absence rule `get`
     *  above still follows. Exists for one reason: the no-access page
     *  (NoAccessCustomer.tsx) has to say WHICH customer it is refusing you,
     *  and `get` 404s before it can. Do not use this anywhere `get` would
     *  work instead. */
    /** Id and name for EVERY customer in the tenant, to any signed-in user.
     *  The sidebar lists customers you cannot open, so that a colleague can
     *  find one and ask for access — without it the request flow is
     *  unreachable. Same deliberate crack in the absence rule as `getName`,
     *  and the same limit: id and name, nothing else. */
    listNames: (): Promise<{ id: string; name: string }[]> =>
      fetch(`${API_BASE}/customers/names`).then((r) =>
        json<{ id: string; name: string }[]>(r)),

    getName: (customerId: string): Promise<{ id: string; name: string }> =>
      fetch(`${API_BASE}/customers/${customerId}/name`).then((r) =>
        json<{ id: string; name: string }>(r)
      ),

    create: (name: string): Promise<Customer> =>
      fetch(`${API_BASE}/customers`, jsonPost({ name })).then((r) => json<Customer>(r)),

    rename: (customerId: string, name: string): Promise<Customer> =>
      fetch(`${API_BASE}/customers/${customerId}`, jsonPatch({ name })).then((r) =>
        json<Customer>(r)
      ),

    listCases: (customerId: string): Promise<CustomerCase[]> =>
      fetch(`${API_BASE}/customers/${customerId}/cases`).then((r) =>
        json<CustomerCase[]>(r)
      ),

    createCase: (customerId: string, name: string): Promise<CustomerCase> =>
      fetch(`${API_BASE}/customers/${customerId}/cases`, jsonPost({ name })).then((r) =>
        json<CustomerCase>(r)
      ),

    /** A case id alone -> its name and owning customer. The URL surface is
     *  still case-rooted from before the hierarchy existed. */
    resolveCase: (caseId: string): Promise<ResolvedCase> =>
      fetch(`${API_BASE}/cases/${caseId}/resolve`).then((r) => json<ResolvedCase>(r)),

    recentReports: (limit = 10): Promise<RecentReport[]> =>
      fetch(`${API_BASE}/reports/recent?limit=${limit}`).then((r) =>
        json<RecentReport[]>(r)
      ),

    renameCase: (
      customerId: string,
      caseId: string,
      name: string
    ): Promise<CustomerCase> =>
      fetch(
        `${API_BASE}/customers/${customerId}/cases/${caseId}`,
        jsonPatch({ name })
      ).then((r) => json<CustomerCase>(r)),
  },

  templates: {
    list: (customerId: string): Promise<Template[]> =>
      fetch(`${API_BASE}/customers/${customerId}/templates`).then((r) =>
        json<Template[]>(r)
      ),

    upload: (customerId: string, file: File): Promise<Template> => {
      const form = new FormData();
      form.append("file", file);
      return fetch(`${API_BASE}/customers/${customerId}/templates`, {
        method: "POST",
        body: form,
      }).then((r) => json<Template>(r));
    },

    remove: (customerId: string, templateId: string): Promise<{ removed: number }> =>
      fetch(`${API_BASE}/customers/${customerId}/templates/${templateId}`, {
        method: "DELETE",
      }).then((r) => json<{ removed: number }>(r)),

    // null clears the binding, so the level above takes over again.
    bindCustomer: (customerId: string, templateId: string | null) =>
      fetch(`${API_BASE}/customers/${customerId}/template`, jsonPut({ template_id: templateId }))
        .then((r) => json<unknown>(r)),

    bindCase: (customerId: string, caseId: string, templateId: string | null) =>
      fetch(
        `${API_BASE}/customers/${customerId}/cases/${caseId}/template`,
        jsonPut({ template_id: templateId })
      ).then((r) => json<unknown>(r)),

    bindReport: (customerId: string, caseId: string, reportId: string,
                 templateId: string | null) =>
      fetch(
        `${API_BASE}/customers/${customerId}/cases/${caseId}/reports/${reportId}/template`,
        jsonPut({ template_id: templateId })
      ).then((r) => json<unknown>(r)),

    forReport: (customerId: string, caseId: string,
                reportId: string): Promise<ResolvedTemplate> =>
      fetch(
        `${API_BASE}/customers/${customerId}/cases/${caseId}/reports/${reportId}/template`
      ).then((r) => json<ResolvedTemplate>(r)),

    detail: (customerId: string, templateId: string): Promise<TemplateDetail> =>
      fetch(`${API_BASE}/customers/${customerId}/templates/${templateId}`)
        .then((r) => json<TemplateDetail>(r)),

    forCase: (customerId: string, caseId: string): Promise<ResolvedTemplate> =>
      fetch(`${API_BASE}/customers/${customerId}/cases/${caseId}/template`)
        .then((r) => json<ResolvedTemplate>(r)),

    /** "Päivitys pitää erikseen pyytää" — move a delivered report onto whatever
     *  its tutkimus or customer now specifies. */
    refreshReport: (customerId: string, caseId: string, reportId: string) =>
      fetch(
        `${API_BASE}/customers/${customerId}/cases/${caseId}/reports/${reportId}/template/refresh`,
        { method: "POST" }
      ).then((r) => json<ResolvedTemplate>(r)),
  },

  cases: {
    list: (): Promise<Case[]> =>
      fetch(`${API_BASE}/cases`).then((r) => json<Case[]>(r)),

    create: (name: string): Promise<{ case_id: string }> =>
      fetch(`${API_BASE}/cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }).then((r) => json<{ case_id: string }>(r)),

    rename: (caseId: string, name: string): Promise<{ id: string; name: string }> =>
      fetch(`${API_BASE}/cases/${caseId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }).then((r) => json<{ id: string; name: string }>(r)),

    remove: (caseId: string): Promise<{ deleted: string }> =>
      fetch(`${API_BASE}/cases/${caseId}`, { method: "DELETE" }).then((r) =>
        json<{ deleted: string }>(r)
      ),
  },

  // Plugin-declared chart-type catalog + config schema (material-independent).
  chartTypes: (): Promise<{ chart_types: ChartTypeInfo[] }> =>
    fetch(`${API_BASE}/chart-types`).then((r) =>
      json<{ chart_types: ChartTypeInfo[] }>(r)
    ),

  materials: {
    /** Throw away every rendered preview for this dataset.
     *
     *  The pictures are a cache and are normally invisible: the same chart,
     *  template and curation give the same PNG. This is for when they are not
     *  — a template edited in place, a font installed on the host, a slide
     *  that came out wrong for a reason nobody has found. Scoped to the
     *  material, so one study refreshing does not cost every other study its
     *  pictures. Returns how many entries went. */
    clearPreviewCache: (materialId: string): Promise<{ cleared: number }> =>
      fetch(`${API_BASE}/materials/${materialId}/preview-cache/clear`,
            { method: "POST" }).then((r) => json<{ cleared: number }>(r)),

    /** What must never reach an LLM from this dataset.
     *
     *  `proposed` is read from the study's own structure — the members of its
     *  batteries, the categories of its questions. `accepted` is null until
     *  somebody reviews them, and a report cannot be created before that. */
    sensitiveTerms: (materialId: string): Promise<SensitiveTerms> =>
      fetch(`${API_BASE}/materials/${materialId}/sensitive-terms`).then((r) =>
        json<SensitiveTerms>(r)
      ),

    /** Accept the terms. The server registers them with the data store FIRST
     *  and records the acceptance only if that succeeded — so a 503 here means
     *  nothing was accepted and nothing would be masked. */
    acceptSensitiveTerms: (
      materialId: string,
      terms: string[]
    ): Promise<SensitiveTerms> =>
      fetch(`${API_BASE}/materials/${materialId}/sensitive-terms`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ terms }),
      }).then((r) => json<SensitiveTerms>(r)),

    // How many groups each question would ACTUALLY show if split by this variable.
    // A battery whose members belong to one study arm reports 1, so the Compare
    // groups dialog can disable it instead of generating an unsplit slide.
    splitGroups: (
      materialId: string,
      classifyingVar: string,
      grouping?: GroupingOverride
    ): Promise<Record<string, number>> => {
      const p = new URLSearchParams({ classifying_var: classifyingVar });
      if (grouping) p.set("grouping", JSON.stringify(grouping));
      return fetch(`${API_BASE}/materials/${materialId}/split-groups?${p}`)
        .then((r) => json<{ groups: Record<string, number> }>(r))
        .then((d) => d.groups);
    },

    // Server-side list of a case's materials (visible to any user/device).
    listForCase: (caseId: string): Promise<{ materials: CaseMaterial[] }> =>
      fetch(`${API_BASE}/cases/${caseId}/materials`).then((r) =>
        json<{ materials: CaseMaterial[] }>(r)
      ),

    // What deleting this dataset would empty. Asked before the confirmation so
    // it can name the reports rather than count them.
    usage: (
      caseId: string,
      materialId: string
    ): Promise<{ reports: CaseReportInfo[] }> =>
      fetch(`${API_BASE}/cases/${caseId}/materials/${materialId}/usage`).then((r) =>
        json<{ reports: CaseReportInfo[] }>(r)
      ),

    remove: async (caseId: string, materialId: string): Promise<void> => {
      const res = await fetch(
        `${API_BASE}/cases/${caseId}/materials/${materialId}`,
        { method: "DELETE" }
      );
      if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
          const body = await res.json();
          // datahive gates a delete behind approval; say so rather than
          // showing the raw envelope.
          if (body?.detail?.error === "consent_required") {
            detail = body.detail.message;
          } else if (typeof body?.detail === "string") {
            detail = body.detail;
          }
        } catch {
          // not JSON — keep the status text
        }
        throw new Error(detail);
      }
    },

    upload: (caseId: string, file: File): Promise<UploadResult> => {
      const form = new FormData();
      form.append("file", file);
      return fetch(`${API_BASE}/cases/${caseId}/materials`, {
        method: "POST",
        body: form,
      }).then((r) => json<UploadResult>(r));
    },

    questions: (materialId: string): Promise<{ questions: Question[] }> =>
      fetch(`${API_BASE}/materials/${materialId}/questions`).then((r) =>
        json<{ questions: Question[] }>(r)
      ),

    variables: (
      materialId: string,
      opts?: { all?: boolean }
    ): Promise<{ variables: Variable[] }> =>
      fetch(
        `${API_BASE}/materials/${materialId}/variables${opts?.all ? "?include_all=true" : ""}`
      ).then((r) => json<{ variables: Variable[] }>(r)),

    // Stateless preview: reshape the question list for a report's grouping override
    // (the override itself is saved WITH the report, not per material).
    regroup: (
      materialId: string,
      override: GroupingOverride
    ): Promise<{
      questions: Question[];
      battery_suggestions: BatterySuggestion[];
      parallel_suggestions: ParallelSuggestion[];
    }> =>
      fetch(`${API_BASE}/materials/${materialId}/regroup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(override),
      }).then((r) =>
        json<{
          questions: Question[];
          battery_suggestions: BatterySuggestion[];
          parallel_suggestions: ParallelSuggestion[];
        }>(r)
      ),

    questionSummary: (
      materialId: string,
      qid: string,
      grouping?: GroupingOverride
    ): Promise<QuestionSummary> => {
      // Pass the report grouping so a battery/multi qid resolves (else the summary 404s).
      const qs = grouping
        ? `?grouping=${encodeURIComponent(JSON.stringify(grouping))}`
        : "";
      return fetch(
        `${API_BASE}/materials/${materialId}/questions/${qid}/summary${qs}`
      ).then((r) => json<QuestionSummary>(r));
    },

    // Word-cloud editing: the question's raw top words (+ current merges) and a
    // setter to persist merges (fold token variants into one word).
    questionWords: (
      materialId: string,
      qid: string
    ): Promise<{ words: { word: string; count: number }[]; merges: WordMerge[] }> =>
      fetch(`${API_BASE}/materials/${materialId}/questions/${qid}/words`).then((r) =>
        json<{ words: { word: string; count: number }[]; merges: WordMerge[] }>(r)
      ),

    setWordMerges: (
      materialId: string,
      qid: string,
      merges: WordMerge[]
    ): Promise<{ qid: string; merges: WordMerge[] }> =>
      fetch(`${API_BASE}/materials/${materialId}/questions/${qid}/word-merges`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ merges }),
      }).then((r) => json<{ qid: string; merges: WordMerge[] }>(r)),

    // Rename a question for this material (case-page edit). Blank reverts to the
    // original SAV label. Applies to every report/chart/deck using the question.
    setQuestionLabel: (
      materialId: string,
      qid: string,
      label: string
    ): Promise<{ qid: string; label: string | null }> =>
      fetch(`${API_BASE}/materials/${materialId}/questions/${qid}/label`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label }),
      }).then((r) => json<{ qid: string; label: string | null }>(r)),

    previewChart: (
      materialId: string,
      chart: ChartSpec,
      opts?: {
        renderTitle?: boolean;
        /** This is the slide the author is looking at: ask the backend for its
         *  reserved render slot. */
        priority?: boolean;
        /** The template to draw on: an id, or "" for "inherit from the case".
         *  Absent leaves the server to resolve it, which only the deck export
         *  should rely on. */
        templateRef?: string;
        grouping?: GroupingOverride;
        // Which report this preview belongs to, so the backend's
        // resolve_template can see ITS template choice (and any pin) rather
        // than only the material's tutkimus/asiakas/house default. See
        // _preview_template in routes_questions.py.
        reportId?: string;
      }
    ): Promise<{ blob: Blob; titleMeta: ChartPreviewTitleMeta | null }> => {
      // No gate here any more: previewQueue owns ordering and concurrency, so
      // that a slide's headline is written before its picture is drawn.
      return (async () => {
        // When renderTitle is false the PNG omits the baked title block, so the
        // frontend owns the title region (progressive preview overlay). The
        // report's grouping is included so a chart on a manually-grouped question
        // previews the same way it renders.
        const body: Record<string, unknown> = {
          ...chart,
          ...(opts?.renderTitle === undefined ? {} : { render_title: opts.renderTitle }),
          ...(opts?.grouping ? { grouping: opts.grouping } : {}),
          ...(opts?.reportId ? { report_id: opts.reportId } : {}),
          // WHICH template, said outright rather than looked up server-side.
          //
          // Choosing a template persists the choice and re-renders at the same
          // moment, and the render regularly won: the server had not stored the
          // binding yet, answered with the PREVIOUS template, and that picture
          // was cached under the new template's key. The deck then stayed on
          // the old template however long you waited, which is the bug that
          // outlasted every other fix. "" is not absent — it means "inherit
          // from the case or asiakas", the editor's "Use parent setting".
          ...(opts?.templateRef === undefined ? {} : { template_id: opts.templateRef }),
        };
        // The backend keeps a reserved soffice slot for the slide the author is
        // looking at. The queue promotes that slide to the head of one queue, so
        // it is already first here; the flag stays for the backend's own pool.
        const res = await fetch(
          `${API_BASE}/materials/${materialId}/preview-chart${opts?.priority ? "?priority=1" : ""}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        );
        if (!res.ok) {
          // Backend returns {detail: "<reason>"} for 422 (and 503 etc.)
          let detail = `${res.status} ${res.statusText}`;
          try {
            const body = await res.json();
            if (body && typeof body.detail === "string") detail = body.detail;
          } catch {
            // not JSON — keep status text
          }
          throw new Error(detail);
        }
        return { blob: await res.blob(), titleMeta: readTitleMeta(res.headers) };
      })();
    },

    // AI: generate a descriptive slide title. Goes through the shared AI gate
    // (bounded concurrency + 503 retry); surfaces the backend {detail} message.
    aiSlideTitle: (
      materialId: string,
      body: AiSlideTitleBody
    ): Promise<{ title: string; subtitle?: string }> =>
      aiPost(`/materials/${materialId}/ai/slide-title`, body),

    // AI: shorten category labels into [full, short] pairs. Through the shared
    // AI gate (bounded concurrency + 503 retry).
    aiShortLabels: (
      materialId: string,
      body: AiShortLabelsBody
    ): Promise<{ overrides: [string, string][] }> =>
      aiPost(`/materials/${materialId}/ai/short-labels`, body),

    // AI: special-slide bullet generators. All may 503 if egoHive is down.
    aiOverview: (
      materialId: string,
      body: { question_refs?: string[] }
    ): Promise<{ bullets: string[] }> =>
      postAi(materialId, "overview", body),

    aiConclusion: (
      materialId: string,
      body: { question_refs?: string[] }
    ): Promise<{ bullets: string[] }> =>
      postAi(materialId, "conclusion", body),

    aiDemographics: (
      materialId: string,
      body: { question_refs?: string[] }
    ): Promise<{
      bullets: string[];
      question_refs: string[];
      charts: { question_ref: string; chart_type: string }[];
    }> => postAi(materialId, "demographics", body),

    // AI: summarise an open-ended question's answers into key themes (bullets).
    /** Mark (or unmark) a variable as a classifying variable for this dataset.
     *  Anyone who may edit the material may mark: the analyst doing the work is
     *  the one who knows what the variable means. */
    markClassifier: (
      materialId: string,
      name: string,
      marked: boolean
    ): Promise<{ marked_classifiers: string[] }> =>
      fetch(`${API_BASE}/materials/${materialId}/classifiers`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, marked }),
      }).then((r) => json<{ marked_classifiers: string[] }>(r)),

    aiThemes: (
      materialId: string,
      body: { question_ref: string }
    ): Promise<{ bullets: string[] }> =>
      aiPost(`/materials/${materialId}/ai/themes`, body),

    // AI: chat with a data-aware assistant about this material's survey data.
    chat: (
      materialId: string,
      messages: { role: "user" | "assistant"; content: string }[]
    ): Promise<{ reply: string }> =>
      aiPost(`/materials/${materialId}/chat`, { messages }),
  },

  reports: {
    // Server-side list of a case's reports (visible to any user/device).
    listForCase: (caseId: string): Promise<{ reports: CaseReportInfo[] }> =>
      fetch(`${API_BASE}/cases/${caseId}/reports`).then((r) =>
        json<{ reports: CaseReportInfo[] }>(r)
      ),

    create: (
      caseId: string,
      report: ReportDoc
    ): Promise<{ report_id: string }> =>
      fetch(`${API_BASE}/cases/${caseId}/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(report),
      }).then((r) => json<{ report_id: string }>(r)),

    /** Take or renew the editing lock. Rejects with an ApiError carrying the
     *  status: 409 (and ONLY 409) means somebody else has it. Anything else is
     *  a failure to find out, which the caller must not confuse with a refusal
     *  — see lib/reportLock. */
    lock: async (caseId: string, reportId: string, tabId: string): Promise<{ mine: boolean; user_name: string; renew_seconds: number }> => {
      const res = await fetch(
        `${API_BASE}/cases/${caseId}/reports/${reportId}/lock?tab=${encodeURIComponent(tabId)}`,
        { method: "POST" }
      );
      if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
          const body = await res.json();
          if (typeof body?.detail === "string") detail = body.detail;
        } catch {
          /* not JSON */
        }
        throw new ApiError(res.status, detail);
      }
      return res.json();
    },

    /** Give the lock back. Uses keepalive so a closing tab still releases it —
     *  an ordinary fetch is cancelled when the page goes away, which would
     *  leave the report locked until it expired. */
    unlock: (caseId: string, reportId: string, tabId: string): Promise<void> =>
      fetch(
        `${API_BASE}/cases/${caseId}/reports/${reportId}/lock?tab=${encodeURIComponent(tabId)}`,
        { method: "DELETE", keepalive: true }
      ).then(() => undefined),

    /** Save a report.
     *
     *  Deliberately sends no If-Match. The server supports one — it records a
     *  version and refuses a save built on a copy somebody else has replaced —
     *  and this editor sending it caused far more harm than the window it
     *  closed. Binding a template writes the report doc, so the version moved
     *  under the open editor and its next autosave was refused; so did a second
     *  tab of the SAME person (which the lock deliberately allows), a save whose
     *  response was lost, and two autosaves overlapping on a slow deck. Every
     *  one of those ended with the editor closing and discarding unsaved work —
     *  the exact harm the check was added to prevent, made much likelier.
     *
     *  What guards concurrent editing is the LOCK. If this is revisited, the
     *  editor needs a single in-flight save, a version refreshed by every write
     *  path (template binding included), and a 409 that can be told apart from
     *  the lock's before any of it is worth switching on. */
    update: (
      caseId: string,
      reportId: string,
      report: ReportDoc
    ): Promise<{ report_id: string; version?: number }> =>
      fetch(`${API_BASE}/cases/${caseId}/reports/${reportId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(report),
      }).then((r) => json<{ report_id: string; version?: number }>(r)),

    get: (caseId: string, reportId: string): Promise<ReportDoc> =>
      fetch(`${API_BASE}/cases/${caseId}/reports/${reportId}`).then((r) =>
        json<ReportDoc>(r)
      ),

    // "Raportti voidaan kopioida uudeksi" — the copy lands under the SAME case
    // and carries every setting; only the name and the id differ. The backend
    // owns the copying (routes_reports.py), so nothing here re-derives a report.
    duplicate: (
      caseId: string,
      reportId: string,
      name: string
    ): Promise<{ report_id: string }> =>
      fetch(`${API_BASE}/cases/${caseId}/reports/${reportId}/duplicate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }).then((r) => json<{ report_id: string }>(r)),

    remove: (
      caseId: string,
      reportId: string
    ): Promise<{ deleted: boolean }> =>
      fetch(`${API_BASE}/cases/${caseId}/reports/${reportId}`, {
        method: "DELETE",
      }).then((r) => json<{ deleted: boolean }>(r)),

    // Run the full PPTX → PDF → raster render chain (slow). Surfaces the
    // backend's {detail} message (422 / 503) so the UI can show the reason.
    //
    // Runs to completion server-side regardless of this fetch: navigating
    // away or closing the tab does not stop it (see routes_render.py). The
    // only way to stop it is `cancelRender` below — there is no `signal`
    // here on purpose, an aborted fetch no longer cancels anything.
    render: async (
      caseId: string,
      reportId: string,
      materialId: string,
      view: "slides" = "slides"
    ): Promise<{ pdf_url: string; font_warnings?: string[] }> => {
      const res = await fetch(
        `${API_BASE}/cases/${caseId}/reports/${reportId}/render`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ material_id: materialId, view }),
        }
      );
      if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
          const body = await res.json();
          if (body && typeof body.detail === "string") detail = body.detail;
        } catch {
          // not JSON — keep status text
        }
        throw new Error(detail);
      }
      return res.json() as Promise<{ pdf_url: string; font_warnings?: string[] }>;
    },

    // The explicit stop: sets the same between-slides cancel flag a client
    // disconnect used to set. Never throws on "nothing was running" — the
    // body says whether this call actually stopped a render, so the caller
    // can tell without treating a race as an error.
    cancelRender: async (
      caseId: string,
      reportId: string
    ): Promise<{ cancelled: boolean }> => {
      const res = await fetch(
        `${API_BASE}/cases/${caseId}/reports/${reportId}/render/cancel`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return res.json() as Promise<{ cancelled: boolean }>;
    },

    // Whether a render is in progress for this report RIGHT NOW, per the
    // server — not per this browser tab's own state. What a returning visitor
    // (a reload, a different tab, a render nobody in this session started)
    // reads to tell "generating" apart from "not rendered".
    /** Report ids in this case with a render in progress. Answered from the
     *  server's own memory — no per-report storage reads — so the case page can
     *  keep a "Generating…" badge honest without re-fetching the whole list,
     *  which costs one read per report plus one per lock. */
    renderingInCase: async (caseId: string): Promise<{ rendering: string[] }> => {
      const res = await fetch(`${API_BASE}/cases/${caseId}/renders`, {
        cache: "no-store",
      });
      return json<{ rendering: string[] }>(res);
    },

    renderStatus: async (
      caseId: string,
      reportId: string
    ): Promise<{ rendering: boolean }> => {
      const res = await fetch(
        `${API_BASE}/cases/${caseId}/reports/${reportId}/render/status`,
        { cache: "no-store" }
      );
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return res.json() as Promise<{ rendering: boolean }>;
    },

    // `no-store`: the URL is fixed but the file changes with every render, and a
    // cached copy is indistinguishable from "the render did nothing".
    previewPdf: async (caseId: string, reportId: string): Promise<Blob> => {
      const res = await fetch(
        `${API_BASE}/cases/${caseId}/reports/${reportId}/preview.pdf`,
        { cache: "no-store" }
      );
      if (!res.ok) {
        throw new Error(`${res.status} ${res.statusText}`);
      }
      return res.blob();
    },

    previewPptx: async (caseId: string, reportId: string): Promise<Blob> => {
      const res = await fetch(
        `${API_BASE}/cases/${caseId}/reports/${reportId}/preview.pptx`,
        { cache: "no-store" }
      );
      if (!res.ok) {
        throw new Error(`${res.status} ${res.statusText}`);
      }
      return res.blob();
    },
  },

  settings: {
    substitutions: (): Promise<Substitutions> =>
      fetch(`${API_BASE}/settings/font-substitutions`).then((r) =>
        json<Substitutions>(r)
      ),

    setSubstitutions: async (map: Record<string, string>): Promise<Substitutions> => {
      const res = await fetch(`${API_BASE}/settings/font-substitutions`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ map }),
      });
      if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
          const body = await res.json();
          if (typeof body?.detail === "string") detail = body.detail;
        } catch {
          // not JSON — keep status text
        }
        throw new Error(detail);
      }
      return res.json() as Promise<Substitutions>;
    },

    chartFont: (): Promise<ChartFontSettings> =>
      fetch(`${API_BASE}/settings/chart-font`).then((r) =>
        json<ChartFontSettings>(r)
      ),

    setChartFont: async (family: string): Promise<ChartFontSettings> => {
      const res = await fetch(`${API_BASE}/settings/chart-font`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ family }),
      });
      if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
          const body = await res.json();
          if (typeof body?.detail === "string") detail = body.detail;
        } catch {
          // not JSON — keep status text
        }
        throw new Error(detail);
      }
      return res.json() as Promise<ChartFontSettings>;
    },

    /** The template every report renders on when nothing above it binds one. */
    defaultTemplate: (): Promise<DefaultTemplateState> =>
      fetch(`${API_BASE}/settings/default-template`).then((r) =>
        json<DefaultTemplateState>(r)
      ),

    uploadDefaultTemplate: async (file: File): Promise<DefaultTemplateState> => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/settings/default-template`, {
        method: "PUT",
        body: form,
      });
      if (!res.ok) {
        // The body carries WHY the template was refused — "no layout with a
        // large content placeholder" is the whole value of the check.
        let detail = `${res.status} ${res.statusText}`;
        try {
          const body = await res.json();
          if (typeof body?.detail === "string") detail = body.detail;
        } catch {
          // not JSON — keep status text
        }
        throw new Error(detail);
      }
      return res.json() as Promise<DefaultTemplateState>;
    },

    restoreDefaultTemplate: (): Promise<DefaultTemplateState> =>
      fetch(`${API_BASE}/settings/default-template`, { method: "DELETE" }).then((r) =>
        json<DefaultTemplateState>(r)
      ),

    fonts: (): Promise<FontsSettings> =>
      fetch(`${API_BASE}/settings/fonts`).then((r) => json<FontsSettings>(r)),

    uploadFont: async (file: File): Promise<InstalledFont> => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/settings/fonts`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        // The body carries WHY — "this is a WOFF, not a .ttf" is the whole
        // value of the check, so it must not be flattened to a status code.
        let detail = `${res.status} ${res.statusText}`;
        try {
          const body = await res.json();
          if (typeof body?.detail === "string") detail = body.detail;
        } catch {
          // not JSON — keep status text
        }
        throw new Error(detail);
      }
      return res.json() as Promise<InstalledFont>;
    },

    deleteFont: async (fontId: string): Promise<void> => {
      const res = await fetch(`${API_BASE}/settings/fonts/${fontId}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
          const body = await res.json();
          // datahive's consent gate: a 409 carries an approval envelope, and
          // the request id is what the user needs in order to approve.
          if (body?.detail?.error === "consent_required") {
            detail = `${body.detail.message} (${body.detail.request_id})`;
          } else if (typeof body?.detail === "string") {
            detail = body.detail;
          }
        } catch {
          // not JSON — keep status text
        }
        throw new Error(detail);
      }
    },

    workspace: (): Promise<Record<string, WorkspaceCaseState>> =>
      fetch(`${API_BASE}/settings/workspace`).then((r) =>
        json<Record<string, WorkspaceCaseState>>(r)
      ),

    setCaseWorkspace: (
      caseId: string,
      state: WorkspaceCaseState
    ): Promise<WorkspaceCaseState> =>
      fetch(`${API_BASE}/settings/workspace/${caseId}`, jsonPut(state)).then((r) =>
        json<WorkspaceCaseState>(r)
      ),
  },

  users: {
    list: (): Promise<StudioUser[]> =>
      fetch(`${API_BASE}/users`).then((r) => json<StudioUser[]>(r)),

    /** Every customer in the tenant, id and name only -- admin-only, and
     *  deliberately NOT grant-filtered (backend: routes_users.py's
     *  list_grantable_customers). Feeds the grant picker on this screen so
     *  an admin with no grants yet -- every bootstrap admin -- has
     *  something to pick from. Never use this for anything that reads a
     *  customer's data; that path stays on `api.customers.list`. */
    listGrantableCustomers: (): Promise<Customer[]> =>
      fetch(`${API_BASE}/users/customers`).then((r) => json<Customer[]>(r)),

    setGrants: (userId: string, grants: UserGrantInput[]): Promise<StudioUser> =>
      fetch(`${API_BASE}/users/${userId}/grants`, jsonPut({ grants })).then((r) => detailedJson<StudioUser>(r)),

    setAdmin: (userId: string, isAdmin: boolean): Promise<StudioUser> =>
      fetch(`${API_BASE}/users/${userId}`, jsonPatch({ is_admin: isAdmin })).then((r) => detailedJson<StudioUser>(r)),

    remove: (userId: string): Promise<void> =>
      fetch(`${API_BASE}/users/${userId}`, { method: "DELETE" }).then(detailedVoid),

    invite: (email: string, grants: UserGrantInput[]): Promise<InvitationResult> =>
      fetch(`${API_BASE}/users/invite`, jsonPost({ email, grants })).then((r) => detailedJson<InvitationResult>(r)),

    listInvites: (): Promise<Invite[]> =>
      fetch(`${API_BASE}/invites`).then((r) => json<Invite[]>(r)),

    revokeInvite: (inviteId: string): Promise<void> =>
      fetch(`${API_BASE}/invites/${inviteId}`, { method: "DELETE" }).then(detailedVoid),
  },

  /** The "Request access"/"Request permissions" buttons on the customer
   *  page, and the admin-or-owner queue that acts on them (Settings >
   *  Permission requests, its own tab — see routes_access_requests.py). */
  /** Somebody a provider has vouched for who has no account here yet.
   *
   *  Reached with a signup TICKET rather than a session — see
   *  routes_signup_requests.py. `me` answers the whole page state in one call
   *  so the request page never has to infer it from the shape of an error. */
  /** Your own account. No id anywhere — the server writes `current_user`'s
   *  record, which is what keeps this a profile route rather than a second
   *  way to edit an account. */
  profile: {
    update: (firstName: string, lastName: string): Promise<Me> =>
      fetch(`${API_BASE}/auth/me`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ first_name: firstName, last_name: lastName }),
      }).then((r) => detailedJson<Me>(r)),
  },

  /** The segment labels this question splits into under a classifier — the two
   *  a scatter plots against each other. From the computed series, not the
   *  variable's value labels, so a group nobody falls into is never offered. */
  segments: (materialId: string, qid: string, classifyingVar: string,
             grouping?: GroupingOverride): Promise<{ segments: string[] }> => {
    const q = new URLSearchParams({ classifying_var: classifyingVar });
    if (grouping && Object.keys(grouping).length) q.set("grouping", JSON.stringify(grouping));
    return fetch(
      `${API_BASE}/materials/${materialId}/questions/${encodeURIComponent(qid)}/segments?${q}`
    ).then((r) => json<{ segments: string[] }>(r));
  },

  /** Which classifier groups a one-panel-per-group chart would actually draw.
   *  Answered by the server because the choice depends on each group's base —
   *  and because `render/panels.py` is the one place that decides it, so the
   *  warning and the slide cannot disagree about what was dropped. */
  panels: (materialId: string, qid: string, classifyingVar: string,
           grouping?: GroupingOverride): Promise<PanelSelection> => {
    const q = new URLSearchParams({ classifying_var: classifyingVar });
    if (grouping && Object.keys(grouping).length) q.set("grouping", JSON.stringify(grouping));
    return fetch(
      `${API_BASE}/materials/${materialId}/questions/${encodeURIComponent(qid)}/panels?${q}`
    ).then((r) => json<PanelSelection>(r));
  },

  signup: {
    me: (): Promise<SignupTicket> =>
      fetch(`${API_BASE}/signup/me`).then((r) => json<SignupTicket>(r)),

    request: (): Promise<SignupRequest> =>
      fetch(`${API_BASE}/signup-requests`, { method: "POST" }).then((r) =>
        detailedJson<SignupRequest>(r)
      ),

    /** Waiting askers, newest first — admin-only. Approved ones have become
     *  accounts and appear on the Users screen; refused ones are gone. */
    pending: (): Promise<SignupRequest[]> =>
      fetch(`${API_BASE}/signup-requests`).then((r) => json<SignupRequest[]>(r)),

    approve: (requestId: string, grants: UserGrantInput[]): Promise<SignupApproval> =>
      fetch(`${API_BASE}/signup-requests/${requestId}/approve`,
            jsonPost({ grants })).then((r) => detailedJson<SignupApproval>(r)),

    refuse: (requestId: string): Promise<void> =>
      fetch(`${API_BASE}/signup-requests/${requestId}`, { method: "DELETE" }).then(
        (r) => {
          if (!r.ok) throw new ApiError(r.status, "Could not remove the request");
        }
      ),
  },

  accessRequests: {
    create: (customerId: string, mode: AccessMode): Promise<AccessRequest> =>
      fetch(`${API_BASE}/access-requests`,
           jsonPost({ customer_id: customerId, mode })).then((r) => detailedJson<AccessRequest>(r)),

    /** Only the signed-in caller's own requests — what the no-access page
     *  checks to show "you already asked" instead of the button again. */
    mine: (): Promise<AccessRequest[]> =>
      fetch(`${API_BASE}/access-requests/mine`).then((r) => json<AccessRequest[]>(r)),

    /** Every request, newest first — admin-only. */
    list: (): Promise<AccessRequest[]> =>
      fetch(`${API_BASE}/access-requests`).then((r) => json<AccessRequest[]>(r)),

    approve: (requestId: string): Promise<AccessRequest> =>
      fetch(`${API_BASE}/access-requests/${requestId}/approve`, { method: "POST" }).then((r) =>
        detailedJson<AccessRequest>(r)
      ),

    refuse: (requestId: string): Promise<AccessRequest> =>
      fetch(`${API_BASE}/access-requests/${requestId}/refuse`, { method: "POST" }).then((r) =>
        detailedJson<AccessRequest>(r)
      ),
  },

  /** Settings > Backup. Both admin-only: the archive carries every password
   *  hash and the session signing key, and restoring one rewrites the store. */
  backup: {
    /** The whole store as a zip: settings, users, customers, studies, the
     *  uploaded SAVs, report definitions, templates and fonts. Rendered decks
     *  are left out — they are regenerated from what IS in there.
     *
     *  Downloaded through fetch rather than a plain link so a failure (a 403,
     *  a server error) surfaces as an error instead of navigating the tab to
     *  a JSON error page. */
    download: async (): Promise<{ blob: Blob; filename: string }> => {
      const res = await fetch(`${API_BASE}/admin/backup`);
      // Reuse the shared failure path (server `detail` over a bare status
      // line); it only returns on success, which cannot happen here.
      if (!res.ok) await detailedVoid(res);
      const disposition = res.headers.get("content-disposition") ?? "";
      const match = /filename="?([^";]+)"?/.exec(disposition);
      return { blob: await res.blob(), filename: match?.[1] ?? "nsight-backup.zip" };
    },

    /** Write a backup's objects back. Overwrites what is at the same path and
     *  leaves anything not in the backup alone. */
    restore: (file: File): Promise<RestoreResult> => {
      const form = new FormData();
      form.append("file", file);
      return fetch(`${API_BASE}/admin/restore`, { method: "POST", body: form }).then(
        (r) => detailedJson<RestoreResult>(r)
      );
    },
  },
};

export interface RestoreResult {
  /** How many objects were written. */
  restored: number;
  total_bytes: number;
  /** Objects that could not be restored, one line each. Empty on a clean
   *  restore — a backup with problems still restores everything else. */
  problems: string[];
}

export interface InstalledFont {
  id: string;
  family: string;
  filename: string;
  size: number;
  on_host: boolean;
}

/** A font family a template names that this host cannot supply, and whose
 *  decks are affected — what an admin needs in order to know what to upload. */
export interface MissingFont {
  family: string;
  reason: string;
  templates: string[];
}

/** The chart font is independent of the template's: brand faces are often too
 *  wide for the long category labels charts are mostly made of. */
export interface ChartFontSettings {
  /** "" means no choice made, so the house default applies. */
  family: string;
  /** What charts actually draw with — differs from `family` if it fell back. */
  effective: string;
  default: string;
  available: string[];
}

export interface DefaultTemplateState {
  /** True while the tenant is still on the deck nSight builds for itself. */
  is_builtin: boolean;
  name: string;
  uploaded_at: string;
  size: number;
  warnings?: string[];
}

export interface FontsSettings {
  fonts: InstalledFont[];
  missing: MissingFont[];
}

/** One entry in a case's report list -- what `workspace.ts` used to keep in
 *  localStorage, now round-tripped through `/settings/workspace` (spec §8). */
export interface WorkspaceReport {
  id: string;
  name: string;
  materialId?: string;
  createdAt?: string;
}

export interface WorkspaceCaseState {
  materialId: string | null;
  reports: WorkspaceReport[];
}

export interface UserGrantInput {
  scope: string;
  mode: "view" | "edit";
}

export interface UserGrant extends UserGrantInput {
  customer_name: string | null;
  case_name: string | null;
}

export interface StudioUser {
  /** ISO-8601, or null for never — which is what a pending invitation looks
   *  like now that inviting creates the account. */
  last_login_at?: string | null;
  id: string;
  email: string;
  name: string;
  is_admin: boolean;
  grants: UserGrant[];
}

export interface Invite {
  id: string;
  email: string;
  invited_by: string;
  invited_at: string;
  expires: string;
  status: "pending" | "accepted" | "expired";
  grants: UserGrantInput[];
}

export interface InvitationResult extends Invite {
  link: string;
  emailed: boolean;
}

export type AccessMode = "view" | "edit";

/** A signed-in user's ask for access to a customer they cannot see — the
 *  record behind the no-access page's "Request access" button (backend:
 *  reportbuilder.store.repository.AccessRequest). */
/** What the signup ticket asserts, plus the two facts that decide what the
 *  request page says. Answered in one call so the page never infers a state
 *  from an error code. */
/** What a pie/doughnut/funnel would actually draw, and what it would leave out.
 *  `thin` and `capped` are separate because they mean different things to a
 *  reader: a thin group could not be reported at all, a capped one fits the data
 *  but not the page. */
export interface PanelSelection {
  drawn: string[];
  thin: string[];
  capped: string[];
  degraded: boolean;
  /** False when the chart is not split into panels at all — one ordinary pie. */
  split: boolean;
  max_panels: number;
}

export interface SignupTicket {
  email: string;
  provider: string;
  name: string;
  /** They were invited while holding this ticket — the answer is "sign in". */
  has_account: boolean;
  /** They already asked; nobody has decided yet. */
  pending: boolean;
}

export interface SignupRequest {
  id: string;
  email: string;
  provider: string;
  name: string;
  requested_at: string;
  state: "pending" | "approved" | "refused";
  decided_by: string | null;
  decided_at: string | null;
}

/** Approval reports whether the invitation mail actually went out: the asker
 *  was told to expect one, so an admin without SMTP has to know they must say
 *  so themselves. */
export interface SignupApproval extends SignupRequest {
  emailed: boolean;
  link: string;
}

export interface AccessRequest {
  id: string;
  user_id: string;
  user_email: string;
  customer_id: string;
  customer_name: string | null;
  mode: AccessMode;
  requested_at: string;
  state: "pending" | "granted" | "refused";
  decided_by: string | null;
  decided_at: string | null;
}
