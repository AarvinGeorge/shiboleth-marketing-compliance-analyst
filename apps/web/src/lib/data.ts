// meta: data access layer for the four MVP1 surfaces, now API-backed via
// TanStack Query against the M4 FastAPI service (src/lib/api.ts). Surfaces
// import ONLY from here. REAL data from the API: product list, TurboTax
// product + properties, scores (draft/verified/per_property/needs_review),
// all flags with verdicts (evidence_quote, reason, confidence), cluster ids
// and labels, dispositions. DOCUMENTED FIXTURE-FALLBACKS (API does not carry
// these yet):
//   1. Hero metric strip (U2): portfolio-level metrics + intent tooltips are
//      the DESIGN.md demo dataset; no /metrics endpoint exists yet.
//   2. Demo product cards QuickBooks Money (clear, 93) and Credit Karma Money
//      (checking) incl. their sparklines: DESIGN.md Demo Dataset; they are
//      shown only for ids the API does not return.
//   3. Rule verbatim text: no rules endpoint; rendered from fixtures, which
//      are byte-for-byte doc 05 §1 (same text the DB is seeded with).
//   4. Evidence panel text: no materials endpoint; the panel highlights the
//      API-served evidence_quote itself and shows the API-served reason.
//   5. Why-flagged chain: GET /products/{id} does not expose the run id, so
//      /runs/{id}/events.json is unreachable from flag context; the compact
//      static chain is used, with the REAL checker reason as the expandable
//      verdict step. getRunEventsApi plumbing exists for when run_id lands.
//   6. Checker model name: not exposed; shown as the configured policy model.
//   7. U6 metric row card 4: coverage is not computed by M4, so the slot
//      shows the REAL needs_review_count instead of the delta's Coverage
//      card (deviation documented in the lane report).
// Also hosts the deterministic client-side property extraction for U3 chips.

"use client";

import { useEffect, useMemo } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  useQueries,
} from "@tanstack/react-query";
import {
  ApiError,
  getProductDetailApi,
  getProductsApi,
  postCheck,
  postDisposition,
  type ApiFlag,
  type ApiProductDetail,
  type ApiProductListItem,
} from "@/lib/api";
import {
  heroMetrics,
  products as demoProducts,
  rules,
  type ClusterFixture,
  type FlagMeta,
  type MetricFixture,
  type ProductSummary,
} from "@/lib/fixtures";
import { useFlagStore, type FlagLifecycle } from "@/lib/flag-store";
import type {
  BinaryCheck,
  Flag,
  FlagState,
  IntersectionTag,
  Material,
  Property,
  PropertyKind,
  Rule,
  Severity,
} from "@/lib/types";

export interface FlagView {
  flag: Flag;
  material: Material;
  property: Property;
  cluster: ClusterFixture;
  rule: Rule;
  check: BinaryCheck;
  meta: FlagMeta;
}

// mirrors apps/api routes/flags.py SEVERITY_BY_RULE (client display copy)
const SEVERITY_BY_RULE: Record<string, Severity> = {
  "R-01": "High",
  "R-02": "High",
  "R-03": "Medium",
  "R-04": "Medium",
};
const POLICY_MODEL = "Groq Llama 3.3"; // model policy default; not in API yet

const TAG_LABEL: Record<IntersectionTag, string> = {
  all_good: "All good",
  drifted_but_compliant: "Drifted but compliant",
  approved_but_non_compliant: "Approved but non-compliant",
  unapproved_violation: "Unapproved violation",
};
const TAG_RANK: Record<IntersectionTag, number> = {
  unapproved_violation: 0,
  approved_but_non_compliant: 1,
  drifted_but_compliant: 2,
  all_good: 3,
};

function ruleIdOf(checkId: string): string {
  // "R-03-REQ" -> "R-03"
  const m = checkId.match(/^(R-\d\d)/);
  return m ? m[1] : checkId;
}

function severityOf(checkId: string): Severity {
  return SEVERITY_BY_RULE[ruleIdOf(checkId)] ?? "Medium";
}

function coerceTag(tag: ApiFlag["verdicts"]["intersection_tag"]): IntersectionTag {
  return tag === "na" ? "all_good" : tag;
}

