import { useCallback, useEffect, useState } from "react";
import { useLocation } from "wouter";
import { useStore } from "@/lib/store";
import { inferencePath, parseInferenceProjectId } from "@/lib/navigation";
import { InferenceCredentialsPanel } from "@/components/inference-credentials-panel";
import { InferenceProjectPicker } from "@/components/inference-project-picker";
import { InferenceTestPanel } from "@/components/inference-test-panel";
import {
  deployInference,
  edgeBundleUrl,
  fetchInferenceStatus,
  rotateInferenceApiKey,
  type InferenceStatusResponse,
} from "@/lib/inference-api";
import {
  fetchProject,
  listProjects,
  projectListTitle,
  setStoredProjectId,
  type ProjectListItem,
} from "@/lib/projects-api";
import { Cloud, Cpu, Download, RefreshCw, ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { announceCreditSpend, useCredits } from "@/hooks/use-credits";

export default function InferenceView() {
  const [location, navigate] = useLocation();
  const inferenceProjectId = parseInferenceProjectId(location);
  const { activeProjectId, addEvent, notify, setActiveProject } = useStore();
  const { account, canAfford, cost } = useCredits();
  const deployCost = cost("inference_deploy");
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [selected, setSelected] = useState<ProjectListItem | null>(null);
  const [status, setStatus] = useState<InferenceStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [deploying, setDeploying] = useState(false);

  const loadProjects = useCallback(async () => {
    setProjectsLoading(true);
    try {
      const data = await listProjects();
      setProjects(data.projects);
    } catch (e) {
      notify(e instanceof Error ? e.message : "Failed to load projects");
    } finally {
      setProjectsLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const handleSelectProject = useCallback(async (project: ProjectListItem) => {
    navigate(inferencePath(project.id));
    setSelected(project);
    setStatus(null);
    setStoredProjectId(project.id);
    setActiveProject(project.id, projectListTitle(project));
    try {
      await fetchProject(project.id);
    } catch {
      /* sidebar sync only */
    }
  }, [navigate, setActiveProject]);

  useEffect(() => {
    if (!inferenceProjectId) {
      setSelected(null);
      setStatus(null);
      return;
    }
    if (selected?.id === inferenceProjectId) return;
    if (projectsLoading) return;
    const match = projects.find((p) => p.id === inferenceProjectId);
    if (match) void handleSelectProject(match);
  }, [inferenceProjectId, projects, projectsLoading, selected?.id, handleSelectProject]);

  const loadStatus = useCallback(async () => {
    if (!selected) return;
    setLoading(true);
    try {
      const data = await fetchInferenceStatus(selected.id);
      setStatus(data);
    } catch (e) {
      notify(e instanceof Error ? e.message : "Failed to load inference");
    } finally {
      setLoading(false);
    }
  }, [selected, notify]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    if (!selected || status?.inference?.status !== "deploying") return;
    const t = setInterval(() => void loadStatus(), 15000);
    return () => clearInterval(t);
  }, [selected, status?.inference?.status, loadStatus]);

  const handleBackToList = () => {
    navigate(inferencePath());
    setSelected(null);
    setStatus(null);
    void loadProjects();
  };

  const handleDeploy = async () => {
    if (!selected) return;
    setDeploying(true);
    try {
      const res = await deployInference(selected.id);
      if (res?.credits) announceCreditSpend(res.credits, notify);
      addEvent("Inference deploy started", "Azure ML endpoint provisioning", "blue");
      notify("Deploying inference endpoint on Azure ML…");
      await loadStatus();
      await loadProjects();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Deploy failed");
    } finally {
      setDeploying(false);
    }
  };

  const handleRotateKey = async () => {
    if (!selected) return;
    const res = await rotateInferenceApiKey(selected.id);
    setStatus((s) => (s ? { ...s, inference: res.inference } : s));
    notify("VisionDock API key updated");
  };

  const handleEdgeDownload = () => {
    if (!selected) return;
    window.open(edgeBundleUrl(selected.id), "_blank");
    addEvent("Edge bundle download", selected.id, "green");
    notify("Edge Docker bundle download started");
  };

  if (!inferenceProjectId || !selected) {
    return (
      <InferenceProjectPicker
        projects={projects}
        loading={projectsLoading}
        onSelect={(p) => void handleSelectProject(p)}
      />
    );
  }

  const inference = status?.inference;
  const canDeploy = status?.can_deploy ?? false;
  const isDeployed = inference?.status === "deployed";
  const isDeploying = inference?.status === "deploying" || deploying;
  const hasModel = status?.model || selected.has_model;

  return (
    <div className="space-y-6">
      <div className="vd-panel p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
          <div className="min-w-0">
            <Button
              variant="ghost"
              size="sm"
              className="mb-2 -ml-2 text-muted-foreground hover:text-foreground"
              onClick={handleBackToList}
            >
              <ChevronLeft className="mr-1 h-4 w-4" />
              All projects
            </Button>
            <h2 className="text-xl font-bold text-foreground mb-1">{projectListTitle(selected)}</h2>
            {selected.subtitle && (
              <p className="text-sm text-muted-foreground mb-1">{selected.subtitle}</p>
            )}
            <p className="text-muted-foreground font-mono text-xs">{selected.id}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void loadStatus()} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="vd-panel relative overflow-hidden border-primary/20 bg-primary/5 p-6">
            <div className="absolute top-0 right-0 p-6 opacity-10">
              <Cloud className="w-32 h-32 text-primary" />
            </div>
            <div className="relative z-10 space-y-4">
              <div className="h-12 w-12 bg-card rounded-lg border border-primary/20 flex items-center justify-center shadow-sm">
                <Cloud className="h-6 w-6 text-primary" />
              </div>
              <h3 className="text-lg font-bold text-foreground">Cloud API (Azure ML)</h3>
              <p className="text-sm text-muted-foreground">
                Managed online endpoint for image recognition. Auto-deploy starts when training completes.
              </p>

              <InferenceCredentialsPanel
                projectId={selected.id}
                inference={inference}
                onRotateKey={handleRotateKey}
              />

              {canDeploy && !isDeployed && !isDeploying && (
                <div className="space-y-2">
                  <Button
                    onClick={() => void handleDeploy()}
                    disabled={!canAfford("inference_deploy")}
                    className="w-full"
                  >
                    Deploy to Azure ML
                  </Button>
                  <p className="text-xs text-muted-foreground text-center">
                    ~{deployCost} credits (final cost depends on your model size) · balance{" "}
                    {(account?.balance ?? 0).toLocaleString()}
                    {!canAfford("inference_deploy") ? ` · need ${deployCost} more` : ""}
                  </p>
                </div>
              )}
            </div>
          </div>

          <div className="vd-panel relative overflow-hidden border-emerald-500/20 bg-emerald-500/5 p-6">
            <div className="absolute top-0 right-0 p-6 opacity-10">
              <Cpu className="w-32 h-32 text-emerald-700" />
            </div>
            <div className="relative z-10 space-y-4">
              <div className="h-12 w-12 bg-card rounded-lg border border-emerald-200 flex items-center justify-center shadow-sm">
                <Cpu className="h-6 w-6 text-emerald-700" />
              </div>
              <h3 className="text-lg font-bold text-foreground">Edge (x86 Docker)</h3>
              <p className="text-sm text-muted-foreground">
                PyTorch model + legacy FastAPI server for factory floor IPC (CPU). Prefer cloud API for image recognition.
              </p>

              <div className="grid grid-cols-2 gap-3">
                <div className="bg-card border border-border/60 rounded-lg p-3 text-center shadow-sm">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">
                    Format
                  </span>
                  <span className="font-mono text-sm font-bold text-foreground">ONNX / PT</span>
                </div>
                <div className="bg-card border border-border/60 rounded-lg p-3 text-center shadow-sm">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">
                    Auth
                  </span>
                  <span className="font-mono text-sm font-bold text-foreground">X-API-Key</span>
                </div>
              </div>

              <Button
                onClick={handleEdgeDownload}
                disabled={!isDeployed && !hasModel}
                className="w-full bg-emerald-700 text-white hover:bg-emerald-800 disabled:opacity-50"
              >
                <Download className="mr-2 h-4 w-4" />
                Download edge bundle
              </Button>
            </div>
          </div>
        </div>
      </div>

      {isDeployed && (
        <InferenceTestPanel
          projectId={selected.id}
          inference={inference}
          onNotify={notify}
        />
      )}
    </div>
  );
}
