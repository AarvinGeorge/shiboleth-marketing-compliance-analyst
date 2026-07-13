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

export interface ApiProductDetail {
  product: { id: string; name: string; status: string };
  properties: ApiProperty[];
  scores: ApiScores | null;
  flags: ApiFlag[];
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

export function postSkipProperty(
  runId: string,
  body: { property_id: string; text?: string }
): Promise<{ run_id: string; status: string }> {
  return fetchJson<{ run_id: string; status: string }>(
    `/runs/${runId}/skip-property`,
    { method: "POST", body: JSON.stringify(body) }
  );
}
