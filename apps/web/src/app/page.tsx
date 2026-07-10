// meta: U2 dashboard (route /). Five hero MetricCards with intent tooltips
// (portfolio strip stays DESIGN.md demo data; no /metrics endpoint yet) +
// product cards: REAL products from the API (TurboTax with live scores and
// open-flag counts) followed by the DESIGN.md demo cards (clear / checking /
// empty states). Reads through lib/data hooks only; API-down renders an
// inline notice, never a crash.

"use client";

import Link from "next/link";
import {
  LoaderCircle,
  Plus,
  ChevronRight,
  Check,
  Activity,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { MetricCard } from "@/components/primitives/metric-card";
import { Sparkline } from "@/components/primitives/sparkline";
import { PropertyIcon } from "@/components/primitives/property-chip";
import { NewCheckModal } from "@/components/shell/new-check-modal";
import { getHeroMetrics, useProducts } from "@/lib/data";
import type { ProductSummary } from "@/lib/fixtures";
import { cn } from "@/lib/utils";

export default function DashboardPage() {
  const metrics = getHeroMetrics();
  const { products, isLoading, apiDown } = useProducts();

  return (
    <main className="flex flex-col px-11 pb-12 pt-9">
      <div className="mb-6 flex items-start justify-between">
        <div className="flex flex-col gap-0.5">
          <h1 className="text-xl font-medium tracking-tight">
            Marketing compliance
          </h1>
          <p className="text-[13px] text-muted-foreground">
            All products, all channels, checked daily.
          </p>
        </div>
        <NewCheckModal>
          <Button className="gap-2">
            <Plus className="size-3.5" />
            New check
          </Button>
        </NewCheckModal>
      </div>

      <div className="mb-7 grid grid-cols-5 gap-3">
        {metrics.map((m) => (
          <MetricCard
            key={m.id}
            label={m.label}
            intent={m.intent}
            value={m.value}
            delta={m.delta}
            sublabel={m.sublabel}
            sparkline={
              m.sparkline ? (
                <Sparkline data={m.sparkline} kind={m.sparklineKind} />
              ) : undefined
            }
          />
        ))}
      </div>

      {apiDown ? (
        <div className="mb-3 flex items-center gap-2.5 rounded-md border border-danger/30 bg-danger-bg px-3.5 py-2.5">
          <TriangleAlert className="size-3.5 flex-none text-danger" />
          <span className="text-xs text-foreground/70">
            The API is unreachable. Live products are hidden; demo cards remain.
          </span>
        </div>
      ) : null}

      <div className="flex flex-col gap-3">
        {isLoading ? (
          <div className="h-28 animate-pulse rounded-lg border border-border bg-surface" />
        ) : products.length === 0 ? (
          <EmptyState />
        ) : (
          products.map((p) => <ProductCard key={p.id} product={p} />)
        )}
      </div>
    </main>
  );
}

function ProductCard({ product: p }: { product: ProductSummary }) {
  if (p.status === "checking" && p.checking) {
    return (
      <div className="flex items-center gap-6 rounded-lg border border-border bg-background p-5 pl-6">
        <div className="flex min-w-0 flex-1 flex-col gap-2.5">
          <div className="flex items-center gap-2.5">
            <Link
              href={`/products/${p.id}`}
              className="text-[15px] font-medium hover:underline"
            >
              {p.name}
            </Link>
            <span className="inline-flex h-5 items-center gap-1.5 rounded-pill bg-accent px-2 text-[11px] font-medium text-accent-foreground">
              <LoaderCircle className="size-2.5 animate-spin" />
              Checking
            </span>
          </div>
          <div className="flex items-center gap-3.5">
            <Progress value={p.checking.pct} className="h-1.5 w-80" />
            <span className="text-xs text-muted-foreground">
              {p.checking.done} of {p.checking.total} checks ·{" "}
              {p.checking.step}
            </span>
          </div>
        </div>
        <Button variant="outline" size="sm" className="gap-1.5">
          View steps
          <ChevronRight className="size-3" />
        </Button>
      </div>
    );
  }

  if (p.status === "empty") {
    return <EmptyState />;
  }

  const flagged = p.status === "flagged";
  return (
    <div className="flex items-start gap-6 rounded-lg border border-border bg-background p-5 pl-6">
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-center gap-2.5">
          <Link
            href={`/products/${p.id}`}
            className="text-[15px] font-medium hover:underline"
          >
            {p.name}
          </Link>
          {flagged ? (
            <span className="inline-flex h-5 items-center rounded-pill bg-danger-bg px-2 text-[11px] font-semibold text-danger-text">
              {p.openFlagCount} open flags
            </span>
          ) : (
            <span className="inline-flex h-5 items-center gap-1 rounded-pill bg-success-bg px-2 text-[11px] font-semibold text-success-text">
              <Check className="size-2.5" />
              Clear
            </span>
          )}
        </div>
        <p className="max-w-2xl text-[13px] text-foreground/70">{p.note}</p>
        <div className="flex flex-wrap items-center gap-2">
          {p.coverage.map((c) => (
            <span
              key={c.kind}
              className="inline-flex h-[22px] items-center gap-1.5 rounded-sm border border-border bg-surface px-2 font-mono text-[11px] font-medium text-foreground/70"
            >
              <PropertyIcon kind={c.kind} className="size-3" />
              {c.label}
            </span>
          ))}
          {p.assignmentNote ? (
            <span className="ml-1 text-xs text-muted-foreground">
              {p.assignmentNote}
            </span>
          ) : null}
        </div>
      </div>
      <div className="flex flex-none flex-col items-end gap-1.5">
        <div className="flex items-center gap-2.5">
          {p.scoreTrend.length > 0 ? (
            <Sparkline data={p.scoreTrend} kind="line" className="h-5 w-16" />
          ) : null}
          <span
            className={cn(
              "text-[1.375rem] font-medium tracking-tight leading-7"
            )}
          >
            {p.verifiedScore}
          </span>
        </div>
        <span className="text-[11px] text-muted-foreground">
          {p.lastChecked}
        </span>
        <Button variant="outline" size="sm" className="mt-0.5 h-7 text-xs">
          Re-run
        </Button>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border-[1.5px] border-dashed border-border px-6 py-6 text-center">
      <Activity className="size-4.5 text-muted-foreground/70" />
      <span className="text-[13px] font-semibold">No products yet</span>
      <span className="max-w-sm text-xs text-muted-foreground">
        Run your first check to start monitoring. Your global scorecard applies
        automatically.
      </span>
      <NewCheckModal>
        <Button size="sm" className="mt-0.5">
          New check
        </Button>
      </NewCheckModal>
    </div>
  );
}
