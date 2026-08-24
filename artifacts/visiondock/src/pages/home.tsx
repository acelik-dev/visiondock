import { useEffect, useMemo, useState } from "react";
import { useLocation } from "wouter";
import { useStore } from "@/lib/store";
import type { WorkflowStep } from "@/lib/store";
import {
  beginNewWorkspace,
  listProjects,
  projectListTitle,
  setStoredProjectId,
  type ProjectListItem,
} from "@/lib/projects-api";
import { fetchMarketplaceDatasets, fetchMarketplaceModels } from "@/lib/marketplace-api";
import { projectsPath } from "@/lib/navigation";
import { useCredits } from "@/hooks/use-credits";
import { Database, FolderGit2, Library, Play, Server, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AnimatedMetricCard } from "@/components/premium/animated-metric";
import { FancyEmpty } from "@/components/premium/fancy-empty";
import {
  CreditCostGuide,
  DashboardHero,
  MarketplaceSnapshot,
  ProjectStatusChart,
  QuickActions,
  RecentProjectCard,
  TipCarousel,
  WorkflowPipeline,
} from "@/components/premium/dashboard-panels";

function trainingProgress(project: ProjectListItem): number {
  const status = (project.training_status || project.status || "").toLowerCase();
  if (project.inference_status === "deployed") return 100;
  if (status.includes("complet")) return 100;
  if (status.includes("train") || status.includes("running")) return 68;
  if (status.includes("ready")) return 40;
  return 15;
}

function inferWorkflowStep(project: ProjectListItem): WorkflowStep {
  if (project.inference_status === "deployed" || project.has_model) return 3;
  const ts = (project.training_status || "").toLowerCase();
  if (ts.includes("train") || ts.includes("running") || ts.includes("queued")) return 3;
  const st = (project.status || "").toLowerCase();
  if (st.includes("ready") || st.includes("dataset")) return 2;
  return 1;
}

