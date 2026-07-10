// meta: U7 flag detail (/products/[id]/flags/[flagId]). Breadcrumb Dashboard ›
// product › flag; header with SeverityBadge, title, rule id and found time;
// three-tag verdict group + one-line explainer; extracted-text evidence panel
// with the span highlighted (swappable on modality); lifecycle strip (delta 3)
// above the Disposition panel; flag facts; compact 5-step why-flagged chain
// with one expandable step. Reads via lib/data; lifecycle via the flag store.

"use client";

import { use } from "react";
import Link from "next/link";
import { SeverityBadge } from "@/components/primitives/severity-badge";
import { VerdictTags } from "@/components/primitives/verdict-tags";
import { LifecycleStrip, lifecycleLabel } from "@/components/primitives/lifecycle-chip";
import { EvidencePanel } from "@/components/surfaces/evidence-panel";
import { DispositionPanel } from "@/components/surfaces/disposition-panel";
import { WhyFlagged } from "@/components/surfaces/why-flagged";
import { getFlagView, getProduct } from "@/lib/data";
import { useFlagStore } from "@/lib/flag-store";

export default function FlagDetailPage({
  params,
}: {
  params: Promise<{ id: string; flagId: string }>;
}) {
  const { id, flagId } = use(params);
  const product = getProduct(id);
  const view = getFlagView(flagId);
  const lifecycle = useFlagStore((s) => s.lifecycles[flagId]);

  if (!product || !view || !lifecycle) {
    return (
      <main className="px-11 pt-9 text-sm text-muted-foreground">
        Flag not found.{" "}
        <Link href="/" className="text-primary hover:underline">
          Back to dashboard
        </Link>
      </main>
    );
  }

  const { flag, cluster, rule, check, meta } = view;

  return (
    <main className="flex flex-col px-11 pb-14 pt-7">
      <div className="mb-3.5 text-xs text-muted-foreground">
        <Link href="/" className="text-primary hover:underline">
          Dashboard
        </Link>{" "}
        <span className="text-border">›</span>{" "}
        <Link href={`/products/${id}`} className="text-primary hover:underline">
          {product.name}
        </Link>{" "}
        <span className="text-border">›</span> Flag {flag.id}
      </div>

      <div className="mb-2 flex items-center gap-2.5">
        <SeverityBadge severity={meta.severity} />
        <h1 className="flex-1 text-lg font-medium tracking-tight">
          {meta.title}
        </h1>
        <span className="text-xs text-muted-foreground">
          <span className="font-mono">{check.id}</span> · {meta.foundAt}
        </span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <VerdictTags verdicts={flag.verdicts} />
        <span className="text-xs text-muted-foreground">{meta.explainer}</span>
      </div>

      <div className="flex items-start gap-6">
        <div className="flex min-w-0 flex-[1.4] flex-col gap-4">
          <EvidencePanel view={view} />

          <div className="flex flex-col gap-2.5">
            <span className="text-xs font-medium text-muted-foreground">
              Lifecycle
            </span>
            <LifecycleStrip state={lifecycle.state} team={lifecycle.team} />
          </div>

          <DispositionPanel flagId={flag.id} />
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <div className="flex flex-col gap-2 rounded-lg border border-border px-4.5 py-4">
            <span className="mb-0.5 text-[13px] font-semibold">Flag facts</span>
            <FactRow label="Rule">
              <span className="font-mono text-xs">
                {rule.id} · check {check.id}
              </span>
            </FactRow>
            <FactRow label="Linked library entry">
              <span className="font-mono text-xs">
                {check.library_entry_id ?? "none"}
              </span>
            </FactRow>
            <FactRow label="Cluster">
              <span className="text-xs">
                {cluster.label} ({cluster.flagIds.length} flags)
              </span>
            </FactRow>
            <FactRow label="Status">
              <span className="text-xs">
                {lifecycle.state === "open"
                  ? `Awaiting triage · ${meta.foundAt}`
                  : lifecycleLabel(lifecycle.state, lifecycle.team)}
              </span>
            </FactRow>
            <FactRow label="Confidence">
              <span className="text-xs">
                {flag.verdicts.confidence.toFixed(2)}
              </span>
            </FactRow>
            <FactRow label="Model">
              <span className="text-xs">{meta.model}</span>
            </FactRow>
          </div>

          <WhyFlagged steps={meta.chain} />
        </div>
      </div>
    </main>
  );
}

function FactRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="text-xs text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}
