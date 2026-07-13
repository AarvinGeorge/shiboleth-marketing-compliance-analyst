// meta: OpenFlagsDonut (dashboard hero, metrics overhaul 2026-07-13). Thin
// donut of ALL open flags across the portfolio, sliced by intersection tag
// in a FIXED order (unapproved_violation, drifted_but_compliant,
// needs_review, then a muted Other only when nonzero). Validated palette
// (binding, dataviz skill): #dc2626 / #d97706 / #5b74c2; 2px white gaps
// (paddingAngle + stroke); center shows the total with "open flags"; hover
// tooltip per slice (plain-English tag + count + percent); legend always
// visible with colored dot + label + count, all text in ink tokens (never
// colored text). shadcn Charts (Recharts) per spec §10.

"use client";

import { Cell, Pie, PieChart, Tooltip } from "recharts";
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
  // legend: the three named slices always; Other only when nonzero
  const legend = SLICES.filter(
    (s) => s.key !== "other" || countOf("other") > 0
  );

  return (
    <div className="flex items-center gap-7 rounded-md border border-border bg-surface px-6 py-4">
      <div className="relative size-[150px] flex-none">
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
                  <Cell key={d.key} fill={d.color} />
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
            {data.length > 0 ? (
              <Tooltip
                content={(props) => {
                  const { active, payload } = props as unknown as {
                    active?: boolean;
                    payload?: Array<{ name?: unknown; value?: unknown }>;
                  };
                  if (!active || !payload || payload.length === 0) return null;
                  const name = String(payload[0].name ?? "");
                  const count = Number(payload[0].value ?? 0);
                  const pct =
                    total > 0 ? Math.round((count / total) * 100) : 0;
                  return (
                    <div className="rounded-md border border-border bg-background px-2.5 py-1.5 text-xs shadow-sm">
                      <span className="font-medium">{name}</span>
                      <span className="text-muted-foreground">
                        {" "}
                        · {count} ({pct}%)
                      </span>
                    </div>
                  );
                }}
              />
            ) : null}
          </PieChart>
        </ChartContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[1.375rem] font-medium leading-7 tracking-tight">
            {total}
          </span>
          <span className="text-[11px] text-muted-foreground">open flags</span>
        </div>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {legend.map((s) => (
          <span key={s.key} className="flex items-center gap-2 text-xs">
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
        ))}
      </div>
    </div>
  );
}
