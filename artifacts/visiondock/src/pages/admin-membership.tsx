import { useEffect, useState } from "react";
import { fetchAdminBilling, saveAdminBilling, type AdminBillingConfig } from "@/lib/admin-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function AdminMembershipPage() {
  const [cfg, setCfg] = useState<AdminBillingConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void fetchAdminBilling()
      .then(setCfg)
      .catch((e) => toast.error(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    if (!cfg) return;
    setSaving(true);
    try {
      const next = await saveAdminBilling({ plans: cfg.plans });
      setCfg(next);
      toast.success("Membership plans saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading || !cfg) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }

  const planIds = Object.keys(cfg.plans).sort();

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Membership plans</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Edit plan names, included credits, and optional USD prices shown in Billing.
        </p>
      </div>

      <div className="space-y-4">
        {planIds.map((pid) => {
          const plan = cfg.plans[pid];
          return (
            <div key={pid} className="rounded-xl border border-border/70 p-5">
              <div className="mb-4 flex items-center justify-between">
                <div className="font-mono text-xs uppercase tracking-wider text-muted-foreground">{pid}</div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1.5 text-sm">
                  <span className="font-medium">Display name</span>
                  <Input
                    value={plan.name || ""}
                    onChange={(e) =>
                      setCfg({
                        ...cfg,
                        plans: { ...cfg.plans, [pid]: { ...plan, name: e.target.value } },
                      })
                    }
                  />
                </label>
                <label className="space-y-1.5 text-sm">
                  <span className="font-medium">Credits on activate</span>
                  <Input
                    type="number"
                    value={plan.credits ?? 0}
                    onChange={(e) =>
                      setCfg({
                        ...cfg,
                        plans: {
                          ...cfg.plans,
                          [pid]: { ...plan, credits: Number(e.target.value) },
                        },
                      })
                    }
                  />
                </label>
                <label className="space-y-1.5 text-sm sm:col-span-2">
                  <span className="font-medium">Description</span>
                  <Input
                    value={plan.description || ""}
                    onChange={(e) =>
                      setCfg({
                        ...cfg,
                        plans: {
                          ...cfg.plans,
                          [pid]: { ...plan, description: e.target.value },
                        },
                      })
                    }
                  />
                </label>
                <label className="space-y-1.5 text-sm">
                  <span className="font-medium">Price USD (optional)</span>
                  <Input
                    type="number"
                    step="0.01"
                    value={plan.price_usd ?? ""}
                    placeholder="TBD"
                    onChange={(e) =>
                      setCfg({
                        ...cfg,
                        plans: {
                          ...cfg.plans,
                          [pid]: {
                            ...plan,
                            price_usd: e.target.value === "" ? null : Number(e.target.value),
                          },
                        },
                      })
                    }
                  />
                </label>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex justify-end">
        <Button onClick={() => void save()} disabled={saving}>
          {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          Save membership plans
        </Button>
      </div>
    </div>
  );
}
