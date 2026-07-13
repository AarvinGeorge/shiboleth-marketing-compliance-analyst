// meta: typed fetch client for the FastAPI service (01_spec §6). Base URL from
// NEXT_PUBLIC_API_URL (default http://localhost:8000). Response types mirror
// apps/api/src/shiboleth/api/routes/{products,flags,runs,metrics}.py exactly;
// ApiError carries the HTTP status so callers can branch on 409 (illegal
// lifecycle transition / duplicate product name). No presentation logic here;
// that lives in data.ts.

import type { IntersectionTag, PropertyKind } from "@/lib/types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

// --- response shapes (mirror the route files 1:1) --------------------------

export interface ApiScores {
  draft: number | null;
  verified: number | null;
  per_property?: Record<string, number>;
  needs_review_count?: number;
  // live runs carry these; property_status maps propertyId -> fetched |
  // needs_input | skipped, config carries the crawl cap for progress.
  property_status?: Record<string, string>;
  config?: { depth?: number; cap?: number };
  // coverage.properties maps propertyId -> fetched | skipped for the run;
  // drives the card's channel chips (what was actually analyzed).
  coverage?: { properties?: Record<string, string> };
}

export interface ApiProductListItem {
  id: string;
  name: string;
  status: string;
  scores: ApiScores | null;
  run_id: string | null;
  last_run_status: string | null;
}

// GET /metrics: each hero KPI. value=null is an honest empty state (render
// the sublabel, never a fabricated number). trend is present only on the
// portfolio score and drives its sparkline (empty array = no sparkline).
export interface ApiMetric {
  value: string | number | null;
  sublabel: string;
  intent: string;
  trend?: number[];
}

export interface ApiMetrics {
  portfolio_score: ApiMetric;
  open_violations: ApiMetric;
  triage: ApiMetric;
  coverage: ApiMetric;
  caught: ApiMetric;
}

export interface ApiVerdicts {
  check_id: string;
  axis_a: boolean | null;
  axis_b: boolean | null;
  intersection_tag: IntersectionTag | "na";
  evidence_quote: string;
  reason: string;
  confidence: number;
}

export interface ApiFlag {
  id: string;
  state: string;
  assigned_team: string | null;
  note: string | null;
  cluster_id: string | null;
  cluster_label: string | null;
  material_id: string | null;
  location: string;
  source_url: string | null; // materials.ref, clean per-page URL for the source link
  verdicts: ApiVerdicts;
}

export interface ApiProperty {
  id: string;
  kind: PropertyKind;
  url_or_handle: string;
  config: Record<string, unknown>;
}

// Cluster rows of the latest run (additive, clustering C2). kind="wording" =
// deterministic exact-wording clusters; kind="issue" = AI-suggested parents
// grouping wording clusters into one analyst decision. member_cluster_ids is
// present only on issue parents (from member_snapshot).
export interface ApiCluster {
  id: string;
  label: string;
  kind: "wording" | "issue";
  state: "auto" | "suggested" | "confirmed" | "rejected";
  rationale: string | null;
  parent_cluster_id: string | null;
  member_cluster_ids?: string[];
}

export interface ApiProductDetail {
  product: { id: string; name: string; status: string };
  properties: ApiProperty[];
  scores: ApiScores | null;
  flags: ApiFlag[];
  clusters?: ApiCluster[]; // optional: older payloads lack it
  run_id?: string | null;
  model_config?: { check?: string } | null;
}

export interface ApiDispositionResult {
  flag: {
    id: string;
    state: string;
    assigned_team: string | null;
    note: string | null;
  };
  scores: ApiScores;
}

export interface ApiEvent {
  event_id: string;
  type: string;
  node: string | null;
  flag_id: string | null;
  ts: string;
  payload: Record<string, unknown>;
}

// --- calls ------------------------------------------------------------------

export function getProductsApi(): Promise<ApiProductListItem[]> {
  return fetchJson<ApiProductListItem[]>("/products");
}

export function getProductDetailApi(id: string): Promise<ApiProductDetail> {
  return fetchJson<ApiProductDetail>(`/products/${id}`);
}

