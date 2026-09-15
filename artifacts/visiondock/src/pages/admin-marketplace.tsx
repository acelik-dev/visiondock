import { useEffect, useState } from "react";
import { fetchAdminMarketplace, type AdminMarketplace } from "@/lib/admin-api";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function AdminMarketplacePage() {
  const [data, setData] = useState<AdminMarketplace | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void fetchAdminMarketplace()
      .then(setData)
      .catch((e) => toast.error(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Marketplace catalog</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Datasets and models currently published in the library.
          {data?.updated_at ? ` Updated ${new Date(data.updated_at).toLocaleString()}.` : ""}
        </p>
      </div>

      {loading || !data ? (
        <div className="flex justify-center py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Chip label="Datasets" value={data.dataset_count} />
            <Chip label="Models" value={data.model_count} />
            <Chip label="Industries covered" value={Object.keys(data.by_industry).length} />
            <Chip label="Task types" value={Object.keys(data.by_task).length} />
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold">By industry</h3>
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.by_industry)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => (
                  <span
                    key={k}
                    className="rounded-lg border border-border/60 bg-muted/40 px-2.5 py-1 text-xs font-medium"
                  >
                    {k}: {v}
                  </span>
                ))}
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-border/70">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted/40 text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-semibold">Dataset</th>
                  <th className="px-4 py-3 font-semibold">Task</th>
                  <th className="px-4 py-3 font-semibold">Images</th>
                  <th className="px-4 py-3 font-semibold">Industries</th>
                </tr>
              </thead>
              <tbody>
                {data.datasets.map((d) => (
                  <tr key={d.id} className="border-t border-border/60">
                    <td className="px-4 py-3">
                      <div className="font-medium">{d.name}</div>
                      <div className="font-mono text-[11px] text-muted-foreground">{d.id}</div>
                    </td>
                    <td className="px-4 py-3 text-xs capitalize">{d.task_type.replace(/_/g, " ")}</td>
                    <td className="px-4 py-3">{(d.image_count || 0).toLocaleString()}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {(d.industries || []).join(", ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function Chip({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-border/60 bg-muted/30 px-4 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}
