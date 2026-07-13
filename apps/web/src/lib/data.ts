// meta: data access layer for the four surfaces, fully API-backed via TanStack
// Query. Surfaces import ONLY from here. Every visible number comes from the
// API: hero KPIs (GET /metrics), products + live run status + progress
// (GET /products, GET /products/{id}, GET /runs/{id}/events.json), flags with
// verdicts, dispositions, live-run create/paste/skip. There is NO runtime
// fixture data left; the only fixture import is the scorecard rule text (no
// rules endpoint yet, byte-for-byte doc 05 §1) surfaced on U7.
// Representation-only fallbacks (not fabricated numbers): card titles + the
// four U6 metric labels are UI copy; the checker model name falls back to an
// "unattributed" label for runs recorded before model attribution landed.

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
  getMetricsApi,
  getProductDetailApi,
  getProductsApi,
  getRunEventsApi,
  postCheck,
  postCreateProduct,
  postDisposition,
  postPasteContent,
  postSkipProperty,
  type ApiFlag,
  type ApiMetric,
  type ApiProductDetail,
  type ApiProductListItem,
  type NewPropertyInput,
} from "@/lib/api";
import {
  rules,
  type ClusterFixture,
  type FlagMeta,
  type MetricFixture,
  type ParkedProperty,
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

const ACTIVE_STATUSES = new Set(["running", "awaiting_input"]);
const POLL_MS = 2000;

// mirrors apps/api routes/*.py SEVERITY_BY_RULE (client display copy)
const SEVERITY_BY_RULE: Record<string, Severity> = {
  "R-01": "High",
  "R-02": "High",
  "R-03": "Medium",
  "R-04": "Medium",
};
// Real checker model comes from the run's model_config (API); this label is
// the last-resort fallback for runs recorded before attribution landed.
const POLICY_MODEL_FALLBACK = "unattributed (pre-attribution run)";
export function modelLabel(detail?: {
  model_config?: { check?: string } | null;
}): string {
  const raw = detail?.model_config?.check;
  if (!raw) return POLICY_MODEL_FALLBACK;
  const name = raw.split(":").pop() ?? raw;
  return name
    .replace("claude-haiku-4-5", "Claude Haiku 4.5")
    .replace("llama-3.3-70b-versatile", "Groq Llama 3.3 70B");
}

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
  if (kind === "instagram")
    return bare.startsWith("@") ? bare : `@${bare.split("/").pop()}`;
  if (kind === "facebook") return bare.split("/").pop() ?? bare;
  return bare;
}

// ---------------------------------------------------------------------------
// Hero metrics (GET /metrics)
// ---------------------------------------------------------------------------

export interface HeroMetric {
  id: string;
  label: string;
  intent: string;
  value: string | null; // null = honest empty state (render sublabel only)
  sublabel: string;
  trend: number[] | null;
}

// Card titles are UI copy; every number + sublabel + intent is the API's.
const HERO_ORDER: { key: keyof ApiMetricsShape; label: string }[] = [
  { key: "portfolio_score", label: "Verified portfolio score" },
  { key: "open_violations", label: "Open violations" },
  { key: "triage", label: "Awaiting triage" },
  { key: "coverage", label: "Coverage 24h" },
  { key: "caught", label: "Caught this week" },
];
type ApiMetricsShape = {
  portfolio_score: ApiMetric;
  open_violations: ApiMetric;
  triage: ApiMetric;
  coverage: ApiMetric;
  caught: ApiMetric;
};

export function useMetrics(active = false): {
  metrics: HeroMetric[];
  isLoading: boolean;
} {
  const q = useQuery({
    queryKey: ["metrics"],
    queryFn: getMetricsApi,
    refetchInterval: active ? POLL_MS : false,
  });
  const metrics = useMemo<HeroMetric[]>(() => {
    if (!q.data) return [];
    return HERO_ORDER.map(({ key, label }) => {
      const m = q.data[key];
      return {
        id: key,
        label,
        intent: m.intent,
        value: m.value === null ? null : String(m.value),
        sublabel: m.sublabel,
        trend: m.trend && m.trend.length > 0 ? m.trend : null,
      };
    });
  }, [q.data]);
  return { metrics, isLoading: q.isLoading };
}

