import { useCallback, useEffect, useState } from "react";
import { fetchAdminLedger, type AdminLedgerEntry } from "@/lib/admin-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2, Search } from "lucide-react";
import { toast } from "sonner";

export default function AdminLedgerPage() {
  const [entries, setEntries] = useState<AdminLedgerEntry[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (query?: string) => {
    setLoading(true);
    try {
      const res = await fetchAdminLedger(query);
      setEntries(res.entries);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load ledger");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Credit ledger</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          All credit grants, spends, refunds, and admin adjustments across users.
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
            placeholder="Filter by email, reason, or note…"
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
                <th className="px-4 py-3 font-semibold">When</th>
                <th className="px-4 py-3 font-semibold">User</th>
                <th className="px-4 py-3 font-semibold">Reason</th>
                <th className="px-4 py-3 font-semibold">Delta</th>
                <th className="px-4 py-3 font-semibold">Balance after</th>
                <th className="px-4 py-3 font-semibold">Note</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-t border-border/60">
                  <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                    {e.created_at ? new Date(e.created_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-3 text-xs">{e.email}</td>
                  <td className="px-4 py-3 font-mono text-xs">{e.reason}</td>
                  <td
                    className={`px-4 py-3 font-semibold ${e.delta >= 0 ? "text-emerald-700" : "text-destructive"}`}
                  >
                    {e.delta >= 0 ? "+" : ""}
                    {e.delta}
                  </td>
                  <td className="px-4 py-3">{e.balance_after}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground max-w-[220px] truncate">
                    {e.note || e.ref || "—"}
                  </td>
                </tr>
              ))}
              {entries.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                    No ledger entries.
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
