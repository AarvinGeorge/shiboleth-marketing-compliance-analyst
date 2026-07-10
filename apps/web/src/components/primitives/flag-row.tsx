// meta: FlagRow primitive (DESIGN.md): property icon, mono snippet + location,
// VerdictTags (delta 2), then LifecycleChip or Dismiss/Confirm actions, and an
// "Open ›" link to flag detail. Dispositions POST to the API via the
// useDisposition mutation (optimistic through the flag store); a 409 or
// network failure reverts the row and shows an inline error line. No Undo:
// the lifecycle state machine has no reverse transitions.

"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LifecycleChip } from "@/components/primitives/lifecycle-chip";
import { PropertyIcon } from "@/components/primitives/property-chip";
import { VerdictTags } from "@/components/primitives/verdict-tags";
import { useFlagStore } from "@/lib/flag-store";
import { useDisposition, type FlagView } from "@/lib/data";
import { cn } from "@/lib/utils";

export const TEAMS = ["Social", "Web", "Growth", "Legal"] as const;

export function FlagRow({
  view,
  productId,
  className,
}: {
  view: FlagView;
  productId: string;
  className?: string;
}) {
  const { flag, material, property, meta } = view;
  const lifecycle = useFlagStore((s) => s.lifecycles[flag.id]) ?? {
    state: flag.state,
    team: flag.assigned_team,
    note: flag.note,
  };
  const error = useFlagStore((s) => s.errors[flag.id]);
  const disposition = useDisposition(productId);
  const [assigning, setAssigning] = useState(false);
  const [team, setTeam] = useState<string>("");
  const [note, setNote] = useState("");

  const dismissed = lifecycle.state === "dismissed";
  const untriaged = lifecycle.state === "open";
  const href = `/products/${productId}/flags/${flag.id}`;

  return (
    <div
      className={cn(
        "flex flex-col gap-2 px-5 py-4",
        dismissed && "bg-surface/60",
        className
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "mt-0.5 flex size-6 flex-none items-center justify-center rounded-sm border border-border bg-surface",
            dismissed ? "text-muted-foreground/60" : "text-muted-foreground"
          )}
        >
          <PropertyIcon kind={property.kind} />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <span
            className={cn(
              "font-mono text-xs leading-5",
              dismissed
                ? "text-muted-foreground line-through"
                : "text-foreground/80"
            )}
          >
            &ldquo;{truncate(flag.verdicts.evidence_quote, 110)}&rdquo;
          </span>
          <span className="text-xs text-muted-foreground">
            {flag.verdicts.location} ·{" "}
            <span className="font-mono">{shortId(flag.id)}</span>
          </span>
          {dismissed && lifecycle.note ? (
            <span className="text-xs text-muted-foreground">
              Dismissed: {lifecycle.note}
            </span>
          ) : (
            <span className="text-xs text-foreground/70">
              {meta.explainer}
            </span>
          )}
          {!dismissed ? <VerdictTags verdicts={flag.verdicts} /> : null}
          {error ? (
            <span className="text-xs font-medium text-danger-text">
              {error}
            </span>
          ) : null}
        </div>
        <div className="flex flex-none items-center gap-2 pt-0.5">
          {untriaged && !assigning ? (
            <>
              <Button
                variant="outline"
                size="sm"
                disabled={disposition.isPending}
                onClick={() =>
                  disposition.mutate({ flagId: flag.id, action: "dismiss" })
                }
              >
                Dismiss
              </Button>
              <Button
                size="sm"
                disabled={disposition.isPending}
                onClick={() => setAssigning(true)}
              >
                Confirm
              </Button>
            </>
          ) : !untriaged ? (
            <LifecycleChip state={lifecycle.state} team={lifecycle.team} />
          ) : null}
          {!dismissed ? (
            <Link
              href={href}
              className="whitespace-nowrap text-xs font-medium text-primary hover:underline"
            >
              Open ›
            </Link>
          ) : null}
        </div>
      </div>
      {assigning ? (
        <div className="ml-9 flex flex-col gap-2.5 rounded-md border border-border bg-surface p-3">
          <span className="text-xs text-foreground/70">On confirm, assign to</span>
          <div className="flex gap-2">
            {TEAMS.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTeam(t)}
                className={cn(
                  "inline-flex h-7 items-center rounded-md border px-3 text-xs font-medium",
                  team === t
                    ? "border-primary/40 bg-accent text-accent-foreground"
                    : "border-border bg-background text-foreground/70 hover:bg-muted"
                )}
              >
                {t}
              </button>
            ))}
          </div>
          <Input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note, travels with the assignment"
            className="h-8 bg-background text-xs"
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={!team || disposition.isPending}
              onClick={() => {
                disposition.mutate({
                  flagId: flag.id,
                  action: "confirm",
                  team,
                  note: note || undefined,
                });
                setAssigning(false);
              }}
            >
              Assign
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setAssigning(false)}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
      <span className="sr-only">{material.ref}</span>
    </div>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 3)}...` : s;
}

function shortId(id: string): string {
  return id.length > 12 ? id.slice(0, 8) : id;
}
