import { useMemo } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { cn } from "@/lib/utils";

export function MetricsAreaChart({
  data,
  dataKey,
  label,
  className,
  color = "hsl(var(--primary))",
}: {
  data: { step: number; value: number }[];
  dataKey?: string;
  label?: string;
  className?: string;
  color?: string;
}) {
  const chartData = useMemo(() => data, [data]);
  if (!chartData.length) return null;

  return (
    <div className={cn("rounded-xl border border-border/40 bg-card/90 p-4", className)}>
      {label && <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>}
      <div className="h-[120px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="metricFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="step" hide />
            <YAxis hide domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{
                borderRadius: 8,
                border: "1px solid hsl(var(--border))",
                background: "hsl(var(--card))",
                fontSize: 12,
              }}
            />
            <Area type="monotone" dataKey={dataKey ?? "value"} stroke={color} fill="url(#metricFill)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
