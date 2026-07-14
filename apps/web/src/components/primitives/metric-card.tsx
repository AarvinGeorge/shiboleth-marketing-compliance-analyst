// meta: MetricCard primitive (DESIGN.md components). Muted 12px label + info
// tooltip carrying the metric's intent line (01_spec §10 / delta PDF), a
// metric-value number (22px / 500 per DESIGN.md typography), muted sublabel
// (parts can carry semantic tones), optional sparkline slot, optional footer
// slot below the sublabel (e.g. the SeverityBar inside Open violations).
// Card surface per DESIGN.md metric-card token: soft surface bg, rounded-md.

import { Info } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { SublabelPart } from "@/lib/fixtures";
import { cn } from "@/lib/utils";

const toneClass: Record<NonNullable<SublabelPart["tone"]>, string> = {
  danger: "text-danger font-medium",
  warning: "text-warning-text font-medium",
  success: "text-success font-medium",
};

export function MetricCard({
  label,
  intent,
  value,
  delta,
  sublabel,
  sparkline,
  footer,
  className,
}: {
  label: string;
  intent: string;
  value: string;
  delta?: { text: string; tone: "success" | "danger" };
  sublabel: SublabelPart[];
  sparkline?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-0.5 rounded-md border border-border bg-surface px-3.5 py-3",
        className
      )}
    >
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">
          {label}
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={`About ${label}`}
              className="text-muted-foreground/70 hover:text-muted-foreground"
            >
              <Info className="size-3" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-56">
            {intent}
          </TooltipContent>
        </Tooltip>
      </div>
      <div className="flex items-end justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <span className="text-[1.375rem] leading-7 font-medium tracking-tight">
            {value}
          </span>
          {delta ? (
            <span
              className={cn(
                "text-xs font-medium",
                delta.tone === "success" ? "text-success" : "text-danger"
              )}
            >
              {delta.text}
            </span>
          ) : null}
        </div>
        {sparkline ? <div className="pb-1">{sparkline}</div> : null}
      </div>
      <div className="text-[11px] leading-4 text-muted-foreground">
        {sublabel.map((part, i) => (
          <span key={i} className={part.tone ? toneClass[part.tone] : undefined}>
            {part.text}
          </span>
        ))}
      </div>
      {footer ? <div className="mt-2">{footer}</div> : null}
    </div>
  );
}
