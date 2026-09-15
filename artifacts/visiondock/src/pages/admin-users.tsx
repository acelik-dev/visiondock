import { useCallback, useEffect, useState } from "react";
import {
  adjustUserCredits,
  fetchAdminUsers,
  setUserPlan,
  type AdminUser,
} from "@/lib/admin-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2, Search, Shield } from "lucide-react";
import { toast } from "sonner";

const PLANS = ["free", "starter", "pro"];

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async (query?: string) => {
    setLoading(true);
    try {
      const res = await fetchAdminUsers(query);
      setUsers(res.users);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const adjust = async (user: AdminUser, delta: number) => {
    const note = window.prompt(
      `Adjust credits for ${user.email} by ${delta > 0 ? "+" : ""}${delta}. Optional note:`,
      delta > 0 ? "Admin grant" : "Admin revoke",
    );
    if (note === null) return;
    setBusyId(user.id);
    try {
      const res = await adjustUserCredits(user.id, delta, note || undefined);
      toast.success(`${user.email} → ${res.data.balance} credits`);
      await load(q);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Adjust failed");
    } finally {
      setBusyId(null);
    }
  };

  const changePlan = async (user: AdminUser, planId: string) => {
    if (planId === user.active_plan) return;
    const grant = window.confirm(
      `Set ${user.email} to plan "${planId}" and grant that plan's credits?`,
    );
    setBusyId(user.id);
    try {
      const res = await setUserPlan(user.id, planId, grant);
      toast.success(`${user.email} → ${res.data.plan} (${res.data.balance} credits)`);
      await load(q);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Plan update failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Users</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Accounts, balances, and membership assignment.
        </p>
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void load(q);
        }}
      >
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search email or name…"
            className="pl-9"
          />
        </div>
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>

      {loading ? (
        <div className="flex justify-center py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border/70">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/40 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-semibold">User</th>
                <th className="px-4 py-3 font-semibold">Plan</th>
                <th className="px-4 py-3 font-semibold">Credits</th>
                <th className="px-4 py-3 font-semibold">Last login</th>
                <th className="px-4 py-3 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-border/60">
                  <td className="px-4 py-3">
                    <div className="font-medium text-foreground">{u.email}</div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      {u.name || "—"}
                      {u.is_admin && (
                        <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 text-emerald-700">
                          <Shield className="h-3 w-3" /> admin
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <select
                      className="h-8 rounded-md border border-border bg-background px-2 text-xs capitalize"
                      value={u.active_plan}
                      disabled={busyId === u.id}
                      onChange={(e) => void changePlan(u, e.target.value)}
                    >
                      {PLANS.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3 font-semibold">{u.credits_balance.toLocaleString()}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {u.last_login ? new Date(u.last_login).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      <Button size="sm" variant="outline" disabled={busyId === u.id} onClick={() => void adjust(u, 100)}>
                        +100
                      </Button>
                      <Button size="sm" variant="outline" disabled={busyId === u.id} onClick={() => void adjust(u, 500)}>
                        +500
                      </Button>
                      <Button size="sm" variant="ghost" disabled={busyId === u.id} onClick={() => void adjust(u, -50)}>
                        −50
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">
                    No users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
