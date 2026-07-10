// meta: U6 product detail (/products/[id]). Product metric row (4 MetricCards,
// contents per v2.2 delta with a verified-score-per-run line sparkline), flags
// list with BOTH groupings toggleable (by cluster AND by property), cluster
// bulk actions (Dismiss all / Confirm all on open flags), per-flag disposition
// via FlagRow, lifecycle chips, three-tag verdicts. Reads via lib/data only;
// disposition state lives in the client flag store.

"use client";

import { use, useMemo, useState } from "react";
import Link from "next/link";
import { Check, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MetricCard } from "@/components/primitives/metric-card";
import { Sparkline } from "@/components/primitives/sparkline";
import { FlagRow } from "@/components/primitives/flag-row";
import { IntersectionPill } from "@/components/primitives/verdict-tags";
import { LifecycleChip } from "@/components/primitives/lifecycle-chip";
import { PropertyIcon } from "@/components/primitives/property-chip";
import {
  getClusters,
  getFlagViewsForProduct,
  getProduct,
  getProductMetrics,
  type FlagView,
} from "@/lib/data";
import { useFlagStore } from "@/lib/flag-store";
import type { FlagState, IntersectionTag, PropertyKind } from "@/lib/types";
import { cn } from "@/lib/utils";

type Grouping = "cluster" | "property";

