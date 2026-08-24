import { CheckCircle2, Coins } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCredits } from "@/hooks/use-credits";
import { activatePlan, type CreditPlan } from "@/lib/credits-api";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { useState } from "react";

const FALLBACK_PLANS: CreditPlan[] = [
  { id: "free", name: "Free", credits: 100, description: "Starter credits for pilots and demos." },
  { id: "starter", name: "Starter", credits: 500, description: "For small teams and pilot projects." },
  { id: "pro", name: "Professional", credits: 2000, description: "For production workloads and heavier usage." },
];

const REASON_LABELS: Record<string, string> = {
  signup_grant: "Signup grant",
  plan_activate: "Plan activated",
  vlm_analyze: "VLM chat",
  generate_config: "Generate config",
  pipeline_tune: "Pipeline tune",
  training_submit: "Training accepted",
  training_compute: "Training (Azure VM time)",
  inference_deploy: "Inference deploy",
  inference_predict: "Inference predict",
};

export default function BillingView() {
  const { addEvent, notify, setActivePlan } = useStore();
  const { account, loading, refresh, cost } = useCredits();
  const [busyPlan, setBusyPlan] = useState<string | null>(null);

  const plans = account?.plans?.length ? account.plans : FALLBACK_PLANS;
  const activePlan = account?.plan || "free";
  const balance = account?.balance ?? 0;

  const handleActivate = async (planId: string) => {
    if (planId === activePlan) return;
    setBusyPlan(planId);
    try {
      const result = await activatePlan(planId);
      setActivePlan(planId);
      addEvent("Plan activated", `Switched to ${planId.toUpperCase()} (+${result.granted} credits).`, "blue");
      notify(`+${result.granted} credits added · balance ${result.balance}`);
      await refresh();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not activate plan");
    } finally {
      setBusyPlan(null);
    }
  };

  const costRows = [
    { key: "vlm_analyze" as const, label: "VLM discovery chat" },
    { key: "generate_config" as const, label: "Generate project config" },
    { key: "pipeline_tune" as const, label: "Pipeline auto-tune" },
    { key: "training_submit" as const, label: "Training (Azure VM reserve / settle)" },
    { key: "inference_deploy" as const, label: "Deploy inference endpoint" },
    { key: "inference_predict" as const, label: "Run inference predict" },
  ];

  return (
    <div className="space-y-8">
      <div className="vd-hero relative overflow-hidden p-6">
        <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-amber-500/15 blur-2xl" />
        <div className="relative flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="vd-label mb-2 text-amber-800/70">Credit balance</div>
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-amber-500/15 text-amber-700">
                <Coins className="h-6 w-6" />
              </div>
              <div className="text-4xl font-semibold tracking-tight text-foreground">
                {loading && !account ? "—" : balance.toLocaleString()}
              </div>
              <span className="text-sm font-medium text-muted-foreground">credits</span>
            </div>
            <p className="mt-3 max-w-xl text-sm text-muted-foreground">
              Active plan: <span className="font-semibold capitalize text-foreground">{activePlan}</span>
              {" · "}Membership prices TBD — activate a default package to add credits.
              {account?.pricing?.credit_usd != null && (
                <>{" · "}1 credit ≈ ${Number(account.pricing.credit_usd).toFixed(2)} Azure cost</>
              )}
            </p>
          </div>
          <Button variant="outline" onClick={() => void refresh()} disabled={loading}>
            Refresh
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        {plans.map((plan) => {
          const isActive = activePlan === plan.id;
          const highlight = plan.id === "pro";
          return (
            <div
              key={plan.id}
              className={cn(
                "vd-panel relative overflow-hidden p-6 transition-all",
                highlight && "border-primary/30 shadow-lg shadow-primary/5 ring-1 ring-primary/10",
              )}
            >
              {isActive && (
                <div
                  className={cn(
                    "absolute right-0 top-0 rounded-bl-lg px-3 py-1 text-[10px] font-bold uppercase tracking-wider",
                    highlight ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary",
                  )}
                >
                  Active
                </div>
              )}
              <h3 className="mb-1 text-lg font-semibold text-foreground">{plan.name}</h3>
              <p className="mb-4 text-sm text-muted-foreground">{plan.description}</p>
              <div className="mb-1 text-3xl font-semibold tracking-tight text-foreground">
                {plan.credits.toLocaleString()}
                <span className="text-sm font-medium text-muted-foreground"> credits</span>
              </div>
              <p className="mb-6 text-xs text-muted-foreground/70">Payment step skipped for now</p>
              <ul className="mb-6 space-y-3 text-sm text-muted-foreground">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  Adds {plan.credits.toLocaleString()} credits when activated
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  Same plan cannot be activated twice
                </li>
              </ul>
              <Button variant={isActive ? "outline" : "default"} className="w-full" disabled={isActive || busyPlan === plan.id} onClick={() => void handleActivate(plan.id)}>
                {isActive ? "Current plan" : busyPlan === plan.id ? "Activating…" : `Activate ${plan.name}`}
              </Button>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="vd-panel p-6">
          <h3 className="mb-1 text-lg font-semibold text-foreground">Usage costs</h3>
          <p className="mb-4 text-xs text-muted-foreground">
            Mapped from Azure list rates
            {account?.pricing?.vm_size
              ? ` · train on ${account.pricing.vm_size} @ $${Number(account.pricing.vm_hourly_usd ?? 0).toFixed(3)}/hr`
              : ""}
            . Training is reserved at start and settled from real job duration.
          </p>
          <div className="space-y-2">
            {costRows.map((row) => (
              <div key={row.key} className="flex items-center justify-between rounded-xl border border-border/40 bg-muted/30 px-4 py-3">
                <div className="min-w-0 pr-3">
                  <span className="text-sm font-medium text-foreground/80">{row.label}</span>
                  {account?.pricing?.cost_notes?.[row.key] && (
                    <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{account.pricing.cost_notes[row.key]}</p>
                  )}
                </div>
                <span className="shrink-0 text-sm font-semibold text-foreground">
                  {row.key === "training_submit" ? "~" : ""}
                  {cost(row.key)} credits
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="vd-panel p-6">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Recent activity</h3>
          <div className="max-h-80 space-y-2 overflow-y-auto">
            {(account?.ledger || []).length === 0 && (
              <p className="text-sm text-muted-foreground">No credit activity yet.</p>
            )}
            {(account?.ledger || []).map((row) => (
              <div key={row.id} className="flex items-start justify-between gap-3 rounded-xl border border-border/40 px-3 py-2.5">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-foreground">{REASON_LABELS[row.reason] || row.reason}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {row.note || row.ref || row.created_at || ""}
                    {row.azure_cost_usd != null ? ` · ~$${Number(row.azure_cost_usd).toFixed(4)} Azure` : ""}
                  </div>
                </div>
                <div className={cn("shrink-0 text-sm font-semibold", row.delta >= 0 ? "text-emerald-600" : "text-foreground")}>
                  {row.delta >= 0 ? "+" : ""}
                  {row.delta}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
