import { useCallback, useEffect, useState } from "react";
import type { TaskType } from "@/lib/project-spec";
import {
  fetchMarketplaceModels,
  formatMetric,
  startProjectFromModel,
  MARKETPLACE_TASK_TYPES,
  taskTypeLabel,
  type MarketplaceModel,
} from "@/lib/marketplace-api";
import { clearForceNewProject, setStoredProjectId } from "@/lib/projects-api";
import {
  displayModelTitle,
  getModelCopy,
  humanArchitecture,
  humanMetricLabel,
  MODEL_LIBRARY_INTRO,
} from "@/lib/marketplace-copy";
import {
  MarketplaceItemExplainer,
  MarketplacePageIntro,
  MarketplaceTaskGuide,
} from "@/components/marketplace-guide";
import { MarketplaceHoverDetail } from "@/components/marketplace-hover-detail";
import { FilterPills, MetricRow, SearchField } from "@/components/premium/ui-primitives";
import { FancyEmpty } from "@/components/premium/fancy-empty";
import { SpotlightCard } from "@/components/premium/spotlight-card";
import { useStore } from "@/lib/store";
import { taskBadgeClass } from "@/lib/task-colors";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { AlertCircle, Cpu, Layers, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

function ModelCard({
  model,
  importing,
  onUse,
}: {
  model: MarketplaceModel;
  importing: boolean;
  onUse: () => void;
}) {
  const copy = getModelCopy(model.id, model.name);
  const title = displayModelTitle(model);
  const metricKey = Object.keys(model.metrics ?? {})[0] ?? "metric";
  const metricLabel = humanMetricLabel(metricKey);

  return (
    <MarketplaceHoverDetail
      kind="model"
      itemId={model.id}
      name={title}
      taskType={model.task_type}
      classes={model.classes ?? []}
      license={model.license}
    >
      <SpotlightCard className="flex h-full flex-col">
        <div className="flex h-full flex-col">
        <div className="mb-4">
          <h3 className="mb-2 min-h-[2.75rem] text-base font-semibold leading-snug text-foreground">{title}</h3>
          <span
            className={cn(
              "inline-flex rounded-lg border px-3 py-1 text-[11px] font-bold uppercase tracking-wider",
              taskBadgeClass(model.task_type),
            )}
          >
            {taskTypeLabel(model.task_type)}
          </span>
        </div>

        <div className="flex flex-1 flex-col">
          <MarketplaceItemExplainer whatItIs={copy.whatItIs} goodFor={copy.goodFor} />

          <div className="mb-5 mt-auto space-y-2">
            <MetricRow label="Model type" value={humanArchitecture(model.architecture)} />
            <MetricRow label={`Reference ${metricLabel}`} value={formatMetric(model.metrics)} tone="success" />
            <MetricRow label="Photo size" value={model.input_resolution} tone="accent" />
          </div>

          <p className="mb-4 min-h-[2.5rem] text-[11px] leading-relaxed text-muted-foreground">{copy.startProjectHint}</p>

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
        </div>
      </SpotlightCard>
    </MarketplaceHoverDetail>
  );
}

export default function ModelsView() {
  const {
    setActiveProject,
    setCurrentView,
    setPendingNewProject,
    setMarketplaceSpecBootstrap,
    setWorkflowStep,
    setDatasetUploaded,
  } = useStore();
  const [models, setModels] = useState<MarketplaceModel[]>([]);
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
      const res = await fetchMarketplaceModels(task);
      setModels(Array.isArray(res.models) ? res.models : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load marketplace");
    } finally {
      setLoading(false);
    }
  }, [selectedTask]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = (models ?? []).filter((m) => {
    const q = searchTerm.toLowerCase();
    if (!q) return true;
    return (
      m.name.toLowerCase().includes(q) ||
      (m.description ?? "").toLowerCase().includes(q) ||
      (m.architecture ?? "").toLowerCase().includes(q)
    );
  });

  const handleUse = async (item: MarketplaceModel) => {
    setImportingId(item.id);
    try {
      clearForceNewProject();
      setPendingNewProject(false);
      const result = await startProjectFromModel(item.id);
      const projectId = result.project_id || String((result.project as { id?: string })?.id ?? "");
      if (!projectId) throw new Error("Project was not created");
      setStoredProjectId(projectId);
      setActiveProject(projectId, displayModelTitle(item));
      setMarketplaceSpecBootstrap(
        result.spec ?? {
          project_name: item.name,
          task_type: item.task_type,
          // Customer's labels — never seed with catalog demo classes.
          classes: [],
          recommended_model: item.architecture || "efficientnet_b0",
          description: item.description,
          target_name: item.task_type === "regression" ? (item.target_name ?? "target") : "",
          target_unit: item.task_type === "regression" ? (item.target_unit ?? "") : "",
        },
      );
      setDatasetUploaded(false);
      setWorkflowStep(2);
      setCurrentView("projects");
      toast.success(
        item.task_type === "classification"
          ? `${displayModelTitle(item)} — add your own group names, then upload photos.`
          : `${displayModelTitle(item)} — upload your labeled data in Step 2, then train.`,
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start project");
    } finally {
      setImportingId(null);
    }
  };

  const filterOptions = [{ id: "all" as const, label: "All tasks" }, ...MARKETPLACE_TASK_TYPES.map((t) => ({ id: t.id, label: t.label }))];

  return (
    <div className="space-y-6">
      <MarketplacePageIntro intro={MODEL_LIBRARY_INTRO} />
      <MarketplaceTaskGuide taskType={selectedTask} />

      <div className="flex items-center gap-2">
        <Cpu className="mr-1 h-4 w-4 text-muted-foreground" />
        <FilterPills options={filterOptions} value={selectedTask} onChange={(v) => setSelectedTask(v as TaskType | "all")} />
      </div>

      <SearchField value={searchTerm} onChange={setSearchTerm} placeholder="Search models…" />

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-20 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
          Loading model catalog…
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
        <FancyEmpty icon={Layers} title="No models match your filters" description="Try a different task type or search term." />
      ) : (
        <div className="grid grid-cols-1 items-stretch gap-6 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((model) => (
            <ModelCard key={model.id} model={model} importing={importingId === model.id} onUse={() => void handleUse(model)} />
          ))}
        </div>
      )}
    </div>
  );
}
