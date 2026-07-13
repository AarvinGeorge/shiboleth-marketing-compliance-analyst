// meta: U7 flag detail (/products/[id]/flags/[flagId]), API-backed via
// useFlagView. Breadcrumb Dashboard › product › flag; header with
// SeverityBadge, title (real cluster label), check id; three-tag verdict
// group + one-line explainer (first sentence of the real checker reason);
// evidence panel highlighting the API-served evidence_quote with the full
// reason below; lifecycle strip (delta 3) above the Disposition panel (live
// POST dispositions); flag facts incl. verbatim rule text via RuleText;
// compact why-flagged chain whose verdict step expands to the real reason.
// Header carries a prominent "View original source" button (meta.sourceUrl =
// materials.ref, the clean per-page URL) opening the live source in a new tab.

"use client";

import { use } from "react";
import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SeverityBadge } from "@/components/primitives/severity-badge";
import { VerdictTags } from "@/components/primitives/verdict-tags";
import {
  LifecycleStrip,
  lifecycleLabel,
} from "@/components/primitives/lifecycle-chip";
import { EvidencePanel } from "@/components/surfaces/evidence-panel";
import { DispositionPanel } from "@/components/surfaces/disposition-panel";
import { WhyFlagged } from "@/components/surfaces/why-flagged";
import { useFlagView, useProductView } from "@/lib/data";
import { useFlagStore } from "@/lib/flag-store";
import { RuleText } from "@/lib/render-rule-text";

export default function FlagDetailPage({
  params,
}: {
  params: Promise<{ id: string; flagId: string }>;
}) {
  const { id, flagId } = use(params);
  const { summary } = useProductView(id);
  const { view, isLoading } = useFlagView(id, flagId);
  const storeLifecycle = useFlagStore((s) => s.lifecycles[flagId]);

  if (isLoading) {
    return (
      <main className="flex flex-col gap-3 px-11 pb-14 pt-7">
        <div className="h-5 w-72 animate-pulse rounded-sm bg-surface" />
        <div className="h-64 animate-pulse rounded-lg border border-border bg-surface" />
      </main>
    );
  }

  if (!summary || !view) {
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
  const lifecycle = storeLifecycle ?? {
    state: flag.state,
    team: flag.assigned_team,
    note: flag.note,
  };

  return (
    <main className="flex flex-col px-11 pb-14 pt-7">
      <div className="mb-3.5 text-xs text-muted-foreground">
        <Link href="/" className="text-primary hover:underline">
          Dashboard
        </Link>{" "}
        <span className="text-border">›</span>{" "}
        <Link href={`/products/${id}`} className="text-primary hover:underline">
          {summary.name}
        </Link>{" "}
        <span className="text-border">›</span> Flag {shortId(flag.id)}
      </div>

      <div className="mb-2 flex items-center gap-2.5">
        <SeverityBadge severity={meta.severity} />
        <h1 className="flex-1 text-lg font-medium tracking-tight">
          {meta.title}
        </h1>
        <span className="text-xs text-muted-foreground">
          <span className="font-mono">{check.id}</span> · {meta.foundAt}
        </span>
        {meta.sourceUrl ? (
          <Button asChild size="sm" className="ml-1">
            <a
              href={meta.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              title={meta.sourceUrl}
            >
              <ExternalLink className="size-3.5" />
              View original source
            </a>
          </Button>
        ) : null}
      </div>
      <div className="mb-6 flex items-start gap-3">
        <VerdictTags verdicts={flag.verdicts} className="flex-none" />
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

          <DispositionPanel
            flagId={flag.id}
            productId={id}
            fallback={{
              state: flag.state,
              team: flag.assigned_team,
              note: flag.note,
            }}
          />
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <div className="flex flex-col gap-2 rounded-lg border border-border px-4.5 py-4">
            <span className="mb-0.5 text-[13px] font-semibold">Flag facts</span>
            <FactRow label="Rule">
              <span className="font-mono text-xs">
                {rule.id} · check {check.id}
              </span>
            </FactRow>
            {rule.verbatim_text ? (
              <div className="rounded-md border border-border/60 bg-surface px-3 py-2">
                <RuleText
                  text={rule.verbatim_text}
                  className="font-mono text-[11px] leading-relaxed text-foreground/70"
                />
              </div>
            ) : null}
            <FactRow label="Linked library entry">
              <span className="font-mono text-xs">
                {check.library_entry_id ?? "none"}
              </span>
            </FactRow>
            <FactRow label="Cluster">
              <span className="text-xs">{cluster.label}</span>
            </FactRow>
            <FactRow label="Status">
              <span className="text-xs">
                {lifecycle.state === "open"
                  ? "Awaiting triage"
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

function shortId(id: string): string {
  return id.length > 12 ? id.slice(0, 8) : id;
}
