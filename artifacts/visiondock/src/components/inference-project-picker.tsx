import { useMemo, useState } from "react";
import type { ProjectListItem } from "@/lib/projects-api";
import { projectListTitle } from "@/lib/projects-api";
import { Button } from "@/components/ui/button";
import {
  ArrowRight,
  CheckCircle2,
  Cloud,
  Loader2,
  Search,
  Server,
  XCircle,
} from "lucide-react";

type Props = {
  projects: ProjectListItem[];
  loading?: boolean;
  onSelect: (project: ProjectListItem) => void;
};

function inferenceLabel(status?: string) {
  switch (status) {
    case "deployed":
      return { text: "Live", className: "bg-emerald-100 text-emerald-800 border-emerald-200" };
    case "deploying":
      return { text: "Deploying", className: "bg-primary/12 text-primary border-primary/20" };
    case "failed":
      return { text: "Deploy failed", className: "bg-red-100 text-red-800 border-red-200" };
    default:
      return { text: "Not deployed", className: "bg-muted/60 text-muted-foreground border-border/60" };
  }
}

function trainingLabel(status?: string) {
  if (!status) return { text: "No training", className: "text-muted-foreground/70" };
  if (status === "Completed") return { text: "Training complete", className: "text-emerald-700" };
  if (status === "Failed") return { text: "Training failed", className: "text-red-700" };
  if (status === "Running") return { text: "Training running", className: "text-primary" };
  return { text: status, className: "text-muted-foreground" };
}

export function InferenceProjectPicker({ projects, loading, onSelect }: Props) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projects;
    return projects.filter((p) => {
      const title = projectListTitle(p).toLowerCase();
      const hay = [title, p.name, p.id, p.subtitle ?? "", p.task_type ?? "", p.dataset_name ?? ""]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [projects, query]);

  const readyCount = projects.filter((p) => p.inference_status === "deployed").length;
  const trainableCount = projects.filter((p) => p.has_model && p.inference_status !== "deployed").length;

  return (
    <div className="vd-panel shadow-sm overflow-hidden">
      <div className="border-b border-border/60 bg-gradient-to-r from-muted/30 to-card px-6 py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-foreground">Inference projects</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              All workspaces with trained models — live endpoints, deploy, or edge export.
            </p>
          </div>
          <div className="flex gap-3 text-center">
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2">
              <p className="text-lg font-bold text-emerald-800">{readyCount}</p>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-emerald-600">Live</p>
            </div>
            <div className="rounded-lg border border-primary/20 bg-primary/8 px-4 py-2">
              <p className="text-lg font-bold text-primary">{trainableCount}</p>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-primary">Ready</p>
            </div>
          </div>
        </div>

        <div className="relative mt-5 max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name or project ID…"
            className="w-full rounded-lg border border-border/50 bg-card py-2.5 pl-10 pr-4 text-sm focus:border-primary/40 focus:outline-none focus:ring-2 focus:ring-primary/15"
          />
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading projects…
        </div>
      ) : filtered.length === 0 ? (
        <div className="px-6 py-16 text-center">
          <Cloud className="mx-auto h-10 w-10 text-muted-foreground/50" />
          <p className="mt-3 text-sm font-medium text-foreground/80">
            {projects.length === 0 ? "No projects yet" : "No matching projects"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {projects.length === 0
              ? "Create a workspace in Discovery & Projects and complete training first."
              : "Try a different search term."}
          </p>
        </div>
      ) : (
        <div className="divide-y divide-slate-100">
          {filtered.map((project) => {
            const inf = inferenceLabel(project.inference_status);
            const train = trainingLabel(project.training_status);
            return (
              <div
                key={project.id}
                className="flex flex-wrap items-center justify-between gap-4 px-6 py-4 hover:bg-muted/40/80 transition-colors"
              >
                <div className="flex min-w-0 items-center gap-4">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center vd-panel font-mono text-xs font-bold text-muted-foreground shadow-sm">
                    {project.id.replace("prj-", "").slice(0, 4)}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-foreground">
                      {projectListTitle(project)}
                    </p>
                    {project.subtitle && (
                      <p className="truncate text-xs text-muted-foreground mt-0.5">{project.subtitle}</p>
                    )}
                    <p className="font-mono text-[11px] text-muted-foreground/70 mt-0.5">{project.id}</p>
                    <p className={`mt-1 text-xs font-medium ${train.className}`}>
                      <Server className="mr-1 inline h-3 w-3" />
                      {train.text}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold ${inf.className}`}
                  >
                    {project.inference_status === "deployed" ? (
                      <CheckCircle2 className="h-3 w-3" />
                    ) : project.inference_status === "failed" ? (
                      <XCircle className="h-3 w-3" />
                    ) : (
                      <Cloud className="h-3 w-3" />
                    )}
                    {inf.text}
                  </span>

                  <Button
                    size="sm"
                    onClick={() => onSelect(project)}
                    className=""
                  >
                    {project.inference_status === "deployed"
                      ? "Test & manage"
                      : project.inference_status === "deploying"
                        ? "View status"
                        : project.has_model
                          ? "Deploy"
                          : "View"}
                    <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