// ---------------------------------------------------------------------------
// Product queries
// ---------------------------------------------------------------------------

export function useProductsQuery() {
  return useQuery({
    queryKey: ["products"],
    queryFn: getProductsApi,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((p) =>
        ACTIVE_STATUSES.has(p.last_run_status ?? "")
      )
        ? POLL_MS
        : false,
  });
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

/** Dashboard + sidebar product list: ONLY GET /products results, joined with
 *  each product's detail (properties, live property_status) and, for active
 *  runs, the run's material_fetched event count for real progress. */
export function useProducts(): {
  products: ProductSummary[];
  isLoading: boolean;
  apiDown: boolean;
  hasActiveRun: boolean;
} {
  const list = useProductsQuery();
  const apiItems = useMemo(() => list.data ?? [], [list.data]);
  const lifecycles = useFlagStore((s) => s.lifecycles);

  const details = useQueries({
    queries: apiItems.map((p) => ({
      queryKey: ["product", p.id],
      queryFn: () => getProductDetailApi(p.id),
      staleTime: 5_000,
      refetchInterval: ACTIVE_STATUSES.has(p.last_run_status ?? "")
        ? POLL_MS
        : false,
    })),
  });

  // material_fetched progress only for products whose run is active
  const activeItems = apiItems.filter(
    (p) => p.run_id && ACTIVE_STATUSES.has(p.last_run_status ?? "")
  );
  const events = useQueries({
    queries: activeItems.map((p) => ({
      queryKey: ["run-events", p.run_id],
      queryFn: () => getRunEventsApi(p.run_id as string),
      refetchInterval: POLL_MS,
    })),
  });
  const fetchedByRun = useMemo(() => {
    const map = new Map<string, number>();
    activeItems.forEach((p, i) => {
      const evs = events[i]?.data ?? [];
      map.set(
        p.run_id as string,
        evs.filter((e) => e.type === "material_fetched").length
      );
    });
    return map;
  }, [activeItems, events]);

  const products = useMemo(
    () =>
      apiItems.map((item, i) =>
        buildSummary(
          item,
          details[i]?.data,
          lifecycles,
          item.run_id ? fetchedByRun.get(item.run_id) ?? 0 : 0
        )
      ),
    [apiItems, details, lifecycles, fetchedByRun]
  );

  return {
    products,
    isLoading: list.isLoading,
    apiDown: list.isError,
    hasActiveRun: apiItems.some((p) =>
      ACTIVE_STATUSES.has(p.last_run_status ?? "")
    ),
  };
}

function buildSummary(
  item: ApiProductListItem,
  detail: ApiProductDetail | undefined,
  lifecycles: Record<string, FlagLifecycle>,
  fetched: number
): ProductSummary {
  const status = item.last_run_status ?? "";
  const flags = detail?.flags ?? [];
  const openCount = flags.filter(
    (f) => (lifecycles[f.id]?.state ?? f.state) === "open"
  ).length;
  const clusterCount = new Set(
    flags.filter((f) => f.cluster_id !== null).map((f) => f.cluster_id)
  ).size;

  const propStatus = detail?.scores?.property_status ?? {};
  const parked: ParkedProperty[] = (detail?.properties ?? [])
    .filter((p) => propStatus[p.id] === "needs_input")
    .map((p) => ({
      id: p.id,
      kind: p.kind,
      label: shortHandle(p.kind, p.url_or_handle),
    }));

  let uiStatus: ProductSummary["status"];
  if (status === "running") uiStatus = "running";
  else if (status === "awaiting_input") uiStatus = "awaiting_input";
  else uiStatus = openCount > 0 ? "flagged" : "clear";

  let note = "";
  if (uiStatus === "running") note = "Live check in progress.";
  else if (uiStatus === "awaiting_input")
    note = `Waiting on content for ${parked.length} ${parked.length === 1 ? "property" : "properties"}.`;
  else if (detail)
    note = `${flags.length} flags in ${clusterCount} ${clusterCount === 1 ? "cluster" : "clusters"} from the latest run.`;

  return {
    id: item.id,
    name: item.name,
    status: uiStatus,
    verifiedScore: item.scores?.verified ?? null,
    openFlagCount: openCount,
    note,
    // chips reflect what the LATEST RUN actually covered (fetched), not the
    // product's static channel config: a website-only run (socials skipped)
    // shows only the website chip. Fall back to all properties when a run has
    // no coverage map (legacy runs).
    coverage: (() => {
      const covered = detail?.scores?.coverage?.properties;
      const props = detail?.properties ?? [];
      const shown = covered
        ? props.filter((p) => covered[p.id] === "fetched")
        : props;
      return shown.map((p) => ({
        kind: p.kind,
        label: shortHandle(p.kind, p.url_or_handle),
      }));
    })(),
    lastChecked:
      uiStatus === "flagged" || uiStatus === "clear" ? "Latest run" : null,
    runId: item.run_id,
    progress:
      uiStatus === "running"
        ? { fetched, cap: detail?.scores?.config?.cap ?? 20 }
        : null,
    parked,
  };
}

// ---------------------------------------------------------------------------
// U6 / U7 product view
// ---------------------------------------------------------------------------

export interface ProductView {
  summary: ProductSummary | undefined;
  metrics: MetricFixture[];
  clusters: ClusterFixture[];
  views: FlagView[];
  isLoading: boolean;
  apiDown: boolean;
  notFound: boolean;
}

export function useProductView(productId: string): ProductView {
  const q = useProductDetailQuery(productId);
  const lifecycles = useFlagStore((s) => s.lifecycles);
  const seed = useFlagStore((s) => s.seed);

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
      return {
        ...built,
        isLoading: false,
        apiDown: false,
        notFound: false,
      };
    }
    return {
      summary: undefined,
      metrics: [],
      clusters: [],
      views: [],
      isLoading: q.isLoading,
      apiDown: q.isError && !notFound,
      notFound,
    };
  }, [q.data, q.error, q.isError, q.isLoading, lifecycles]);
}

