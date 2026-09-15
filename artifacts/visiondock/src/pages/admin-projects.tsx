import { useEffect, useState } from "react";
import { fetchAdminProjects, type AdminProject } from "@/lib/admin-api";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function AdminProjectsPage() {
  const [projects, setProjects] = useState<AdminProject[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void fetchAdminProjects()
      .then((res) => setProjects(res.projects))
      .catch((e) => toast.error(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">All projects</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Platform-wide project inventory (not limited to your account).
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border/70">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/40 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-semibold">Project</th>
                <th className="px-4 py-3 font-semibold">Owner</th>
                <th className="px-4 py-3 font-semibold">Task</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold">Updated</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id} className="border-t border-border/60">
                  <td className="px-4 py-3">
                    <div className="font-medium">{p.name}</div>
                    <div className="font-mono text-[11px] text-muted-foreground">{p.id}</div>
                    {p.marketplace_dataset && (
                      <div className="mt-0.5 text-[11px] text-primary">{p.marketplace_dataset}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs">{p.owner_email || "—"}</td>
                  <td className="px-4 py-3 text-xs capitalize">
                    {(p.detected_task || "—").replace(/_/g, " ")}
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-xs">{p.status || "—"}</div>
                    <div className="text-[11px] text-muted-foreground">
                      train: {p.training_status || "—"} · inf: {p.inference_status || "—"}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {p.updated_at ? new Date(p.updated_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
              {projects.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">
                    No projects yet.
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
