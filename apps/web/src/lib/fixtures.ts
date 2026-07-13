// meta: presentation view-model types shared by the surfaces + data.ts, plus
// the VERBATIM scorecard rules (doc 05 §1). All runtime fixture DATA has been
// deleted: every visible number now comes from the API via data.ts. The rules
// stay only because there is no rules endpoint yet; their text is byte-for-byte
// doc 05 §1 (rendered through lib/render-rule-text.tsx) and matches the DB seed.

import type {
  IntersectionTag,
  PropertyKind,
  Rule,
  Severity,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// View-model types (fixture-layer only; the frozen contract stays in types.ts)
// ---------------------------------------------------------------------------

// Live run lifecycle reflected on the dashboard card (all from API/event data).
export type ProductStatus =
  | "flagged"
  | "clear"
  | "running"
  | "awaiting_input";

export interface PropertyCoverage {
  kind: PropertyKind;
  label: string;
}

export interface ParkedProperty {
  id: string;
  kind: PropertyKind;
  label: string;
}

export interface ProductSummary {
  id: string;
  name: string;
  status: ProductStatus;
  verifiedScore: number | null;
  openFlagCount: number;
  note: string;
  coverage: PropertyCoverage[];
  lastChecked: string | null;
  runId: string | null;
  // running: real material_fetched count vs the run's crawl cap (no timers)
  progress: { fetched: number; cap: number } | null;
  // awaiting_input: properties the run parked, needing paste or skip
  parked: ParkedProperty[];
}

export interface SublabelPart {
  text: string;
  tone?: "danger" | "warning" | "success";
}

export interface MetricFixture {
  id: string;
  label: string;
  intent: string; // tooltip line (delta PDF / 01_spec §10)
  value: string;
  delta?: { text: string; tone: "success" | "danger" };
  sublabel: SublabelPart[];
  sparkline?: number[];
  sparklineKind?: "area" | "line";
}

export interface ClusterFixture {
  id: string;
  productId: string;
  label: string;
  sourceLine: string; // e.g. "R-01 · 6 flags: 4 pages, 2 Instagram posts"
  dominantTag: IntersectionTag;
  flagIds: string[];
}

export interface WhyStep {
  title: string;
  detail?: string; // present on the expandable step
}

export interface FlagMeta {
  flagId: string;
  title: string; // short finding title (flag detail header)
  explainer: string; // one-line explainer under the tags
  severity: Severity;
  foundAt: string;
  model: string;
  missingRequirement: string | null; // "required nearby, not found" callout
  chain: WhyStep[]; // compact why-flagged chain, 5 steps
  postDate: string | null; // social posts only
  sourceUrl: string | null; // clean per-page URL (materials.ref) for the source link

}

// ---------------------------------------------------------------------------
// Scorecard: 4 rules VERBATIM from doc 05 §1 + decomposed checks + D-01.
// R-01 keeps the source's markdown [text](url) link markup byte-for-byte;
// rendering (links as anchors) happens ONLY via lib/render-rule-text.tsx.
// ---------------------------------------------------------------------------

export const rules: Rule[] = [
  {
    id: "R-01",
    verbatim_text:
      "If Turbotax free is mentioned, the following must be disclosed right underneath ~37% of filers qualify. [Simple Form 1040 returns only](https://turbotax.intuit.com/personal-taxes/online/free-edition.jsp#modals/simple-tax-returns-en) (no schedules, except for EITC, CTC, student loan interest, and Schedule 1-A).",
    severity: "High",
    position: 1,
  },
  {
    id: "R-02",
    verbatim_text:
      "If a rate of finance charge was stated, was the finance charge stated as an APR?",
    severity: "High",
    position: 2,
  },
  {
    id: "R-03",
    verbatim_text:
      "If the product being advertised is a deposit product, does the FDIC insurance language state Deposit product is FDIC-insured up to $250,000 through  Bank",
    severity: "Medium",
    position: 3,
  },
  {
    id: "R-04",
    verbatim_text:
      'If an institution states a bonus in an advertisement, does the advertisement state clearly and conspicuously the following information, if applicable to the advertised product: (1) "Annual percentage yield," using that term; (2) Time requirement to obtain the bonus; (3) Minimum balance required to obtain the bonus; (4) Minimum balance required to open the account, if it is greater than the minimum balance necessary to obtain the bonus; and (5) Time when the bonus will be provided? In addition, general statements such as "bonus checking" or "get a bonus when you open a checking account" do not trigger the bonus disclosures.',
    severity: "Medium",
    position: 4,
  },
];
