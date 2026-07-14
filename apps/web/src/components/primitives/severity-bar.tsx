// meta: SeverityBar (severity representation increment, 2026-07-13; restores
// doc 04 hero metric #2 intent). ONE thin horizontal stacked bar of open
// violations by severity in the VALIDATED ordinal ramp (darker = worse,
// binding): High #991b1b, Medium #dc2626, Low #f47c7c; 2px white gaps,
// rounded ends. Below it a compact labeled count row in ink tokens (counts
// always visible; labels are the secondary encoding). Hovering a segment or
// its label gently dims the others (the donut's 140ms pattern, no floating
// tooltip). Zero-count severities: segment omitted, label kept with a muted
// 0. Per-flag severity override is DEFERRED; severity derives from rules.

"use client";

import { useState } from "react";

const SEGMENTS = [
  { key: "High", color: "#991b1b" },
  { key: "Medium", color: "#dc2626" },
  { key: "Low", color: "#f47c7c" },
] as const;

type SeverityKey = (typeof SEGMENTS)[number]["key"];

export function SeverityBar({
  bySeverity,
}: {
  bySeverity: Record<SeverityKey, number>;
}) {
  const [active, setActive] = useState<SeverityKey | null>(null);
  const total = SEGMENTS.reduce((n, s) => n + (bySeverity[s.key] ?? 0), 0);
  const nonzero = SEGMENTS.filter((s) => (bySeverity[s.key] ?? 0) > 0);

  return (
    <div
      className="flex flex-col gap-1.5"
      onMouseLeave={() => setActive(null)}
    >
      {total > 0 ? (
        <div className="flex h-2 w-full gap-[2px] overflow-hidden rounded-pill">
          {nonzero.map((s) => (
            <div
              key={s.key}
              style={{
                flexGrow: bySeverity[s.key],
                flexBasis: 0,
                backgroundColor: s.color,
                opacity: active === null || active === s.key ? 1 : 0.3,
                transition: "opacity 140ms ease",
              }}
              onMouseEnter={() => setActive(s.key)}
            />
          ))}
        </div>
      ) : null}
      <div className="flex items-center gap-1.5 text-[11px] leading-4">
        {SEGMENTS.map((s, i) => {
          const count = bySeverity[s.key] ?? 0;
          const dimmed = active !== null && active !== s.key;
          return (
            <span key={s.key} className="flex items-center gap-1.5">
              {i > 0 ? <span className="text-border">·</span> : null}
              <span
                className={
                  count === 0
                    ? "text-muted-foreground/60"
                    : "text-foreground/80"
                }
                style={{
                  opacity: dimmed ? 0.45 : 1,
                  transition: "opacity 140ms ease",
                }}
                onMouseEnter={() => setActive(count > 0 ? s.key : null)}
              >
                {s.key}{" "}
                <span className="font-mono text-muted-foreground">
                  {count}
                </span>
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
