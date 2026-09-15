import { useEffect, useState } from "react";
import { fetchAdminBilling, saveAdminBilling, type AdminBillingConfig } from "@/lib/admin-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function AdminCreditsPage() {
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
      const next = await saveAdminBilling({
        credit_usd: cfg.credit_usd,
        platform_markup: cfg.platform_markup,
        action_credits: cfg.action_credits,
      });
      setCfg(next);
      toast.success("Credit settings saved");
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

  const actions = Object.keys(cfg.action_credits).sort();

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Credit settings</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Override action costs (credits charged per operation) and conversion rates.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="space-y-1.5 text-sm">
          <span className="font-medium">USD per credit</span>
          <Input
            type="number"
            step="0.001"
            value={cfg.credit_usd}
            onChange={(e) => setCfg({ ...cfg, credit_usd: Number(e.target.value) })}
          />
        </label>
        <label className="space-y-1.5 text-sm">
          <span className="font-medium">Platform markup</span>
          <Input
            type="number"
            step="0.01"
            value={cfg.platform_markup}
            onChange={(e) => setCfg({ ...cfg, platform_markup: Number(e.target.value) })}
          />
        </label>
      </div>

      <div className="overflow-hidden rounded-xl border border-border/70">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">Action</th>
              <th className="px-4 py-3 text-left font-semibold">Credits</th>
            </tr>
          </thead>
          <tbody>
            {actions.map((key) => (
              <tr key={key} className="border-t border-border/60">
                <td className="px-4 py-3 font-mono text-xs">{key}</td>
                <td className="px-4 py-3">
                  <Input
                    type="number"
                    className="h-9 w-28"
                    value={cfg.action_credits[key]}
                    onChange={(e) =>
                      setCfg({
                        ...cfg,
                        action_credits: {
                          ...cfg.action_credits,
                          [key]: Number(e.target.value),
                        },
                      })
                    }
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {cfg.updated_at ? `Last updated ${new Date(cfg.updated_at).toLocaleString()}` : "Using defaults"}
        </p>
        <Button onClick={() => void save()} disabled={saving}>
          {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          Save credit settings
        </Button>
      </div>
    </div>
  );
}