function buildProductView(
  detail: ApiProductDetail,
  lifecycles: Record<string, FlagLifecycle>
): Pick<ProductView, "summary" | "metrics" | "clusters" | "views"> {
  const propById = new Map(detail.properties.map((p) => [p.id, p]));
  const websiteProp =
    detail.properties.find((p) => p.kind === "website") ??
    detail.properties[0];
  const fallbackProperty: Property = websiteProp
    ? { ...websiteProp }
    : { id: "unknown", kind: "website", url_or_handle: "unknown", config: {} };

  const model = modelLabel(detail);
  const views = detail.flags.map((f) => {
    const prop = (f.material_id && propById.get(f.material_id)) || fallbackProperty;
    return toFlagView(f, prop, model);
  });

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
        dominantTag: dominant ?? members[0].flag.verdicts.intersection_tag,
        flagIds: members.map((v) => v.flag.id),
      };
    });

  const summary = buildSummary(
    {
      id: detail.product.id,
      name: detail.product.name,
      status: detail.product.status,
      scores: detail.scores,
      run_id: detail.run_id ?? null,
      last_run_status: null, // detail is the completed-run surface
    },
    detail,
    lifecycles,
    0
  );

  return { summary, metrics: buildMetrics(detail, lifecycles), clusters, views };
}

