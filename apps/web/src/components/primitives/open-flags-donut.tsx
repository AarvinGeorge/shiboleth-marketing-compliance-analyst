// meta: OpenFlagsDonut (dashboard hero, metrics overhaul 2026-07-13). Thin
// donut of ALL open flags across the portfolio, sliced by intersection tag
// in a FIXED order (unapproved_violation, drifted_but_compliant,
// needs_review, then a muted Other only when nonzero). Validated palette
// (binding, dataviz skill): #dc2626 / #d97706 / #5b74c2; 2px white gaps.
// Interaction (2026-07-13, Aarvin: floating tooltip felt janky): NO floating
// tooltip — the CENTER is the readout. Hovering a slice or its legend row
// shows that slice's count + share in the center and dims the other slices
// with a CSS transition; mouse-out restores the total. All text in ink
// tokens. shadcn Charts (Recharts) per spec §10.

"use client";

import { useState } from "react";
import { Cell, Pie, PieChart } from "recharts";
import { ChartContainer } from "@/components/ui/chart";
import type { ApiMetrics } from "@/lib/api";

const SLICES = [
  {
    key: "unapproved_violation",
    label: "Unapproved violation",
    color: "#dc2626",
  },
  {
    key: "drifted_but_compliant",
    label: "Drifted but compliant",
    color: "#d97706",
  },
  { key: "needs_review", label: "Needs review", color: "#5b74c2" },
  { key: "other", label: "Other", color: "#a1a1aa" },
] as const;

type SliceKey = (typeof SLICES)[number]["key"];

export function OpenFlagsDonut({ metrics }: { metrics: ApiMetrics }) {
  const total = metrics.open_flags_total;
  const countOf = (key: SliceKey) => metrics.open_flags_by_tag[key] ?? 0;
  const data = SLICES.map((s) => ({
    key: s.key,
    label: s.label,
    color: s.color,
    value: countOf(s.key),
  })).filter((d) => d.value > 0);
  const legend = SLICES.filter(
    (s) => s.key !== "other" || countOf("other") > 0
  );
  const [active, setActive] = useState<SliceKey | null>(null);
  const activeSlice = data.find((d) => d.key === active) ?? null;
  const pct =
    activeSlice && total > 0
      ? Math.round((activeSlice.value / total) * 100)
      : 0;

  return (
    <div className="flex items-center gap-7 rounded-md border border-border bg-surface px-6 py-4">
      <div
        className="relative size-[150px] flex-none"
        onMouseLeave={() => setActive(null)}
      >
        <ChartContainer config={{}} className="aspect-square h-full w-full">
          <PieChart>
            {data.length > 0 ? (
              <Pie
                data={data}
                dataKey="value"
                nameKey="label"
                innerRadius="72%"
                outerRadius="100%"
                paddingAngle={2}
                stroke="#ffffff"
                strokeWidth={2}
                startAngle={90}
                endAngle={-270}
                isAnimationActive={false}
              >
                {data.map((d) => (
                  <Cell
                    key={d.key}
                    fill={d.color}
                    fillOpacity={active === null || active === d.key ? 1 : 0.3}
                    style={{
                      transition: "fill-opacity 140ms ease",
                      cursor: "pointer",
                      outline: "none",
                    }}
                    onMouseEnter={() => setActive(d.key)}
                  />
                ))}
              </Pie>
            ) : (
              <Pie
                data={[{ value: 1 }]}
                dataKey="value"
                innerRadius="72%"
                outerRadius="100%"
                fill="#e4e4e7"
                stroke="none"
                isAnimationActive={false}
              />
            )}
          </PieChart>
        </ChartContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center px-4 text-center">
          {activeSlice ? (
            <>
              <span className="text-[1.375rem] font-medium leading-7 tracking-tight">
                {activeSlice.value}
              </span>
              <span className="text-[11px] leading-tight text-muted-foreground">
                {pct}% of open flags
              </span>
            </>
          ) : (
            <>
              <span className="text-[1.375rem] font-medium leading-7 tracking-tight">
                {total}
              </span>
              <span className="text-[11px] text-muted-foreground">
                open flags
              </span>
            </>
          )}
        </div>
      </div>
      <div
        className="flex min-w-0 flex-1 flex-col gap-1"
        onMouseLeave={() => setActive(null)}
      >
        {legend.map((s) => {
          const dimmed = active !== null && active !== s.key;
          return (
            <span
              key={s.key}
              className="flex cursor-default items-center gap-2 rounded-sm px-1.5 py-1 text-xs transition-colors duration-150 hover:bg-muted/60"
              style={{ opacity: dimmed ? 0.45 : 1, transition: "opacity 140ms ease" }}
              onMouseEnter={() =>
                setActive(countOf(s.key) > 0 ? s.key : null)
              }
            >
              <span
                className="size-2 flex-none rounded-pill"
                style={{ backgroundColor: s.color }}
                aria-hidden="true"
              />
              <span className="text-foreground/80">{s.label}</span>
              <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                {countOf(s.key)}
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