export default function HomeView() {
  const [, navigate] = useLocation();
  const {
    setCurrentView,
    setWorkflowStep,
    addEvent,
    setPendingNewProject,
    setActiveProject,
  } = useStore();
  const { account } = useCredits();

  const [marketplaceModelCount, setMarketplaceModelCount] = useState<number | null>(null);
  const [marketplaceDatasetCount, setMarketplaceDatasetCount] = useState<number | null>(null);
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);

  useEffect(() => {
    void fetchMarketplaceModels()
      .then((res) => setMarketplaceModelCount(res.models.length))
      .catch(() => setMarketplaceModelCount(0));
    void fetchMarketplaceDatasets()
      .then((res) => setMarketplaceDatasetCount(res.datasets.length))
      .catch(() => setMarketplaceDatasetCount(0));
    void listProjects()
      .then((res) => setProjects(res.projects))
      .catch(() => setProjects([]))
      .finally(() => setProjectsLoading(false));
  }, []);

  const openDiscovery = () => {
    setWorkflowStep(1);
    setCurrentView("projects");
    navigate(projectsPath(1));
    addEvent("Discovery opened", "VLM chat workspace", "blue");
  };

  const startNewProject = () => {
    beginNewWorkspace();
    setPendingNewProject(true);
    setWorkflowStep(1);
    setCurrentView("projects");
    navigate(projectsPath(1));
    addEvent("New workspace", "Creating fresh VLM chat", "blue");
  };

  const goTo = (view: Parameters<typeof setCurrentView>[0], path: string) => {
    setCurrentView(view);
    navigate(path);
  };

  const openProject = (project: ProjectListItem) => {
    const step = inferWorkflowStep(project);
    setStoredProjectId(project.id);
    setActiveProject(project.id, projectListTitle(project));
    setWorkflowStep(step);
    setCurrentView("projects");
    navigate(projectsPath(step, project.id));
    addEvent("Project opened", projectListTitle(project), "blue");
  };

  const recentProjects = projects.slice(0, 5);
  const deployedCount = projects.filter((p) => p.inference_status === "deployed").length;
  const trainedCount = projects.filter((p) => p.has_model).length;
  const trainingCount = projects.filter((p) =>
    (p.training_status || "").toLowerCase().match(/train|running|queued/),
  ).length;

  const pipelineStep = useMemo((): WorkflowStep => {
    if (trainingCount > 0) return 3;
    if (trainedCount > 0) return 4;
    if (projects.some((p) => inferWorkflowStep(p) >= 2)) return 2;
    return 1;
  }, [projects, trainingCount, trainedCount]);

  const quickActions = [
    {
      label: "VLM Discovery",
      desc: "Define task via chat",
      icon: Sparkles,
      accent: "from-violet-500 to-primary",
      onClick: openDiscovery,
    },
    {
      label: "Model Library",
      desc: "Pretrained architectures",
      icon: Library,
      accent: "from-primary to-blue-600",
      onClick: () => goTo("models", "/models"),
    },
    {
      label: "Dataset Library",
      desc: "Ready-to-train data",
      icon: Database,
      accent: "from-emerald-500 to-teal-600",
      onClick: () => goTo("datasets", "/datasets"),
    },
    {
      label: "Inference",
      desc: "Test live endpoints",
      icon: Play,
      accent: "from-amber-500 to-orange-600",
      onClick: () => goTo("inference", "/inference"),
    },
  ];

  return (
    <div className="space-y-6">
      <DashboardHero
        projectCount={projects.length}
        credits={account?.balance ?? null}
        onStart={projects.length > 0 ? openDiscovery : startNewProject}
      />

      <div className="flex flex-wrap gap-3">
        <Button onClick={startNewProject} className="shadow-lg shadow-primary/20">
          <Sparkles className="mr-2 h-4 w-4" />
          Start new VLM session
        </Button>
        <Button variant="outline" onClick={openDiscovery}>
          Open current discovery
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4 lg:gap-5">
        <AnimatedMetricCard
          label="Workspaces"
          value={projectsLoading ? 0 : projects.length}
          icon={FolderGit2}
          accent="primary"
          delay={0}
        />
        <AnimatedMetricCard
          label="In training"
          value={projectsLoading ? 0 : trainingCount}
          icon={Server}
          accent="amber"
          delay={0.05}
        />
        <AnimatedMetricCard
          label="Trained models"
          value={projectsLoading ? 0 : trainedCount}
          icon={Library}
          accent="violet"
          delay={0.1}
        />
        <AnimatedMetricCard
          label="Live endpoints"
          value={projectsLoading ? 0 : deployedCount}
          icon={Play}
          accent="emerald"
          delay={0.15}
        />
      </div>

      <WorkflowPipeline activeStep={pipelineStep} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <div className="vd-panel-elevated p-6">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold tracking-tight text-foreground">Recent workspaces</h2>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Click a project to resume where you left off
                </p>
              </div>
              {projects.length > 0 && (
                <Button variant="outline" size="sm" onClick={openDiscovery}>
                  View all
                </Button>
              )}
            </div>
            {projectsLoading ? (
              <div className="space-y-3">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-16 animate-pulse rounded-xl bg-muted/50" />
                ))}
              </div>
            ) : recentProjects.length === 0 ? (
              <FancyEmpty
                icon={FolderGit2}
                title="No workspaces yet"
                description="Start with VLM discovery — upload 10 sample photos and describe your vision task in plain language."
                action={
                  <Button onClick={startNewProject} className="shadow-lg shadow-primary/20">
                    Create first workspace
                  </Button>
                }
              />
            ) : (
              <div className="space-y-2">
                {recentProjects.map((project, i) => (
                  <RecentProjectCard
                    key={project.id}
                    project={project}
                    title={projectListTitle(project)}
                    progress={trainingProgress(project)}
                    statusLabel={project.training_status || project.status || "Created"}
                    onOpen={() => openProject(project)}
                    delay={i * 0.06}
                  />
                ))}
              </div>
            )}
          </div>

          <QuickActions actions={quickActions} />
        </div>

        <div className="space-y-5">
          <ProjectStatusChart projects={projects} />
          <MarketplaceSnapshot
            modelCount={marketplaceModelCount}
            datasetCount={marketplaceDatasetCount}
            onModels={() => goTo("models", "/models")}
            onDatasets={() => goTo("datasets", "/datasets")}
          />
          <TipCarousel />
          <CreditCostGuide costs={account?.costs} />
        </div>
      </div>
    </div>
  );
}