function toFlagView(f: ApiFlag, property: Property, model: string): FlagView {
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
  // materials.ref (source_url) is the clean per-page URL; f.location is a
  // display string that may be a corpus page id, so prefer the real URL.
  const sourceUrl =
    f.source_url && /^https?:\/\//.test(f.source_url) ? f.source_url : null;
  const material: Material = {
    id: f.material_id ?? f.id,
    property_id: property.id,
    ref: f.source_url ?? f.location,
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
    foundAt: "latest run",
    model,
    missingRequirement: null,
    postDate: null,
    sourceUrl,
    chain: [
      { title: `Ingested · ${f.location}` },
      { title: `Extracted · marketing copy from ${f.location}` },
      { title: `Trigger check · ${ruleId} trigger matched` },
      {
        title: `Requirement check · ${f.verdicts.check_id} evaluated against the material`,
      },
      {
        title: `Verdict · ${TAG_LABEL[tag]} at ${f.verdicts.confidence.toFixed(2)} confidence · ${model}`,
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
      value:
        verified === null || verified === undefined ? "" : String(verified),
      sublabel: [
        {
          text: `draft ${draft ?? "-"} · ${dispositioned} of ${flags.length} dispositioned`,
        },
      ],
    },
    {
      id: "open-violations",
      label: "Open violations",
      intent: "What is exposed right now and how long has it festered?",
      value: String(openViolations.length),
      sublabel: [
        { text: `${highOpen} high`, tone: "danger" },
        { text: " · latest run" },
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
// Disposition mutation
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
      queryClient.invalidateQueries({ queryKey: ["metrics"] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
    onError: (err, input, context) => {
      if (context?.previous) setLifecycle(input.flagId, context.previous);
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

// ---------------------------------------------------------------------------
// New-check flows (live) + paste/skip
// ---------------------------------------------------------------------------

/** Live check for an existing product. */
export function useStartCheck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (productId: string) => postCheck(productId, "live"),
    onSuccess: (_res, productId) => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      queryClient.invalidateQueries({ queryKey: ["product", productId] });
      queryClient.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
}

/** Create a product from the modal chips, then start a live check on it. */
export function useCreateProductAndCheck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      name: string;
      properties: NewPropertyInput[];
    }) => {
      const created = await postCreateProduct(input);
      const run = await postCheck(created.id, "live");
      return { id: created.id, run_id: run.run_id };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      queryClient.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
}

/** Paste content / skip for a parked property on a running-but-parked run. */
export function useResolveProperty(productId: string, runId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["products"] });
    queryClient.invalidateQueries({ queryKey: ["product", productId] });
    queryClient.invalidateQueries({ queryKey: ["run-events", runId] });
    queryClient.invalidateQueries({ queryKey: ["metrics"] });
  };
  const paste = useMutation({
    mutationFn: (body: { property_id: string; text: string }) =>
      postPasteContent(runId, body),
    onSuccess: invalidate,
  });
  const skip = useMutation({
    mutationFn: (body: { property_id: string; text?: string }) =>
      postSkipProperty(runId, body),
    onSuccess: invalidate,
  });
  return { paste, skip };
}

// ---------------------------------------------------------------------------
// U3 chip extraction (client-side stand-in for GET /extract-properties)
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

/** Map extracted chips to the POST /products property shape. */
export function chipsToProperties(
  chips: ExtractedProperty[]
): NewPropertyInput[] {
  return chips.map((c) => {
    if (c.kind === "website") {
      const host = c.label.replace(/^https?:\/\//, "");
      return { kind: "website", url_or_handle: `https://${host}`, config: {} };
    }
    if (c.kind === "instagram") {
      return {
        kind: "instagram",
        url_or_handle: `instagram.com/${c.label.replace(/^@/, "")}`,
        config: {},
      };
    }
    return {
      kind: "facebook",
      url_or_handle: `facebook.com/${c.label.replace(/^@/, "")}`,
      config: {},
    };
  });
}
