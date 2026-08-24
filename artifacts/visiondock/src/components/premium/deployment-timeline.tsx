import { motion } from "framer-motion";
import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Step = {
  id: string;
  label: string;
  status: "pending" | "active" | "done" | "error";
  detail?: string;
};

export function DeploymentTimeline({ steps }: { steps: Step[] }) {
  return (
    <div className="space-y-0">
      {steps.map((step, i) => (
        <div key={step.id} className="relative flex gap-4 pb-6 last:pb-0">
          {i < steps.length - 1 && (
            <div
              className={cn(
                "absolute left-[15px] top-8 h-[calc(100%-1rem)] w-px",
                step.status === "done" ? "bg-emerald-500/50" : "bg-border",
              )}
            />
          )}
          <div className="relative z-10 mt-0.5">
            {step.status === "done" && (
              <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} className="text-emerald-500">
                <CheckCircle2 className="h-8 w-8" />
              </motion.div>
            )}
            {step.status === "active" && (
              <div className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-primary bg-primary/10">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
              </div>
            )}
            {step.status === "pending" && (
              <Circle className="h-8 w-8 text-muted-foreground/40" />
            )}
            {step.status === "error" && (
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                !
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1 pt-1">
            <p
              className={cn(
                "text-sm font-semibold",
                step.status === "active" && "text-primary",
                step.status === "done" && "text-foreground",
                step.status === "pending" && "text-muted-foreground",
              )}
            >
              {step.label}
            </p>
            {step.detail && <p className="mt-0.5 text-xs text-muted-foreground">{step.detail}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

export function GpuUtilBar({ percent, label = "GPU utilization" }: { percent: number; label?: string }) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <div className="rounded-xl border border-border/50 bg-card/90 p-4">
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="font-medium text-muted-foreground">{label}</span>
        <span className="font-semibold tabular-nums text-foreground">{clamped}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-cyan-500 via-primary to-violet-500"
          initial={{ width: 0 }}
          animate={{ width: `${clamped}%` }}
          transition={{ type: "spring", stiffness: 80, damping: 20 }}
        />
      </div>
    </div>
  );
}
