import { useEffect, useState } from "react";
import { fetchAdminSystem, type AdminSystem } from "@/lib/admin-api";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function AdminSystemPage() {
  const [data, setData] = useState<AdminSystem | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void fetchAdminSystem()
      .then(setData)
      .catch((e) => toast.error(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  if (loading || !data) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }

  const rows: Array<[string, string]> = [
    ["Storage backend", data.storage_backend],
    ["Storage container", data.storage_container],
    ["Blob store", data.blob_store_type],
    ["Azure resource group", data.azure_resource_group || "—"],
    ["Azure ML workspace", data.azure_ml_workspace || "—"],
    ["Public API URL", data.public_api_url || "—"],
    ["Skills catalog version", data.skills_version || "—"],
    [
      "Skills updated",
      data.skills_catalog_updated_at
        ? new Date(data.skills_catalog_updated_at).toLocaleString()
        : "—",
    ],
    ["AUTH_USERNAME fallback", data.auth_username_fallback ? "yes" : "no"],
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">System</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Runtime configuration visible to admins. Secrets are never shown.
        </p>
      </div>

      <div className="overflow-hidden rounded-xl border border-border/70">
        <table className="w-full text-sm">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k} className="border-t border-border/60 first:border-0">
                <td className="w-1/3 bg-muted/30 px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {k}
                </td>
                <td className="px-4 py-3 font-mono text-xs">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold">Admin email allowlist</h3>
        <div className="flex flex-wrap gap-2">
          {data.admin_emails.length === 0 ? (
            <span className="text-sm text-muted-foreground">No ADMIN_EMAILS configured.</span>
          ) : (
            data.admin_emails.map((e) => (
              <span
                key={e}
                className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-800"
              >
                {e}
              </span>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