function firstSentence(text: string): string {
  const idx = text.indexOf(". ");
  return idx > 0 ? text.slice(0, idx + 1) : text;
}

function shortHandle(kind: PropertyKind, urlOrHandle: string): string {
  const bare = urlOrHandle.replace(/^https?:\/\//, "").replace(/\/$/, "");
  if (kind === "instagram") return `@${bare.split("/").pop()}`;
  if (kind === "facebook") return bare.split("/").pop() ?? bare;
  return bare;
}

// ---------------------------------------------------------------------------
// Query hooks
// ---------------------------------------------------------------------------

export function useProductsQuery() {
  return useQuery({ queryKey: ["products"], queryFn: getProductsApi });
}

export function useProductDetailQuery(id: string | null) {
  return useQuery({
    queryKey: ["product", id],
    queryFn: () => getProductDetailApi(id as string),
    enabled: id !== null,
    retry: (count, err) =>
      !(err instanceof ApiError && err.status === 404) && count < 1,
  });
}

/** Product list for U1 sidebar, U2 dashboard, U3 modal: API products first
 *  (real), then DESIGN.md demo cards for ids the API does not return. */
export function useProducts(): {
  products: ProductSummary[];
  isLoading: boolean;
  apiDown: boolean;
} {
  const list = useProductsQuery();
  const apiItems = useMemo(() => list.data ?? [], [list.data]);
  const details = useQueries({
    queries: apiItems.map((p) => ({
      queryKey: ["product", p.id],
      queryFn: () => getProductDetailApi(p.id),
      staleTime: 30_000,
    })),
  });
  const lifecycles = useFlagStore((s) => s.lifecycles);

  const products = useMemo(() => {
    const real = apiItems.map((item, i) =>
      toProductSummary(item, details[i]?.data, lifecycles)
    );
    const apiIds = new Set(apiItems.map((p) => p.id));
    const demo = demoProducts.filter((p) => !apiIds.has(p.id));
    return [...real, ...demo];
  }, [apiItems, details, lifecycles]);

  return {
    products,
    isLoading: list.isLoading,
    apiDown: list.isError,
  };
}

function toProductSummary(
  item: ApiProductListItem,
  detail: ApiProductDetail | undefined,
  lifecycles: Record<string, FlagLifecycle>
): ProductSummary {
  const flags = detail?.flags ?? [];
  const openCount = flags.filter(
    (f) => (lifecycles[f.id]?.state ?? f.state) === "open"
  ).length;
  const clusterCount = new Set(
    flags.map((f) => f.cluster_id ?? "unclustered")
  ).size;
  const verified = item.scores?.verified ?? null;
  return {
    id: item.id,
    name: item.name,
    status: flags.length === 0 ? "clear" : openCount > 0 ? "flagged" : "clear",
    verifiedScore: verified,
    scoreTrend: [], // no run-history endpoint yet; sparkline omitted
    openFlagCount: openCount,
    note: detail
      ? `${flags.length} flags in ${clusterCount} clusters from the latest corpus run.`
      : "",
    coverage: (detail?.properties ?? []).map((p) => ({
      kind: p.kind,
      label: shortHandle(p.kind, p.url_or_handle),
    })),
    assignmentNote: null,
    lastChecked: item.last_run_status
      ? `Last run ${item.last_run_status}`
      : null,
    checking: null,
  };
}

export interface ProductView {
  summary: ProductSummary | undefined;
  metrics: MetricFixture[];
  clusters: ClusterFixture[];
  views: FlagView[];
  isLoading: boolean;
  apiDown: boolean;
}

/** U6/U7 source: the API product detail joined into FlagViews, with the
 *  lifecycle overlay from the flag store (optimistic dispositions). Demo
 *  products (404 from the API) fall back to their fixture summaries. */
export function useProductView(productId: string): ProductView {
  const q = useProductDetailQuery(productId);
  const lifecycles = useFlagStore((s) => s.lifecycles);
  const seed = useFlagStore((s) => s.seed);

  // Seed lifecycle store from server flags (server is truth on load).
  useEffect(() => {
    if (!q.data) return;
    const entries: Record<string, FlagLifecycle> = {};
    for (const f of q.data.flags) {
      entries[f.id] = {
        state: f.state as FlagState,
        team: f.assigned_team,
        note: f.note,
      };
    }
    seed(entries);
  }, [q.data, seed]);

  return useMemo(() => {
    const notFound = q.error instanceof ApiError && q.error.status === 404;
    if (q.data) {
      const built = buildProductView(q.data, lifecycles);
      return { ...built, isLoading: false, apiDown: false };
    }
    const demo = demoProducts.find((p) => p.id === productId);
    return {
      summary: notFound || q.isError ? demo : undefined,
      metrics: [],
      clusters: [],
      views: [],
      isLoading: q.isLoading,
      apiDown: q.isError && !notFound,
    };
  }, [q.data, q.error, q.isError, q.isLoading, productId, lifecycles]);
}

function buildProductView(
  detail: ApiProductDetail,
  lifecycles: Record<string, FlagLifecycle>
): Omit<ProductView, "isLoading" | "apiDown"> {
  const websiteProp =
    detail.properties.find((p) => p.kind === "website") ??
    detail.properties[0];
  const property: Property = websiteProp
    ? { ...websiteProp }
    : { id: "unknown", kind: "website", url_or_handle: "unknown", config: {} };

  const views = detail.flags.map((f) => toFlagView(f, property));

  // clusters: group by cluster_id, ordered by size desc, unclustered last
  const groups = new Map<string, FlagView[]>();
  for (const v of views) {
    const key = v.flag.cluster_id ?? "unclustered";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(v);
  }
  const clusters: ClusterFixture[] = [...groups.entries()]
    .sort((a, b) => {
      if (a[0] === "unclustered") return 1;
      if (b[0] === "unclustered") return -1;
      return b[1].length - a[1].length;
    })
    .map(([key, members]) => {
      const first = members[0];
      const apiLabel =
        key === "unclustered"
          ? "Not yet clustered"
          : detail.flags.find((f) => f.cluster_id === key)?.cluster_label ??
            "Cluster";
      const ruleIds = [
        ...new Set(members.map((v) => ruleIdOf(v.flag.check_id))),
      ].join(", ");
      const dominant = members
        .map((v) => v.flag.verdicts.intersection_tag)
        .sort((a, b) => TAG_RANK[a] - TAG_RANK[b])[0];
      return {
        id: key,
        productId: detail.product.id,
        label: apiLabel,
        sourceLine: `${ruleIds} · ${members.length} ${members.length === 1 ? "flag" : "flags"}`,
        dominantTag: dominant ?? first.flag.verdicts.intersection_tag,
        flagIds: members.map((v) => v.flag.id),
      };
    });

  const summary = toProductSummary(
    {
      id: detail.product.id,
      name: detail.product.name,
      status: detail.product.status,
      scores: detail.scores,
      last_run_status: null,
    },
    detail,
    lifecycles
  );
  summary.lastChecked = "Latest corpus run";

  return {
    summary,
    metrics: buildMetrics(detail, lifecycles),
    clusters,
    views,
  };
}

function toFlagView(f: ApiFlag, property: Property): FlagView {
  const tag = coerceTag(f.verdicts.intersection_tag);
  const ruleId = ruleIdOf(f.verdicts.check_id);
  const rule: Rule = rules.find((r) => r.id === ruleId) ?? {
    id: ruleId,
    verbatim_text: "",
    severity: severityOf(f.verdicts.check_id),
    position: 0,
  };
  const isRequirement = !/TRG$/i.test(f.verdicts.check_id);
  const check: BinaryCheck = {
    id: f.verdicts.check_id,
    rule_id: ruleId,
    kind: isRequirement ? "requirement" : "trigger",
    text: "",
    evidence_criteria: "",
    library_entry_id: ruleId === "R-01" && isRequirement ? "D-01" : null,
  };
  const axisA = f.verdicts.axis_a === true;
  const flag: Flag = {
    id: f.id,
    run_id: "latest",
    material_id: f.material_id,
    check_id: f.verdicts.check_id,
    state: f.state as FlagState,
    assigned_team: f.assigned_team,
    note: f.note,
    modality: "text",
    media_ref: null,
    cluster_id: f.cluster_id ?? "unclustered",
    verdicts: {
      material_id: f.material_id ?? f.id,
      check_id: f.verdicts.check_id,
      trigger_met: true,
      requirement_met: axisA,
      axis_a: axisA,
      axis_b: f.verdicts.axis_b,
      intersection_tag: tag,
      evidence_quote: f.verdicts.evidence_quote,
      location: f.location,
      reason: f.verdicts.reason,
      confidence: f.verdicts.confidence,
    },
  };
  const material: Material = {
    id: f.material_id ?? f.id,
    property_id: property.id,
    ref: f.location,
    kind: "page",
    modality: "text",
    media_ref: null,
    content_hash: "",
    // no materials endpoint: the API-served evidence quote IS the panel text
    extracted_text: f.verdicts.evidence_quote,
    fetched_at: "",
  };
  const meta: FlagMeta = {
    flagId: f.id,
    title: f.cluster_label ?? TAG_LABEL[tag],
    explainer: firstSentence(f.verdicts.reason),
    severity: severityOf(f.verdicts.check_id),
    foundAt: "latest corpus run",
    model: POLICY_MODEL,
    missingRequirement: null,
    postDate: null,
    chain: [
      { title: `Crawled · ${f.location} ingested from the corpus snapshot` },
      { title: `Extracted · marketing copy from ${f.location}` },
      { title: `Trigger check · ${ruleId} trigger matched` },
      {
        title: `Requirement check · ${f.verdicts.check_id} evaluated against the material`,
      },
      {
        title: `Verdict · ${TAG_LABEL[tag]} at ${f.verdicts.confidence.toFixed(2)} confidence · ${POLICY_MODEL}`,
        detail: f.verdicts.reason,
      },
    ],
  };
  const cluster: ClusterFixture = {
    id: f.cluster_id ?? "unclustered",
    productId: "",
    label: f.cluster_label ?? "Not yet clustered",
    sourceLine: "",
    dominantTag: tag,
    flagIds: [],
  };
  return { flag, material, property, cluster, rule, check, meta };
}

function buildMetrics(
  detail: ApiProductDetail,
  lifecycles: Record<string, FlagLifecycle>
): MetricFixture[] {
  const stateOf = (f: ApiFlag): FlagState =>
    (lifecycles[f.id]?.state ?? f.state) as FlagState;
  const flags = detail.flags;
  const open = flags.filter((f) => stateOf(f) === "open");
  const openViolations = open.filter((f) => f.verdicts.axis_a === false);
  const highOpen = openViolations.filter(
    (f) => severityOf(f.verdicts.check_id) === "High"
  ).length;
  const dispositioned = flags.length - open.length;
  const draft = detail.scores?.draft;
  const verified = detail.scores?.verified;
  const needsReview = detail.scores?.needs_review_count ?? 0;

  return [
    {
      id: "verified-score",
      label: "Verified score",
      intent: "Are we getting safer or riskier overall?",
      value: verified === null || verified === undefined ? "–" : String(verified),
      sublabel: [
        {
          text: `draft ${draft ?? "–"} · ${dispositioned} of ${flags.length} dispositioned`,
        },
      ],
    },
    {
      id: "open-violations",
      label: "Open violations",
      intent: "What's exposed right now and how long has it festered?",
      value: String(openViolations.length),
      sublabel: [
        { text: `${highOpen} high`, tone: "danger" },
        { text: " · latest corpus run" },
      ],
    },
    {
      id: "awaiting-triage",
      label: "Awaiting triage",
      intent: "Is the review queue under control?",
      value: String(open.length),
      sublabel: [{ text: `of ${flags.length} flags` }],
    },
    {
      id: "needs-review",
      label: "Needs review",
      intent:
        "How much did the checker decline to decide? Excluded from the score.",
      value: String(needsReview),
      sublabel: [{ text: "excluded from the denominator" }],
    },
  ];
}

/** U7: one flag joined for detail, from the same product query. */
export function useFlagView(
  productId: string,
  flagId: string
): { view: FlagView | undefined; isLoading: boolean } {
  const pv = useProductView(productId);
  return {
    view: pv.views.find((v) => v.flag.id === flagId),
    isLoading: pv.isLoading,
  };
}

// ---------------------------------------------------------------------------
// Disposition mutation: optimistic via the flag store, reconciled with the
// server's {flag, scores}; 409 reverts and surfaces an inline error.
// ---------------------------------------------------------------------------

export interface DispositionInput {
  flagId: string;
  action: "confirm" | "dismiss";
  team?: string;
  note?: string;
}

export function useDisposition(productId: string) {
  const queryClient = useQueryClient();
  const setLifecycle = useFlagStore((s) => s.setLifecycle);
  const setError = useFlagStore((s) => s.setError);

  return useMutation({
    mutationFn: ({ flagId, ...body }: DispositionInput) =>
      postDisposition(flagId, body),
    onMutate: async (input) => {
      const previous = useFlagStore.getState().lifecycles[input.flagId];
      setError(input.flagId, null);
      setLifecycle(input.flagId, {
        state:
          input.action === "dismiss"
            ? "dismissed"
            : input.team
              ? "assigned"
              : "confirmed",
        team: input.team ?? null,
        note: input.note ?? null,
      });
      return { previous };
    },
    onSuccess: (result, input) => {
      setLifecycle(input.flagId, {
        state: result.flag.state as FlagState,
        team: result.flag.assigned_team,
        note: result.flag.note,
      });
      // fold the recomputed scores + flag state into the cached detail
      queryClient.setQueryData<ApiProductDetail>(
        ["product", productId],
        (old) =>
          old
            ? {
                ...old,
                scores: { ...old.scores, ...result.scores },
                flags: old.flags.map((f) =>
                  f.id === result.flag.id
                    ? {
                        ...f,
                        state: result.flag.state,
                        assigned_team: result.flag.assigned_team,
                        note: result.flag.note,
                      }
                    : f
                ),
              }
            : old
      );
    },
    onError: (err, input, context) => {
      if (context?.previous) {
        setLifecycle(input.flagId, context.previous);
      }
      const message =
        err instanceof ApiError
          ? err.status === 409
            ? `Not allowed: ${err.detail}`
            : err.detail
          : "The API is unreachable.";
      setError(input.flagId, message);
    },
  });
}

/** U3 submit: corpus check for an API-backed product. */
export function useStartCheck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (productId: string) => postCheck(productId),
    onSuccess: (_res, productId) => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      queryClient.invalidateQueries({ queryKey: ["product", productId] });
    },
  });
}

