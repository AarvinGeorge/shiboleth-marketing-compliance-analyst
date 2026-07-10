// meta: U7 compact why-flagged chain: the 5 pipeline steps (Crawled →
// Extracted → Trigger check → Requirement check → Verdict), numbered, with
// exactly the step carrying a detail expandable (prototype 3f). At M4 the
// steps come from persisted run events; fixture mode reads FlagMeta.chain.

"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import type { WhyStep } from "@/lib/fixtures";
import { cn } from "@/lib/utils";

export function WhyFlagged({ steps }: { steps: WhyStep[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="border-b border-border/60 px-4.5 py-3.5 text-[13px] font-semibold">
        Why this was flagged
      </div>
      {steps.map((s, i) => {
        const expandable = Boolean(s.detail);
        const isOpen = expanded === i;
        return (
          <div
            key={i}
            className={cn(i < steps.length - 1 && "border-b border-border/60")}
          >
            <button
              type="button"
              disabled={!expandable}
              onClick={() => setExpanded(isOpen ? null : i)}
              className={cn(
                "flex w-full items-start gap-2.5 px-4.5 py-2.5 text-left",
                expandable && "cursor-pointer hover:bg-surface"
              )}
            >
              <ChevronRight
                className={cn(
                  "mt-1 size-3 flex-none text-muted-foreground/70 transition-transform",
                  isOpen && "rotate-90",
                  !expandable && "opacity-0"
                )}
              />
              <span className="mt-0.5 flex-none font-mono text-[11px] font-semibold text-muted-foreground">
                {i + 1}
              </span>
              <span className="text-xs font-medium text-foreground/80">
                {s.title}
              </span>
            </button>
            {isOpen && s.detail ? (
              <div className="px-4.5 pb-3 pl-[57px] text-xs leading-relaxed text-foreground/70">
                {s.detail}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
