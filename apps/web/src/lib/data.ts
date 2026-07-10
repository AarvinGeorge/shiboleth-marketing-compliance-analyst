// meta: data access layer for the four MVP1 surfaces. The ONLY module surfaces
// import data from; today it reads src/lib/fixtures.ts, at M4 these functions
// become fetches against the FastAPI endpoints (01_spec §6) without touching
// any surface. Also hosts the deterministic client-side property extraction
// that simulates U3's live chips in fixture mode (zero LLM, zero network).

import {
  checks,
  clusters,
  flagMeta,
  flags,
  heroMetrics,
  materials,
  productMetrics,
  products,
  properties,
  rules,
  TURBOTAX_ID,
  type ClusterFixture,
  type FlagMeta,
  type MetricFixture,
  type ProductSummary,
} from "@/lib/fixtures";
import type {
  BinaryCheck,
  Flag,
  Material,
  Property,
  PropertyKind,
  Rule,
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

export function getProducts(): ProductSummary[] {
  return products;
}

export function getProduct(id: string): ProductSummary | undefined {
  return products.find((p) => p.id === id);
}

export function getHeroMetrics(): MetricFixture[] {
  return heroMetrics;
}

export function getProductMetrics(productId: string): MetricFixture[] {
  return productMetrics[productId] ?? [];
}

export function getClusters(productId: string): ClusterFixture[] {
  return clusters.filter((c) => c.productId === productId);
}

export function getFlags(productId: string): Flag[] {
  // Fixture mode: flags exist for the TurboTax run only.
  return productId === TURBOTAX_ID ? flags : [];
}

export function getFlagView(flagId: string): FlagView | undefined {
  const f = flags.find((x) => x.id === flagId);
  if (!f) return undefined;
  const material = materials.find((m) => m.id === f.material_id);
  const cluster = clusters.find((c) => c.id === f.cluster_id);
  const check = checks.find((c) => c.id === f.check_id);
  const rule = check ? rules.find((r) => r.id === check.rule_id) : undefined;
  const property = material
    ? properties.find((p) => p.id === material.property_id)
    : undefined;
  const meta = flagMeta[f.id];
  if (!material || !cluster || !check || !rule || !property || !meta) {
    return undefined;
  }
  return { flag: f, material, property, cluster, rule, check, meta };
}

export function getFlagViewsForProduct(productId: string): FlagView[] {
  return getFlags(productId)
    .map((f) => getFlagView(f.id))
    .filter((v): v is FlagView => v !== undefined);
}

// ---------------------------------------------------------------------------
// U3 live chips: deterministic extraction of typed properties from freeform
// text. In fixture mode this simulates N1 extract-properties client-side.
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