export function postDisposition(
  flagId: string,
  body: { action: "confirm" | "dismiss"; team?: string; note?: string }
): Promise<ApiDispositionResult> {
  return fetchJson<ApiDispositionResult>(`/flags/${flagId}/disposition`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getRunEventsApi(runId: string): Promise<ApiEvent[]> {
  return fetchJson<ApiEvent[]>(`/runs/${runId}/events.json`);
}

export function getMetricsApi(): Promise<ApiMetrics> {
  return fetchJson<ApiMetrics>("/metrics");
}

export interface NewPropertyInput {
  kind: PropertyKind;
  url_or_handle: string;
  config?: Record<string, unknown>;
}

export function postCreateProduct(body: {
  name: string;
  properties: NewPropertyInput[];
}): Promise<{ id: string; name: string }> {
  return fetchJson<{ id: string; name: string }>("/products", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function postCheck(
  productId: string,
  mode: "live" | "corpus" = "live"
): Promise<{ run_id: string; status?: string }> {
  return fetchJson<{ run_id: string; status?: string }>("/checks", {
    method: "POST",
    body: JSON.stringify({ product_id: productId, mode }),
  });
}

export function postPasteContent(
  runId: string,
  body: { property_id: string; text: string }
): Promise<{ run_id: string; status: string }> {
  return fetchJson<{ run_id: string; status: string }>(
    `/runs/${runId}/paste-content`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

// POST /runs/{run_id}/issue-suggestions (clustering C2). Idempotent on the
// API side: already-parented clusters and rejected snapshots are skipped, so
// an empty array means "no new groupings", never an error.
export interface ApiIssueSuggestion {
  id: string;
  label: string;
  state: string;
  rationale: string;
  member_cluster_ids: string[];
  signatures: string[];
}

export function postIssueSuggestions(
  runId: string
): Promise<ApiIssueSuggestion[]> {
  return fetchJson<ApiIssueSuggestion[]>(`/runs/${runId}/issue-suggestions`, {
    method: "POST",
  });
}

// PATCH /clusters/{id}/issue-state: rejected = ungroup (detaches children),
// suggested = undo the ungroup (re-attaches snapshot members still
// unparented), confirmed = keep.
export function patchIssueState(
  clusterId: string,
  state: "confirmed" | "rejected" | "suggested"
): Promise<{ id: string; state: string }> {
  return fetchJson<{ id: string; state: string }>(
    `/clusters/${clusterId}/issue-state`,
    { method: "PATCH", body: JSON.stringify({ state }) }
  );
}

export function postSkipProperty(
  runId: string,
  body: { property_id: string; text?: string }
): Promise<{ run_id: string; status: string }> {
  return fetchJson<{ run_id: string; status: string }>(
    `/runs/${runId}/skip-property`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

// --- scorecard (customize layer) --------------------------------------------
// Mirrors routes/scorecard.py. verbatim_text is canonical: stored and served
// exactly as entered, only ever transformed at render time (<RuleText/>).
// DELETE returns 409 with a detail message when flags reference the rule or
// check (audit rows are never orphaned); surface that detail to the analyst.

export interface ApiBinaryCheck {
  id: string;
  kind: "trigger" | "requirement";
  text: string;
  evidence_criteria: string;
  library_entry_id: string | null;
}

export interface ApiScorecardRule {
  id: string;
  verbatim_text: string;
  severity: string;
  position: number;
  retrieval_keywords: { primary?: string[]; broad?: string[] };
  seeded: boolean;
  flag_count: number;
  checks: ApiBinaryCheck[];
}

export function getScorecardApi(): Promise<ApiScorecardRule[]> {
  return fetchJson<ApiScorecardRule[]>("/scorecard");
}

/** Auto-decomposes + derives keywords server-side (LLM call, ~5-10s). */
export function postScorecardRule(body: {
  verbatim_text: string;
  severity: string;
}): Promise<ApiScorecardRule> {
  return fetchJson<ApiScorecardRule>("/scorecard/rules", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function patchScorecardRule(
  ruleId: string,
  body: { verbatim_text?: string; severity?: string; regenerate?: boolean }
): Promise<ApiScorecardRule> {
  return fetchJson<ApiScorecardRule>(`/scorecard/rules/${ruleId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteScorecardRule(
  ruleId: string
): Promise<{ deleted: string }> {
  return fetchJson<{ deleted: string }>(`/scorecard/rules/${ruleId}`, {
    method: "DELETE",
  });
}

export interface CheckUpsertInput {
  kind: "trigger" | "requirement";
  text: string;
  evidence_criteria: string;
}

export function postScorecardCheck(
  ruleId: string,
  body: CheckUpsertInput
): Promise<ApiBinaryCheck> {
  return fetchJson<ApiBinaryCheck>(`/scorecard/rules/${ruleId}/checks`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function patchScorecardCheck(
  checkId: string,
  body: CheckUpsertInput
): Promise<ApiBinaryCheck> {
  return fetchJson<ApiBinaryCheck>(`/scorecard/checks/${checkId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteScorecardCheck(
  checkId: string
): Promise<{ deleted: string }> {
  return fetchJson<{ deleted: string }>(`/scorecard/checks/${checkId}`, {
    method: "DELETE",
  });
}