export default function ProductDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const product = getProduct(id);
  const metrics = getProductMetrics(id);
  const clusters = getClusters(id);
  const views = getFlagViewsForProduct(id);
  const [grouping, setGrouping] = useState<Grouping>("cluster");

  if (!product) {
    return (
      <main className="px-11 pt-9 text-sm text-muted-foreground">
        Product not found.{" "}
        <Link href="/" className="text-primary hover:underline">
          Back to dashboard
        </Link>
      </main>
    );
  }

  return (
    <main className="flex flex-col px-11 pb-14 pt-7">
      <div className="mb-3.5 text-xs text-muted-foreground">
        <Link href="/" className="text-primary hover:underline">
          Dashboard
        </Link>{" "}
        <span className="text-border">›</span> {product.name}
      </div>

      <div className="mb-5 flex items-start justify-between">
        <div className="flex flex-col gap-1.5">
          <h1 className="text-xl font-medium tracking-tight">{product.name}</h1>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {product.coverage.map((c) => (
              <span
                key={c.kind}
                className="inline-flex h-[22px] items-center gap-1.5 rounded-sm border border-border bg-surface px-2 font-mono text-[11px] font-medium text-foreground/70"
              >
                <PropertyIcon kind={c.kind} className="size-3" />
                {c.label}
              </span>
            ))}
            {product.lastChecked ? (
              <span>{product.lastChecked.toLowerCase()}</span>
            ) : null}
          </div>
        </div>
        <Button variant="outline" className="gap-2">
          <RefreshCw className="size-3.5" />
          Re-run
        </Button>
      </div>

      {metrics.length > 0 ? (
        <div className="mb-6 grid grid-cols-4 gap-3">
          {metrics.map((m) => (
            <MetricCard
              key={m.id}
              label={m.label}
              intent={m.intent}
              value={m.value}
              sublabel={m.sublabel}
              sparkline={
                m.sparkline ? (
                  <Sparkline data={m.sparkline} kind={m.sparklineKind} />
                ) : undefined
              }
            />
          ))}
        </div>
      ) : null}

      {views.length === 0 ? (
        <NoFlags checking={product.status === "checking"} />
      ) : (
        <>
          <div className="mb-3.5 flex items-center gap-3">
            <span className="flex-1 text-[13px] font-semibold">
              {views.length} flags in {clusters.length} clusters
            </span>
            <div className="flex rounded-md bg-muted p-[3px]">
              {(["cluster", "property"] as const).map((g) => (
                <button
                  key={g}
                  type="button"
                  onClick={() => setGrouping(g)}
                  className={cn(
                    "flex h-7 items-center whitespace-nowrap rounded-sm px-3 text-xs",
                    grouping === g
                      ? "bg-background font-semibold shadow-sm"
                      : "font-medium text-muted-foreground"
                  )}
                >
                  {g === "cluster" ? "By cluster" : "By property"}
                </button>
              ))}
            </div>
          </div>

          {grouping === "cluster" ? (
            <div className="flex flex-col gap-3.5">
              {clusters.map((c) => (
                <ClusterGroup
                  key={c.id}
                  label={c.label}
                  sourceLine={c.sourceLine}
                  dominantTag={c.dominantTag}
                  views={c.flagIds
                    .map((fid) => views.find((v) => v.flag.id === fid))
                    .filter((v): v is FlagView => v !== undefined)}
                  productId={id}
                />
              ))}
            </div>
          ) : (
            <div className="flex flex-col gap-3.5">
              {groupByProperty(views).map(([kind, group]) => (
                <div
                  key={kind}
                  className="overflow-hidden rounded-lg border border-border bg-background"
                >
                  <div className="flex items-center gap-2.5 border-b border-border/60 bg-surface px-5 py-3.5">
                    <span className="flex size-6 items-center justify-center rounded-sm border border-border bg-background text-muted-foreground">
                      <PropertyIcon kind={kind} />
                    </span>
                    <span className="flex-1 text-[13px] font-semibold">
                      {group[0].property.url_or_handle}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {group.length} {group.length === 1 ? "flag" : "flags"}
                    </span>
                  </div>
                  <div className="divide-y divide-border/60">
                    {group.map((v) => (
                      <FlagRow key={v.flag.id} view={v} productId={id} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}

function ClusterGroup({
  label,
  sourceLine,
  dominantTag,
  views,
  productId,
}: {
  label: string;
  sourceLine: string;
  dominantTag: IntersectionTag;
  views: FlagView[];
  productId: string;
}) {
  const lifecycles = useFlagStore((s) => s.lifecycles);
  const confirmAll = useFlagStore((s) => s.confirmAll);
  const dismissAll = useFlagStore((s) => s.dismissAll);
  const flagIds = useMemo(() => views.map((v) => v.flag.id), [views]);
  const openCount = flagIds.filter(
    (fid) => lifecycles[fid]?.state === "open"
  ).length;

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-background">
      <div className="flex items-center gap-2.5 border-b border-border/60 bg-surface px-5 py-3.5">
        <IntersectionPill tag={dominantTag} />
        <div className="flex min-w-0 flex-1 flex-col leading-snug">
          <span className="text-[13px] font-semibold">{label}</span>
          <span className="text-xs text-muted-foreground">
            <SourceLine text={sourceLine} />
          </span>
        </div>
        {openCount > 0 ? (
          <>
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground"
              onClick={() => dismissAll(flagIds)}
            >
              Dismiss all
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => confirmAll(flagIds)}
            >
              Confirm all
            </Button>
          </>
        ) : (
          <ClusterStateChip
            states={flagIds.map((fid) => lifecycles[fid].state)}
            team={
              flagIds.map((fid) => lifecycles[fid].team).find((t) => t) ?? null
            }
          />
        )}
      </div>
      <div className="divide-y divide-border/60">
        {views.map((v) => (
          <FlagRow key={v.flag.id} view={v} productId={productId} />
        ))}
      </div>
    </div>
  );
}

function ClusterStateChip({
  states,
  team,
}: {
  states: FlagState[];
  team: string | null;
}) {
  const unique = Array.from(new Set(states));
  if (unique.length === 1) {
    return <LifecycleChip state={unique[0]} team={team} />;
  }
  return (
    <span className="text-xs text-muted-foreground">all dispositioned</span>
  );
}

function SourceLine({ text }: { text: string }) {
  // Rule and entry ids render in the mono face (DESIGN.md typography rule).
  const parts = text.split(/(R-0\d(?:\.\d)?|D-0\d)/g);
  return (
    <>
      {parts.map((p, i) =>
        /^(R-0\d(\.\d)?|D-0\d)$/.test(p) ? (
          <span key={i} className="font-mono">
            {p}
          </span>
        ) : (
          <span key={i}>{p}</span>
        )
      )}
    </>
  );
}

function groupByProperty(views: FlagView[]): [PropertyKind, FlagView[]][] {
  const order: PropertyKind[] = ["website", "instagram", "facebook"];
  const map = new Map<PropertyKind, FlagView[]>();
  for (const v of views) {
    const k = v.property.kind;
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(v);
  }
  return order
    .filter((k) => map.has(k))
    .map((k) => [k, map.get(k)!] as [PropertyKind, FlagView[]]);
}

function NoFlags({ checking }: { checking: boolean }) {
  return (
    <div className="flex flex-col items-center gap-1.5 rounded-lg border border-border px-6 py-8 text-center">
      <span className="flex size-6 items-center justify-center rounded-pill border border-success/30 bg-success-bg">
        <Check className="size-3 text-success" />
      </span>
      <span className="text-[13px] font-semibold">
        {checking ? "Check in progress" : "No open flags"}
      </span>
      <span className="text-xs text-muted-foreground">
        {checking
          ? "Results land here as checks complete."
          : "All checks passing. The daily check keeps watching for drift."}
      </span>
    </div>
  );
}
