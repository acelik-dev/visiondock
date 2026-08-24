import { useCallback, useEffect, useState } from "react";
import type { TaskType } from "@/lib/project-spec";
import {
  fetchMarketplaceDatasets,
  startProjectFromDataset,
  MARKETPLACE_TASK_TYPES,
  taskTypeLabel,
  type MarketplaceDataset,
} from "@/lib/marketplace-api";
import { clearForceNewProject, setStoredProjectId } from "@/lib/projects-api";
import { getDatasetCopy, DATASET_LIBRARY_INTRO } from "@/lib/marketplace-copy";
import {
  MarketplaceItemExplainer,
  MarketplacePageIntro,
  MarketplaceTaskGuide,
} from "@/components/marketplace-guide";
import { MarketplaceHoverDetail } from "@/components/marketplace-hover-detail";
import { FilterPills, SearchField } from "@/components/premium/ui-primitives";
import { FancyEmpty } from "@/components/premium/fancy-empty";
import { SpotlightCard } from "@/components/premium/spotlight-card";
import { useStore } from "@/lib/store";
import { taskBadgeClass } from "@/lib/task-colors";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { AlertCircle, Database, HardDrive, Layers, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

function DatasetCard({
  dataset,
  importing,
  onUse,
}: {
  dataset: MarketplaceDataset;
  importing: boolean;
  onUse: () => void;
}) {
  const copy = getDatasetCopy(dataset.id, dataset.name);

  return (
    <MarketplaceHoverDetail
      kind="dataset"
      itemId={dataset.id}
      name={dataset.name}
      taskType={dataset.task_type}
      classes={dataset.classes ?? []}
      imageCount={dataset.image_count}
      classCount={dataset.class_count}
      license={dataset.license}
      format={dataset.format}
    >
      <SpotlightCard className="flex h-full flex-col">
        <div className="flex h-full flex-col">
        <div className="mb-4">
          <h3 className="mb-2 text-base font-semibold text-foreground">{dataset.name}</h3>
          <span
            className={cn(
              "inline-flex rounded-lg border px-3 py-1 text-[11px] font-bold uppercase tracking-wider",
              taskBadgeClass(dataset.task_type),
            )}
          >
            {taskTypeLabel(dataset.task_type)}
          </span>
        </div>

        <MarketplaceItemExplainer headline={copy.headline} whatItIs={copy.whatItIs} goodFor={copy.goodFor} />

        <div className="mb-5 grid grid-cols-2 gap-3">
          <div className="rounded-lg bg-muted/50 px-3 py-2.5">
            <div className="mb-1 flex items-center gap-1.5">
              <Database className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-[10px] font-semibold uppercase text-muted-foreground">Photos</span>
            </div>
            <div className="text-sm font-bold text-foreground">{(dataset.image_count ?? 0).toLocaleString()}</div>
          </div>
          <div className="rounded-lg bg-primary/8 px-3 py-2.5">
            <div className="mb-1 flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5 text-primary" />
              <span className="text-[10px] font-semibold uppercase text-primary">Categories</span>
            </div>
            <div className="text-sm font-bold text-foreground">{dataset.class_count || "—"}</div>
          </div>
          <div className="col-span-2 rounded-lg bg-emerald-500/8 px-3 py-2.5">
            <div className="mb-1 flex items-center gap-1.5">
              <HardDrive className="h-3.5 w-3.5 text-emerald-600" />
              <span className="text-[10px] font-semibold uppercase text-emerald-600">Size</span>
            </div>
            <div className="text-sm font-bold text-foreground">{dataset.size_label}</div>
          </div>
        </div>

        <p className="mb-4 text-[11px] text-muted-foreground">{copy.startProjectHint}</p>

        <Button className="mt-auto w-full shadow-md shadow-primary/10" disabled={importing} onClick={onUse}>
          {importing ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Starting project…
            </>
          ) : (
            <>
              <Sparkles className="mr-2 h-4 w-4" />
              Start project
            </>
          )}
        </Button>
        </div>
      </SpotlightCard>
    </MarketplaceHoverDetail>
  );
}

