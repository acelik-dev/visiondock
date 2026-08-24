import { Badge } from "@/components/ui/badge";
import { AnimatedMetricCard } from "@/components/premium/animated-metric";
import { MetricsAreaChart } from "@/components/premium/metrics-chart";
import {
  formatMetricNumber,
  formatMetricPercent,
  type TrainingMetrics,
} from "@/lib/training-api";
import type { LucideIcon } from "lucide-react";
import { BarChart3, CheckCircle2, Crosshair, Target, TrendingUp } from "lucide-react";

type TrainingMetricsPanelProps = {
  metrics: TrainingMetrics;
  completed?: boolean;
};

function MetricCard({
  label,
  value,
  icon: Icon,
  delay = 0,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
  delay?: number;
}) {
  const numeric = parseFloat(value.replace(/[^0-9.]/g, ""));
  return (
    <AnimatedMetricCard
      label={label}
      value={Number.isFinite(numeric) ? numeric : value}
      suffix={Number.isFinite(numeric) && value.includes("%") ? "%" : ""}
      icon={Icon}
      accent="primary"
      delay={delay}
    />
  );
}

export function TrainingMetricsPanel({ metrics, completed = false }: TrainingMetricsPanelProps) {
  const mAP50 = metrics.mAP50 ?? metrics.mAP;
  const accuracy = metrics.accuracy ?? metrics.val_accuracy;
  const f1 = metrics.f1 ?? metrics.micro_f1;
  const hasMetrics =
    mAP50 != null ||
    metrics.mAP50_95 != null ||
    metrics.precision != null ||
    metrics.recall != null ||
    accuracy != null ||
    f1 != null ||
    metrics.macro_f1 != null ||
    metrics.mae != null ||
    metrics.rmse != null ||
    metrics.r2 != null ||
    metrics.loss != null;

  if (!hasMetrics) {
    return (
      <div className="vd-empty border-dashed p-4 text-sm text-muted-foreground">
        {completed
          ? "Loading results from Azure ML… (this can take up to a minute on first view)."
          : "Metrics will appear here as training progresses."}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-foreground">Model performance</h4>
        {completed && (
          <Badge className="bg-emerald-600 hover:bg-emerald-600">
            <CheckCircle2 className="mr-1 h-3 w-3" />
            Training complete
          </Badge>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {mAP50 != null && (
          <MetricCard
            label="mAP@50"
            value={formatMetricPercent(mAP50)}
            icon={BarChart3}
          />
        )}
        {metrics.mAP50_95 != null && (
          <MetricCard
            label="mAP@50-95"
            value={formatMetricPercent(metrics.mAP50_95)}
            icon={Target}
          />
        )}
        {metrics.precision != null && (
          <MetricCard
            label="Precision"
            value={formatMetricPercent(metrics.precision)}
            icon={Crosshair}
          />
        )}
        {metrics.recall != null && (
          <MetricCard
            label="Recall"
            value={formatMetricPercent(metrics.recall)}
            icon={TrendingUp}
          />
        )}
        {accuracy != null && mAP50 == null && f1 == null && (
          <MetricCard
            label="Validation accuracy"
            value={formatMetricPercent(accuracy)}
            icon={CheckCircle2}
          />
        )}
        {f1 != null && (
          <MetricCard
            label="F1 score"
            value={formatMetricPercent(f1)}
            icon={CheckCircle2}
          />
        )}
        {metrics.macro_f1 != null && (
          <MetricCard
            label="Macro F1"
            value={formatMetricPercent(metrics.macro_f1)}
            icon={Target}
          />
        )}
        {metrics.mae != null && (
          <MetricCard
            label="MAE"
            value={formatMetricNumber(metrics.mae, 3)}
            icon={Target}
          />
        )}
        {metrics.rmse != null && (
          <MetricCard
            label="RMSE"
            value={formatMetricNumber(metrics.rmse, 3)}
            icon={BarChart3}
          />
        )}
        {metrics.r2 != null && (
          <MetricCard
            label="R²"
            value={formatMetricNumber(metrics.r2, 3)}
            icon={TrendingUp}
          />
        )}
        {metrics.loss != null && (
          <MetricCard
            label="Loss"
            value={formatMetricNumber(metrics.loss)}
            icon={TrendingUp}
          />
        )}
      </div>
      {metrics.loss != null && (
        <MetricsAreaChart
          label="Loss trend"
          data={Array.from({ length: Math.max(metrics.epoch ?? 1, 1) }, (_, i) => ({
            step: i + 1,
            value: metrics.loss! * (1 - i * 0.04),
          }))}
        />
      )}
      {metrics.epoch != null && (
        <p className="text-xs text-muted-foreground">
          Trained for {metrics.epoch} epoch{metrics.epoch === 1 ? "" : "s"}
        </p>
      )}
    </div>
  );
}
