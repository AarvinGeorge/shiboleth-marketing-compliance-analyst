// meta: U7 Disposition panel. Open: Dismiss / Confirm; Confirm opens the
// assign strip (Social | Web | Growth | Legal + note + Assign/Cancel,
// prototype 3g state 1). Actions POST /flags/{id}/disposition via the
// useDisposition mutation (optimistic, reconciled with the server's
// {flag, scores}); 409s render as an inline error line, not a crash.
// After assignment the delta 3 hint appears. No Undo: dismissed is terminal
// in the M4 state machine.

"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TEAMS } from "@/components/primitives/flag-row";
import { LifecycleChip } from "@/components/primitives/lifecycle-chip";
import { useFlagStore } from "@/lib/flag-store";
import { useDisposition } from "@/lib/data";
import { cn } from "@/lib/utils";
import type { FlagState } from "@/lib/types";

export function DispositionPanel({
  flagId,
  productId,
  fallback,
}: {
  flagId: string;
  productId: string;
  fallback: { state: FlagState; team: string | null; note: string | null };
}) {
  const lifecycle = useFlagStore((s) => s.lifecycles[flagId]) ?? fallback;
  const error = useFlagStore((s) => s.errors[flagId]);
  const disposition = useDisposition(productId);
  const [assigning, setAssigning] = useState(false);
  const [team, setTeam] = useState("");
  const [note, setNote] = useState("");

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border px-5 py-4.5">
      <span className="text-[13px] font-semibold">Disposition</span>

      {lifecycle.state === "open" ? (
        <>
          <div className="flex gap-2.5">
            <Button
              variant="outline"
              disabled={disposition.isPending}
              onClick={() => disposition.mutate({ flagId, action: "dismiss" })}
            >
              Dismiss
            </Button>
            <Button
              disabled={disposition.isPending}
              onClick={() => setAssigning(true)}
            >
              Confirm
            </Button>
          </div>
          {assigning ? (
            <div className="flex flex-col gap-2.5 border-t border-border/60 pt-3.5">
              <span className="text-xs text-foreground/70">
                On confirm, assign to
              </span>
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
                className="h-8 text-xs"
              />
              <div className="flex gap-2.5">
                <Button
                  size="sm"
                  disabled={!team || disposition.isPending}
                  onClick={() => {
                    disposition.mutate({
                      flagId,
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
        </>
      ) : lifecycle.state === "dismissed" ? (
        <div className="flex items-center gap-2.5">
          <span className="inline-flex h-[26px] items-center rounded-md bg-muted px-2.5 text-xs font-medium text-muted-foreground">
            Dismissed as false positive
          </span>
          {lifecycle.note ? (
            <span className="text-xs text-muted-foreground">
              Note: {lifecycle.note}
            </span>
          ) : null}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2.5">
            {lifecycle.state === "assigned" || lifecycle.state === "confirmed" ? (
              <span className="inline-flex h-[26px] items-center gap-1.5 rounded-md bg-accent px-2.5 text-xs font-semibold text-accent-foreground">
                <Check className="size-3" />
                {lifecycle.team
                  ? `Confirmed, assigned to ${lifecycle.team}`
                  : "Confirmed"}
              </span>
            ) : (
              <LifecycleChip state={lifecycle.state} team={lifecycle.team} />
            )}
            {lifecycle.note ? (
              <span className="text-xs text-muted-foreground">
                Note: {lifecycle.note}
              </span>
            ) : null}
          </div>
          {lifecycle.state === "assigned" ||
          lifecycle.state === "fix_pending_verification" ? (
            <span className="text-xs text-muted-foreground">
              closes automatically when a future scan verifies the fix.
            </span>
          ) : null}
        </div>
      )}
      {error ? (
        <span className="text-xs font-medium text-danger-text">{error}</span>
      ) : null}
    </div>
  );
}
