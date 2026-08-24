import { useEffect, useState } from "react";
import {
  listProjects,
  projectListTitle,
  setStoredProjectId,
  type ProjectListItem,
} from "@/lib/projects-api";
import { Button } from "@/components/ui/button";
import { Loader2, Search } from "lucide-react";

type Props = {
  open: boolean;
  title: string;
  description: string;
  taskType?: string;
  creating?: boolean;
  onClose: () => void;
  onSelect: (project: ProjectListItem) => void;
  onCreateNew?: () => void;
};

function projectMatchesTask(project: ProjectListItem, taskType?: string): boolean {
  if (!taskType) return true;
  if (!project.task_type) return true;
  return project.task_type === taskType;
}

export function MarketplaceProjectDialog({
  open,
  title,
  description,
  taskType,
  creating = false,
  onClose,
  onSelect,
  onCreateNew,
}: Props) {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    void listProjects()
      .then((res) => setProjects(res.projects))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load projects"))
      .finally(() => setLoading(false));
  }, [open]);

  if (!open) return null;

  const filtered = projects.filter((p) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    const hay = [
      projectListTitle(p),
      p.name,
      p.id,
      p.task_type ?? "",
      p.subtitle ?? "",
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/50 p-4">
      <div className="w-full max-w-lg vd-panel shadow-xl">
        <div className="border-b border-border/60 px-6 py-5">
          <h3 className="text-lg font-bold text-foreground">{title}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
          {taskType && (
            <p className="mt-2 text-xs font-semibold text-primary">
              Requires project task type: {taskType.replace(/_/g, " ")}
            </p>
          )}
        </div>

        <div className="px-6 py-4">
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search projects…"
              className="w-full rounded-lg border border-border/60 py-2.5 pl-10 pr-4 text-sm focus:border-primary/40 focus:outline-none focus:ring-2 focus:ring-primary/15"
            />
          </div>

          {loading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading projects…
            </div>
          ) : error ? (
            <p className="py-8 text-center text-sm text-red-600">{error}</p>
          ) : filtered.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No projects found. Create a workspace in Discovery &amp; Projects first.
            </p>
          ) : (
            <div className="max-h-64 space-y-2 overflow-y-auto">
              {filtered.map((project) => {
                const compatible = projectMatchesTask(project, taskType);
                return (
                  <button
                    key={project.id}
                    type="button"
                    disabled={!compatible}
                    onClick={() => {
                      if (!compatible) return;
                      setStoredProjectId(project.id);
                      onSelect(project);
                    }}
                    className={`flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left transition-colors ${
                      compatible
                        ? "border-border/60 hover:border-primary/30 hover:bg-primary/5"
                        : "border-border/40 bg-muted/40 opacity-60 cursor-not-allowed"
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-foreground">
                        {projectListTitle(project)}
                      </p>
                      <p className="font-mono text-[11px] text-muted-foreground/70">{project.id}</p>
                      {project.task_type && (
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {project.task_type.replace(/_/g, " ")}
                        </p>
                      )}
                      {!compatible && taskType && (
                        <p className="mt-1 text-[11px] text-amber-700">
                          Task mismatch — create a new project instead
                        </p>
                      )}
                    </div>
                    <span
                      className={`text-xs font-semibold ${compatible ? "text-primary" : "text-muted-foreground/70"}`}
                    >
                      {compatible ? "Select" : "—"}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex justify-between gap-2 border-t border-border/60 px-6 py-4">
          {onCreateNew ? (
            <Button variant="secondary" onClick={onCreateNew} disabled={creating}>
              {creating ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating…
                </>
              ) : (
                "Create new project"
              )}
            </Button>
          ) : (
            <span />
          )}
          <Button variant="outline" onClick={onClose} disabled={creating}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}