export default function DatasetsView() {
  const {
    setActiveProject,
    setCurrentView,
    setWorkflowStep,
    setDatasetUploaded,
    setPendingNewProject,
    setMarketplaceSpecBootstrap,
  } = useStore();
  const [datasets, setDatasets] = useState<MarketplaceDataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedTask, setSelectedTask] = useState<TaskType | "all">("all");
  const [importingId, setImportingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const task = selectedTask === "all" ? undefined : selectedTask;
      const res = await fetchMarketplaceDatasets(task);
      setDatasets(Array.isArray(res.datasets) ? res.datasets : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load marketplace");
    } finally {
      setLoading(false);
    }
  }, [selectedTask]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = (datasets ?? []).filter((d) => {
    const q = searchTerm.toLowerCase();
    if (!q) return true;
    return (
      d.name.toLowerCase().includes(q) ||
      (d.description ?? "").toLowerCase().includes(q) ||
      d.task_type.includes(q)
    );
  });

  const handleUse = async (item: MarketplaceDataset) => {
    setImportingId(item.id);
    try {
      clearForceNewProject();
      setPendingNewProject(false);
      const result = await startProjectFromDataset(item.id);
      const projectId = result.project_id || String((result.project as { id?: string })?.id ?? "");
      if (!projectId) throw new Error("Project was not created");
      setStoredProjectId(projectId);
      setActiveProject(projectId, item.name);
      setMarketplaceSpecBootstrap(
        result.spec ?? {
          project_name: item.name,
          task_type: item.task_type,
          classes: item.classes,
          recommended_model:
            item.task_type === "classification" ||
            item.task_type === "multi_label" ||
            item.task_type === "regression"
              ? "efficientnet_b0"
              : "yolov8n",
          description: item.description,
          target_name: item.target_name ?? "target",
          target_unit: item.target_unit ?? "",
        },
      );
      setWorkflowStep(3);
      setCurrentView("projects");
      setDatasetUploaded(true);
      toast.success(`${item.name} is ready — pipeline will be configured from library images.`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start project");
    } finally {
      setImportingId(null);
    }
  };

  const filterOptions = [{ id: "all" as const, label: "All tasks" }, ...MARKETPLACE_TASK_TYPES.map((t) => ({ id: t.id, label: t.label }))];

  return (
    <div className="space-y-6">
      <MarketplacePageIntro intro={DATASET_LIBRARY_INTRO} />
      <MarketplaceTaskGuide taskType={selectedTask} />

      <div className="flex items-center gap-2">
        <Layers className="mr-1 h-4 w-4 text-muted-foreground" />
        <FilterPills options={filterOptions} value={selectedTask} onChange={(v) => setSelectedTask(v as TaskType | "all")} />
      </div>

      <SearchField value={searchTerm} onChange={setSearchTerm} placeholder="Search datasets…" />

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-20 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
          Loading marketplace catalog…
        </div>
      ) : error ? (
        <div className="flex items-center gap-3 rounded-xl border border-destructive/20 bg-destructive/8 px-5 py-4 text-destructive">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <div>
            <p className="font-semibold">Could not load marketplace</p>
            <p className="mt-0.5 text-sm">{error}</p>
            <Button variant="outline" size="sm" className="mt-3" onClick={() => void load()}>
              Retry
            </Button>
          </div>
        </div>
      ) : filtered.length === 0 ? (
        <FancyEmpty icon={Database} title="No datasets match your filters" description="Try a different task type or search term." />
      ) : (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((dataset) => (
            <DatasetCard
              key={dataset.id}
              dataset={dataset}
              importing={importingId === dataset.id}
              onUse={() => void handleUse(dataset)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
