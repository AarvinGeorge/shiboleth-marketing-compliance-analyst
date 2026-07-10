// meta: tiny sparkline for MetricCard slots and product cards. shadcn/ui
// Charts (Recharts v3) only, per DESIGN.md; no axes, no grid, muted gray
// stroke (blue stays reserved for interaction and AI activity). Kinds: "area"
// (hero portfolio trend) and "line" (per-run product score).

"use client";

import { Area, AreaChart, Line, LineChart, YAxis } from "recharts";
import { ChartContainer, type ChartConfig } from "@/components/ui/chart";

const chartConfig = {
  v: { label: "Score", color: "#d4d4d4" },
} satisfies ChartConfig;

export function Sparkline({
  data,
  kind = "line",
  className,
}: {
  data: number[];
  kind?: "area" | "line";
  className?: string;
}) {
  const rows = data.map((v, i) => ({ i, v }));

  return (
    <ChartContainer
      config={chartConfig}
      className={className ?? "h-6 w-full max-w-24"}
    >
      {kind === "area" ? (
        <AreaChart data={rows} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
          <Area
            dataKey="v"
            type="monotone"
            stroke="var(--color-v)"
            strokeWidth={1.5}
            fill="var(--color-v)"
            fillOpacity={0.25}
            isAnimationActive={false}
          />
        </AreaChart>
      ) : (
        <LineChart data={rows} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
          <Line
            dataKey="v"
            type="monotone"
            stroke="var(--color-v)"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      )}
    </ChartContainer>
  );
}
