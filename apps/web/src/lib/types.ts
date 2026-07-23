// meta: TypeScript mirror of apps/api/src/adlign/domain/schemas.py
// (07 §6 rule: 1:1, both sides change in the same commit). M0: vocabulary +
// core contracts; extended as milestones land.

export type PropertyKind = "website" | "instagram" | "facebook";
export type CheckKind = "trigger" | "requirement";
export type Severity = "High" | "Medium" | "Low";
export type RunMode = "corpus" | "live";
export type Modality = "text" | "image" | "social_post" | "video";

export type IntersectionTag =
  | "all_good"
  | "drifted_but_compliant"
  | "approved_but_non_compliant"
  | "unapproved_violation";

export type FlagState =
  | "open"
  | "confirmed"
  | "assigned"
  | "fix_pending_verification"
  | "closed"
  | "dismissed";

export type SSEEventType =
  | "run_started"
  | "node_started"
  | "material_fetched"
  | "property_status"
  | "check_result"
  | "node_finished"
  | "needs_input"
  | "run_awaiting_input"
  | "run_resumed"
  | "scores_updated"
  | "run_finished"
  | "error";

export interface Property {
  id: string;
  kind: PropertyKind;
  url_or_handle: string;
  config: Record<string, unknown>;
}

export interface Rule {
  id: string;
  verbatim_text: string;
  severity: Severity;
  position: number;
}

export interface BinaryCheck {
  id: string;
  rule_id: string;
  kind: CheckKind;
  text: string;
  evidence_criteria: string;
  library_entry_id: string | null;
}

export interface Material {
  id: string;
  property_id: string;
  ref: string;
  kind: string;
  modality: Modality;
  media_ref: string | null;
  content_hash: string;
  extracted_text: string;
  fetched_at: string;
}

export interface CheckResult {
  material_id: string;
  check_id: string;
  trigger_met: boolean;
  requirement_met: boolean | null;
  axis_a: boolean;
  axis_b: boolean | null; // null encodes "na"
  intersection_tag: IntersectionTag;
  evidence_quote: string;
  location: string;
  reason: string;
  // measured checker accuracy for this rule (GT v2); null = not yet measured
  accuracy_measured: { accuracy: number; source: string } | null;
}

export interface Flag {
  id: string;
  run_id: string;
  material_id: string | null;
  check_id: string;
  state: FlagState;
  assigned_team: string | null;
  note: string | null;
  modality: Modality;
  media_ref: string | null;
  cluster_id: string | null;
  verdicts: CheckResult;
}

export interface RunScores {
  draft: number | null;
  verified: number | null;
  per_property: Record<string, number>;
}

export interface Disposition {
  action: "confirm" | "dismiss";
  team?: string;
  note?: string;
}

export interface SSEEvent {
  event_id: string;
  run_id: string;
  ts: string;
  type: SSEEventType;
  node: string | null;
  property_id: string | null;
  flag_id: string | null;
  payload: Record<string, unknown>;
}