// ---------------------------------------------------------------------------
// Fixture-only reads that remain (documented in the header)
// ---------------------------------------------------------------------------

export function getHeroMetrics(): MetricFixture[] {
  return heroMetrics;
}

// ---------------------------------------------------------------------------
// U3 live chips: deterministic extraction of typed properties from freeform
// text (client-side stand-in for GET /extract-properties until M6 live mode).
// ---------------------------------------------------------------------------

export interface ExtractedProperty {
  kind: PropertyKind;
  label: string;
}

export function extractPropertiesFromText(text: string): ExtractedProperty[] {
  const found: ExtractedProperty[] = [];
  const seen = new Set<string>();
  const push = (kind: PropertyKind, label: string) => {
    const key = `${kind}:${label.toLowerCase()}`;
    if (!seen.has(key)) {
      seen.add(key);
      found.push({ kind, label });
    }
  };

  for (const m of text.matchAll(/instagram\.com\/([A-Za-z0-9._]+)/gi)) {
    push("instagram", `@${m[1]}`);
  }
  for (const m of text.matchAll(/(?<![A-Za-z0-9.])@([A-Za-z0-9._]{2,})/g)) {
    push("instagram", `@${m[1]}`);
  }
  for (const m of text.matchAll(/facebook\.com\/([A-Za-z0-9.]+)/gi)) {
    push("facebook", m[1]);
  }
  for (const m of text.matchAll(
    /(?:https?:\/\/)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:\/[^\s]*)?/gi
  )) {
    const host = m[1].toLowerCase();
    if (host.includes("instagram.com") || host.includes("facebook.com")) {
      continue;
    }
    push("website", host);
  }
  const order: PropertyKind[] = ["website", "instagram", "facebook"];
  return found.sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind));
}
