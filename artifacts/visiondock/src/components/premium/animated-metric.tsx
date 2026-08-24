import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

function useCountUp(target: number, duration = 800, enabled = true) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (!enabled || target === 0) {
      setValue(target);
      return;
    }
    let start: number | null = null;
    let raf = 0;
    const step = (ts: number) => {
      if (start === null) start = ts;
      const p = Math.min((ts - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(Math.round(target * eased));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, enabled]);
  return value;
}

export function AnimatedMetricCard({
  label,
  value,
  suffix = "",
  icon: Icon,
  accent = "primary",
  delay = 0,
}: {
  label: string;
  value: number | string;
  suffix?: string;
  icon: LucideIcon;
  accent?: "primary" | "emerald" | "amber" | "violet" | "cyan";
  delay?: number;
}) {
  const numeric = typeof value === "number" ? value : parseInt(String(value).replace(/\D/g, ""), 10) || 0;
  const display = typeof value === "number" ? useCountUp(numeric) : value;

  const accents = {
    primary: "from-primary/20 to-primary/5 text-primary",
    emerald: "from-emerald-500/20 to-emerald-500/5 text-emerald-600",
    amber: "from-amber-500/20 to-amber-500/5 text-amber-600",
    violet: "from-violet-500/20 to-violet-500/5 text-violet-600",
    cyan: "from-cyan-500/20 to-cyan-500/5 text-cyan-600",
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
      className="relative overflow-hidden rounded-2xl border border-border/40 bg-card/90 p-5 shadow-sm backdrop-blur-sm"
    >
      <div className={cn("absolute inset-0 bg-gradient-to-br opacity-60", accents[accent])} />
      <div className="relative">
        <div className="mb-3 flex items-center gap-2">
          <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br", accents[accent])}>
            <Icon className="h-4 w-4" />
          </div>
          <span className="text-sm font-medium text-muted-foreground">{label}</span>
        </div>
        <div className="text-3xl font-semibold tracking-tight text-foreground tabular-nums">
          {display}
          {suffix}
        </div>
      </div>
    </motion.div>
  );
}

export function MetricSparkline({
  data,
  color = "hsl(var(--primary))",
}: {
  data: number[];
  color?: string;
}) {
  if (!data.length) return null;
  const max = Math.max(...data, 1);
  const w = 120;
  const h = 32;
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1 || 1)) * w;
      const y = h - (v / max) * h;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg width={w} height={h} className="opacity-80">
      <polyline fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" points={points} />
    </svg>
  );
}
