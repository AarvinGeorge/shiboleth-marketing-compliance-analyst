// meta: U2 dashboard (route /). Five hero MetricCards render from GET /metrics
// (value, sublabel, intent tooltip; the portfolio card's sparkline from the
// REAL trend array only). Product cards render ONLY GET /products results, in
// their live run state: running (progress from real material_fetched count vs
// page cap), awaiting_input (legacy runs only; the redesigned ingestion
// auto-skips failed mediums instead of parking), or completed (verified score
// + open-flag count + delete-latest-check with
// confirm against DELETE /runs/{id}). No fixtures, no timers. Display
// vocabulary: "marketing mediums" (code identifiers keep property_*).

"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Activity,
  Check,
  Loader2,
  LoaderCircle,
  Plus,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { MetricCard } from "@/components/primitives/metric-card";
import { Sparkline } from "@/components/primitives/sparkline";
import { PropertyIcon } from "@/components/primitives/property-chip";
import { NewCheckModal } from "@/components/shell/new-check-modal";
import { PasteDialog } from "@/components/shell/paste-dialog";
import { ApiError } from "@/lib/api";
import {
  useDeleteRun,
  useMetrics,
  useProducts,
  useStartCheck,
} from "@/lib/data";
import type { ProductSummary } from "@/lib/fixtures";

const MEDIUM_NAME: Record<string, string> = {
  website: "Website",
  instagram: "Instagram",
  facebook: "Facebook",
};

export default function DashboardPage() {
  const { products, isLoading, apiDown, hasActiveRun } = useProducts();
  const { metrics } = useMetrics(hasActiveRun);

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

      {metrics.length > 0 ? (
        <div className="mb-7 grid grid-cols-5 gap-3">
          {metrics.map((m) => (
            <MetricCard
              key={m.id}
              label={m.label}
              intent={m.intent}
              value={m.value ?? ""}
              sublabel={[{ text: m.sublabel }]}
              sparkline={
                m.trend ? <Sparkline data={m.trend} kind="area" /> : undefined
              }
            />
          ))}
        </div>
      ) : null}

      {apiDown ? (
        <div className="mb-3 flex items-center gap-2.5 rounded-md border border-danger/30 bg-danger-bg px-3.5 py-2.5">
          <TriangleAlert className="size-3.5 flex-none text-danger" />
          <span className="text-xs text-foreground/70">
            The API is unreachable. Start the service to see products.
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
  const startCheck = useStartCheck();
  if (p.status === "running") {
    const pct = p.progress && p.progress.cap > 0
      ? Math.min(100, Math.round((p.progress.fetched / p.progress.cap) * 100))
      : 0;
    return (
      <div className="flex items-center gap-6 rounded-lg border border-border bg-background p-5 pl-6">
        <div className="flex min-w-0 flex-1 flex-col gap-2.5">
          <div className="flex items-center gap-2.5">
            <span className="text-[15px] font-medium">{p.name}</span>
            <span className="inline-flex h-5 items-center gap-1.5 rounded-pill bg-accent px-2 text-[11px] font-medium text-accent-foreground">
              <LoaderCircle className="size-2.5 animate-spin" />
              Checking
            </span>
          </div>
          <div className="flex items-center gap-3.5">
            <Progress value={pct} className="h-1.5 w-80" />
            <span className="text-xs text-muted-foreground">
              {p.progress?.fetched ?? 0} of {p.progress?.cap ?? 0} pages fetched
            </span>
          </div>
        </div>
      </div>
    );
  }

  if (p.status === "awaiting_input") {
    return (
      <div className="flex items-center gap-6 rounded-lg border border-border bg-background p-5 pl-6">
        <div className="flex min-w-0 flex-1 flex-col gap-2.5">
          <div className="flex items-center gap-2.5">
            <span className="text-[15px] font-medium">{p.name}</span>
            <span className="inline-flex h-5 items-center gap-1.5 rounded-pill bg-warning-bg px-2 text-[11px] font-semibold text-warning-text">
              <TriangleAlert className="size-2.5" />
              Needs input
            </span>
          </div>
          <span className="text-xs text-muted-foreground">{p.note}</span>
        </div>
        {p.runId ? (
          <PasteDialog productId={p.id} runId={p.runId} parked={p.parked} />
        ) : null}
      </div>
    );
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
              key={`${c.kind}:${c.label}`}
              className="inline-flex h-[22px] items-center gap-1.5 rounded-sm border border-border bg-surface px-2 font-mono text-[11px] font-medium text-foreground/70"
            >
              <PropertyIcon kind={c.kind} className="size-3" />
              {c.label}
            </span>
          ))}
        </div>
      </div>
      <div className="flex flex-none flex-col items-end gap-1.5">
        <span className="text-[1.375rem] font-medium leading-7 tracking-tight">
          {p.verifiedScore ?? ""}
        </span>
        <span className="text-[11px] text-muted-foreground">
          {p.lastChecked}
        </span>
        <div className="mt-0.5 flex items-center gap-1.5">
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            disabled={startCheck.isPending}
            onClick={() => startCheck.mutate({ productId: p.id })}
          >
            Re-run
          </Button>
          {p.runId ? (
            <DeleteRunButton runId={p.runId} productName={p.name} />
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Trash affordance for the product card's latest check run: confirm dialog,
 *  then DELETE /runs/{id}. The product falls back to its previous run (or
 *  empty) on the refetch. */
function DeleteRunButton({
  runId,
  productName,
}: {
  runId: string;
  productName: string;
}) {
  const deleteRun = useDeleteRun();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setError(null);
    try {
      await deleteRun.mutateAsync(runId);
      setOpen(false);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "The API is unreachable."
      );
    }
  }

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 text-muted-foreground"
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
        aria-label={`Delete latest check for ${productName}`}
      >
        <Trash2 className="size-3.5" />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base">Delete this check?</DialogTitle>
            <DialogDescription className="text-xs">
              All its flags, clusters and events will be permanently removed.
            </DialogDescription>
          </DialogHeader>
          {error ? (
            <p className="rounded-md border border-danger/30 bg-danger-bg px-3 py-2 text-xs text-danger-text">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground"
              disabled={deleteRun.isPending}
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={deleteRun.isPending}
              onClick={confirm}
            >
              {deleteRun.isPending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : null}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
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
