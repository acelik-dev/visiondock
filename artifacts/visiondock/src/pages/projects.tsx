import { useStore } from "@/lib/store";
import { 
  Brain, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Clock, Database, 
  Folder, ImagePlus, MessageSquare, 
  Mic, MoreHorizontal, Plus, Server, Sparkles, Trash2, 
  X, Zap, Cpu, DollarSign, Check, AlertTriangle
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { StatusPill } from "@/components/layout";
import { ConfigSummaryPanel } from "@/components/config-summary-panel";
import { ConfigPipelineEditor } from "@/components/config-pipeline-editor";
import { DatasetSummaryPanel } from "@/components/dataset-summary-panel";
import { DatasetUploadGuide, type UploadChecklistItem } from "@/components/dataset-upload-guide";
import { PremiumChatInput, PremiumChatPanel } from "@/components/premium/chat-panel";
import { FancyEmpty } from "@/components/premium/fancy-empty";
import { ImageUploadTrigger, ImageUploadZone } from "@/components/premium/image-upload-zone";
import { TrainingProgress } from "@/components/training-progress";
import { friendlyValidationMessage } from "@/lib/dataset-templates";
import { resolveApiBase } from "@/lib/api-base";
import { useActiveProject } from "@/hooks/use-active-project";
import { useTrainingInfo } from "@/hooks/use-training-info";
import { announceCreditSpend, useCredits } from "@/hooks/use-credits";
import { costLabel } from "@/lib/credits-api";
import { trainingConfigFromSpec } from "@/lib/training-api";
import type { DiscoveryInfo, ProjectSpec, TaskType } from "@/lib/project-spec";
import { DATASET_FORMAT_HINTS, DISCOVERY_HINTS, TASK_LABELS } from "@/lib/project-spec";
import { sanitizeLabels, stripLeadingDollar } from "@/lib/label-sanitize";

import {
  completeSetup,
  fetchClassificationDataset,
  fetchDatasetStatus,
  patchDiscovery,
  saveChat,
  tunePipelineFromDataset,
  uploadAnnotatedDataset,
  uploadClassificationImages,
  uploadMultiLabelImages,
  uploadMultiLabelManifest,
  uploadRegressionImages,
  uploadRegressionTargets,
  uploadSample,
  saveSpec,
} from "@/lib/projects-api";
import { rotateInferenceApiKey } from "@/lib/inference-api";
import { navigateToPath, parseProjectsRoute, pathToView, projectsPath } from "@/lib/navigation";
import { useLocation } from "wouter";
import { useState, useRef, useEffect, useCallback, useMemo } from "react";

// Types
type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
  images?: string[];
  timestamp?: Date;
};

type TaskTypeState = TaskType | null;

type VlmApiMessage = { role: "user" | "assistant"; content: string; internal?: boolean };

type AnalyzeResult = {
  text: string;
  readyForConfig: boolean;
  discovery: DiscoveryInfo | null;
  detectedTask: TaskTypeState;
  credits?: { balance?: number; debited?: number };
};

// VLM Service — same origin on Azure; localhost in dev
const PYTHON_API = resolveApiBase();

const REQUIRED_SAMPLE_IMAGES = 10;
const MIN_IMAGES_PER_CLASS = 5;

function isWelcomeAssistantMessage(m: ChatMessage): boolean {
  return m.role === "assistant" && m.content.trimStart().startsWith("Welcome!");
}

/** Reconstruct API message list: synthetic first user (image-analysis prompt) + all turns after the UI-only welcome bubble. */
function buildVlmApiMessages(
  chatSnapshot: ChatMessage[],
  firstAnalysisPrompt: string | null
): VlmApiMessage[] {
  const tail = chatSnapshot
    .filter((m) => m.role === "user" || m.role === "assistant")
    .filter((m) => !isWelcomeAssistantMessage(m))
    .map((m) => ({ role: m.role, content: m.content }));

  if (firstAnalysisPrompt) {
    // internal: this prompt is written by the UI, not the user — the API must not
    // count it as a discovery answer.
    return [{ role: "user" as const, content: firstAnalysisPrompt, internal: true }, ...tail];
  }
  return tail;
}

async function analyzeImagesWithVLM(
  images: string[],
  apiMessages: VlmApiMessage[],
  projectId: string | null,
): Promise<AnalyzeResult> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 90_000);
  try {
    // Follow-up turns: never re-send photos (was exhausting Azure OpenAI quota → 503).
    // Initial analysis may include up to 2 sample refs; backend prefers stored samples.
    const visionImages = images.slice(0, 2);
    const response = await fetch(`${PYTHON_API}/api/vlm/analyze`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        messages: apiMessages,
        images: visionImages.length > 0 ? visionImages : undefined,
        project_id: projectId,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : typeof data.detail === "object" && data.detail?.message
            ? String(data.detail.message)
            : Array.isArray(data.detail)
              ? data.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ")
              : data.detail != null
                ? JSON.stringify(data.detail)
                : `HTTP ${response.status}`;
      console.error("VLM API error:", response.status, detail);
      const friendly =
        response.status === 402
          ? detail
          : response.status === 422 || response.status === 429 || response.status === 502
            ? detail
            : `Could not reach the vision API (${response.status}). ${detail}`;
      return {
        text: friendly,
        readyForConfig: false,
        discovery: null,
        detectedTask: null,
        credits: data.credits,
      };
    }
    const text =
      typeof data.response === "string" ? data.response.trim() : "";
    if (!text) {
      return {
        text: "The assistant returned an empty reply. Please try sending again.",
        readyForConfig: false,
        discovery: data.discovery ?? null,
        detectedTask: (data.detected_task as TaskType) ?? null,
        credits: data.credits,
      };
    }
    return {
      text,
      readyForConfig: Boolean(data.ready_for_config),
      discovery: data.discovery ?? null,
      detectedTask: (data.detected_task as TaskType) ?? null,
      credits: data.credits,
    };
  } catch (error) {
    console.error("VLM Error:", error);
    const aborted = error instanceof DOMException && error.name === "AbortError";
    return {
      text: aborted
        ? "The vision assistant timed out. Please try again."
        : `Could not connect to the Python backend at ${PYTHON_API}.`,
      readyForConfig: false,
      discovery: null,
      detectedTask: null,
    };
  } finally {
    window.clearTimeout(timeout);
  }
}

/** Datasets already auto-tuned in this session — survives leaving and re-entering step 3. */
const tunedDatasets = new Set<string>();

export default function ProjectsView() {
  const {
    workflowStep,
    setWorkflowStep,
    syntheticGenerated,
    setSyntheticGenerated,
    trainingStarted,
    setTrainingStarted,
    addEvent,
    notify,
    marketplaceSpecBootstrap,
    setMarketplaceSpecBootstrap,
    setDatasetUploaded,
  } = useStore();

  const { canAfford, cost, refresh: refreshCredits } = useCredits();
  const chatCost = cost("vlm_analyze");

  const [location] = useLocation();

  const {
    projectId,
    projectMeta,
    setProjectMeta,
    initialSpec,
    initialChat,
    sampleUrls,
    setSampleUrls,
    loading: projectLoading,
    error: projectError,
    refresh: refreshProject,
    newProject,
    reload: reloadProject,
  } = useActiveProject();

  const handleRotateApiKey = useCallback(async () => {
    if (!projectId) return;
    const res = await rotateInferenceApiKey(projectId);
    setProjectMeta((m) => (m ? { ...m, inference: res.inference } : m));
    notify("VisionDock API key updated");
    await refreshProject(projectId);
  }, [projectId, refreshProject, notify, setProjectMeta]);

  // State
  const [sampleImages, setSampleImages] = useState<string[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isGeneratingConfig, setIsGeneratingConfig] = useState(false);
  const [detectedTask, setDetectedTask] = useState<TaskTypeState>(null);
  const [discovery, setDiscovery] = useState<DiscoveryInfo | null>(null);
  const [readyForConfig, setReadyForConfig] = useState(false);
  const [generatedConfig, setGeneratedConfig] = useState<ProjectSpec | null>(null);
  // Readiness is decided by the assessment model on the backend only.
  const canGenerateConfig = readyForConfig;
  const [pipelineTuning, setPipelineTuning] = useState(false);
  const [pipelineRationale, setPipelineRationale] = useState<string | null>(null);
  const pipelineTunedRef = useRef<string | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [classCounts, setClassCounts] = useState<Record<string, number>>({});
  const [classUploading, setClassUploading] = useState<string | null>(null);
  const [manifestUploading, setManifestUploading] = useState(false);
  const [targetsUploading, setTargetsUploading] = useState(false);
  const [imagesUploading, setImagesUploading] = useState(false);
  const [annotatedUploading, setAnnotatedUploading] = useState(false);
  const [datasetImageCount, setDatasetImageCount] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const classFileRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatSectionRef = useRef<HTMLDivElement>(null);
  const configSectionRef = useRef<HTMLElement>(null);
  const firstVlmPromptRef = useRef<string | null>(null);
  const hydratedRef = useRef(false);
  const readyNotifiedRef = useRef(false);
  const bouncedToDatasetRef = useRef<string | null>(null);

  useEffect(() => {
    hydratedRef.current = false;
    bouncedToDatasetRef.current = null;
  }, [projectId]);

  useEffect(() => {
    if (projectLoading || !projectMeta?.dataset?.source) return;
    if (projectMeta.dataset.source === "marketplace" && initialSpec) {
      setGeneratedConfig(initialSpec);
      setShowConfig(true);
      if (projectMeta.dataset.validated) {
        setWorkflowStep(3);
      } else {
        setWorkflowStep(2);
      }
    }
  }, [projectLoading, projectMeta, initialSpec, setWorkflowStep]);

  useEffect(() => {
    if (!marketplaceSpecBootstrap) return;
    // Apply marketplace/model bootstrap config only — do not force Training (step 3).
    // Model Library sets step 2 (upload required); Dataset Library sets step 3 (data already linked).
    setGeneratedConfig(marketplaceSpecBootstrap as ProjectSpec);
    setShowConfig(true);
    setMarketplaceSpecBootstrap(null);
  }, [marketplaceSpecBootstrap, setMarketplaceSpecBootstrap]);

  useEffect(() => {
    if (canGenerateConfig && !generatedConfig && !readyNotifiedRef.current) {
      readyNotifiedRef.current = true;
      notify("Ready to build your plan — tap Generate Config when you're happy with the chat.");
    }
    if (!canGenerateConfig) {
      readyNotifiedRef.current = false;
    }
  }, [canGenerateConfig, generatedConfig, notify]);

  const persistChat = useCallback(
    async (messages: ChatMessage[]) => {
      if (!projectId) return;
      const payload = messages
        .filter((m) => !isWelcomeAssistantMessage(m))
        .filter((m) => Boolean(m.content?.trim()) || (m.images && m.images.length > 0))
        .map((m) => ({
          role: m.role,
          content: m.content,
          timestamp: m.timestamp?.toISOString(),
        }));
      await saveChat(projectId, payload);
    },
    [projectId],
  );

  const projectConfig = generatedConfig ?? initialSpec;
  const taskType: TaskType = projectConfig?.task_type ?? "classification";
  const configClasses = useMemo(
    () => sanitizeLabels(Array.isArray(projectConfig?.classes) ? projectConfig!.classes : []),
    [projectConfig?.classes],
  );
  const classificationReady =
    projectMeta?.dataset?.validated ||
    (Object.values(classCounts).filter((c) => c >= MIN_IMAGES_PER_CLASS).length >= 2 &&
      configClasses.every((cls) => (classCounts[cls] ?? 0) >= MIN_IMAGES_PER_CLASS));
  const datasetReady =
    taskType === "classification"
      ? classificationReady
      : Boolean(projectMeta?.dataset?.validated);
  const isMarketplaceDataset = projectMeta?.dataset?.source === "marketplace";
  const marketplaceImporting =
    isMarketplaceDataset && projectMeta?.dataset?.import_status === "in_progress";
  const marketplaceDatasetReady = isMarketplaceDataset && Boolean(projectMeta?.dataset?.validated);
  const marketplaceDatasetLabel =
    projectMeta?.dataset?.marketplace_name ??
    projectMeta?.dataset?.marketplace_item_id ??
    "Library dataset";
  const isModelTemplate = projectMeta?.model_template?.source === "marketplace";
  const modelTemplateLabel =
    projectMeta?.model_template?.marketplace_name ??
    projectMeta?.model_template?.marketplace_item_id ??
    "Model template";
  const modelTemplateArch =
    projectMeta?.model_template?.architecture ?? projectConfig?.recommended_model ?? "";
  const modelTemplateExamples = useMemo(() => {
    const raw = projectMeta?.model_template?.example_classes;
    return Array.isArray(raw) ? raw.map(String).filter(Boolean).slice(0, 8) : [];
  }, [projectMeta?.model_template?.example_classes]);

  // Model Library projects must upload data before Training — bounce if they land on step 3 early.
  useEffect(() => {
    if (projectLoading || workflowStep !== 3) return;
    if (!isModelTemplate || marketplaceDatasetReady || datasetReady) return;
    const key = projectId ?? "unknown";
    setWorkflowStep(2);
    if (bouncedToDatasetRef.current !== key) {
      bouncedToDatasetRef.current = key;
      notify("Upload your training photos in Step 2 before starting training.");
    }
  }, [
    projectLoading,
    workflowStep,
    isModelTemplate,
    marketplaceDatasetReady,
    datasetReady,
    projectId,
    setWorkflowStep,
    notify,
  ]);

  useEffect(() => {
    setDatasetUploaded(datasetReady);
  }, [datasetReady, setDatasetUploaded]);

  const uploadChecklist: UploadChecklistItem[] = useMemo(() => {
    if (marketplaceDatasetReady) {
      return [{ id: "library", label: "Library dataset linked", done: true }];
    }
    if (taskType === "classification") {
      return [
        {
          id: "groups",
          label: `At least ${MIN_IMAGES_PER_CLASS} photos in every group`,
          done: Boolean(classificationReady),
        },
      ];
    }
    if (taskType === "multi_label") {
      const hasImages =
        datasetImageCount > 0 ||
        Boolean((projectMeta?.dataset?.validation?.stats?.image_count as number) > 0);
      const hasList = Boolean(projectMeta?.dataset?.file_name) || Boolean(projectMeta?.dataset?.validated);
      return [
        { id: "images", label: "Photos added", done: hasImages },
        { id: "list", label: "Label list added", done: hasList },
        { id: "ok", label: "Everything matches", done: Boolean(projectMeta?.dataset?.validated) },
      ];
    }
    if (taskType === "regression") {
      return [
        { id: "images", label: "Photos added", done: datasetImageCount > 0 },
        {
          id: "list",
          label: "Measurement list added",
          done: Boolean(projectMeta?.dataset?.file_name) || Boolean(projectMeta?.dataset?.validated),
        },
        { id: "ok", label: "Photos and numbers match", done: Boolean(projectMeta?.dataset?.validated) },
      ];
    }
    return [
      {
        id: "zip",
        label: "Labeled package uploaded",
        done: Boolean(projectMeta?.dataset?.uploaded),
      },
      {
        id: "ok",
        label: "Package checked and ready",
        done: Boolean(projectMeta?.dataset?.validated),
      },
    ];
  }, [
    marketplaceDatasetReady,
    taskType,
    classificationReady,
    datasetImageCount,
    projectMeta?.dataset?.file_name,
    projectMeta?.dataset?.validated,
    projectMeta?.dataset?.uploaded,
    projectMeta?.dataset?.validation?.stats?.image_count,
  ]);

  const trainingHp = trainingConfigFromSpec(projectConfig);
  const {
    info: trainingInfo,
    loading: trainingInfoLoading,
    error: trainingInfoError,
  } = useTrainingInfo(trainingHp.epochs);
  const samplesComplete = sampleImages.length >= REQUIRED_SAMPLE_IMAGES;
  // Model Library templates already have a task/spec — skip the 10-sample chat gate.
  const canContinueToDataset = Boolean(projectConfig) && (isModelTemplate || samplesComplete);

  const displayDuration =
    trainingInfo?.estimated_duration ??
    projectConfig?.hardware_requirements?.estimated_training_time ??
    "—";
  const displayCost =
    trainingInfo?.estimated_cost ??
    projectConfig?.hardware_requirements?.estimated_cost ??
    "—";

  const goToDatasetStep = () => {
    if (!projectConfig) {
      notify("Generate configuration before continuing.");
      return;
    }
    if (!generatedConfig) setGeneratedConfig(projectConfig);
    setWorkflowStep(2);
    addEvent("Task defined", "Moving to dataset upload", "green");
    notify(`Step 2: Upload your labeled dataset (${TASK_LABELS[taskType]}).`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  useEffect(() => {
    if (workflowStep !== 3 || !projectId) return;
    const dsKey = JSON.stringify(projectMeta?.dataset ?? {});
    const token = `${projectId}:${dsKey}`;
    // Claim the token before awaiting: re-entering the step or a meta refresh must not
    // fire a second tune for the same dataset.
    if (pipelineTunedRef.current === token || tunedDatasets.has(token)) return;
    pipelineTunedRef.current = token;

    let cancelled = false;
    setPipelineTuning(true);
    setPipelineRationale(null);
    void tunePipelineFromDataset(projectId)
      .then((res) => {
        tunedDatasets.add(token);
        if (cancelled) return;
        setGeneratedConfig(res.spec);
        setPipelineRationale(res.rationale ?? null);
      })
      .catch((err) => {
        pipelineTunedRef.current = null;
        if (cancelled) return;
        notify(err instanceof Error ? err.message : "Could not auto-configure pipeline from dataset");
      })
      .finally(() => {
        if (!cancelled) setPipelineTuning(false);
      });

    return () => {
      cancelled = true;
    };
  }, [workflowStep, projectId, projectMeta?.dataset, notify]);

  useEffect(() => {
    if (!projectId || pathToView(location) !== "projects") return;
    const expected = projectsPath(workflowStep, projectId);
    if (location !== expected) {
      navigateToPath(expected);
    }
  }, [projectId, workflowStep, location]);

  useEffect(() => {
    if (projectLoading || hydratedRef.current) return;
    if (initialSpec) {
      setGeneratedConfig(initialSpec);
      setShowConfig(true);
    }
    if (initialChat.length > 0) {
      setChatMessages((prev) =>
        prev.length > 0
          ? prev
          : initialChat.map((m) => ({
              role: m.role as "user" | "assistant",
              content: m.content,
              timestamp: m.timestamp ? new Date(m.timestamp) : new Date(),
            })),
      );
    }
    if (sampleUrls.length > 0) setSampleImages(sampleUrls);
    if (projectMeta?.dataset?.mode === "classification" && projectMeta.dataset.classes) {
      const counts: Record<string, number> = {};
      for (const [cls, info] of Object.entries(projectMeta.dataset.classes)) {
        counts[cls] = info.count ?? 0;
      }
      setClassCounts(counts);
    }
    hydratedRef.current = true;
  }, [projectLoading, initialSpec, initialChat, sampleUrls, projectMeta]);

  const refreshDatasetStatus = useCallback(async () => {
    if (!projectId) return;
    try {
      const status = await fetchDatasetStatus(projectId);
      if (status.mode === "classification" && status.classes) {
        setClassCounts(status.classes);
      }
      if (status.total_images != null) setDatasetImageCount(status.total_images);
      setProjectMeta((m) =>
        m
          ? {
              ...m,
              dataset: {
                ...(m.dataset ?? {
                  uploaded: false,
                  validated: false,
                  size_bytes: 0,
                  file_name: null,
                }),
                mode: status.mode,
                uploaded: (status.total_images ?? 0) > 0 || Boolean(m.dataset?.uploaded),
                validated: status.validated,
                validation: status.validation ?? undefined,
                classes: status.classes
                  ? Object.fromEntries(
                      Object.entries(status.classes).map(([cls, count]) => [cls, { count }]),
                    )
                  : m.dataset?.classes,
              },
            }
          : m,
      );
    } catch {
      /* ignore until first upload */
    }
  }, [projectId, setProjectMeta]);

  const refreshClassificationStatus = useCallback(async () => {
    if (!projectId) return;
    try {
      const status = await fetchClassificationDataset(projectId);
      setClassCounts(status.classes);
      setDatasetImageCount(status.total_images);
      setProjectMeta((m) =>
        m
          ? {
              ...m,
              dataset: {
                ...(m.dataset ?? {
                  uploaded: false,
                  validated: false,
                  size_bytes: 0,
                  file_name: null,
                }),
                mode: "classification",
                uploaded: status.total_images > 0,
                validated: status.validated,
                validation: status.validation ?? undefined,
                classes: Object.fromEntries(
                  Object.entries(status.classes).map(([cls, count]) => [cls, { count }]),
                ),
              },
            }
          : m,
      );
    } catch {
      /* ignore until first upload */
    }
  }, [projectId, setProjectMeta]);

  useEffect(() => {
    if (!projectId || workflowStep !== 2) return;
    if (taskType === "classification") {
      void refreshClassificationStatus();
    } else {
      void refreshDatasetStatus();
    }
  }, [projectId, workflowStep, taskType, refreshClassificationStatus, refreshDatasetStatus]);

  useEffect(() => {
    if (!projectId || !marketplaceImporting) return;
    const timer = window.setInterval(() => {
      if (taskType === "classification") {
        void refreshClassificationStatus();
      } else {
        void refreshDatasetStatus();
      }
      void refreshProject(projectId).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [projectId, marketplaceImporting, taskType, refreshClassificationStatus, refreshDatasetStatus, refreshProject]);


  if (projectLoading) {
    return (
      <div className="flex items-center justify-center py-24 text-muted-foreground text-sm">
        Loading project…
      </div>
    );
  }

  if (projectError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 space-y-4">
        <p className="text-red-700 text-sm">
          {projectError}
          <span className="block mt-2 text-red-600/80">
            The saved project may have been removed from storage. Create a new workspace to open the VLM chat.
          </span>
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            className=""
            onClick={() => void newProject()}
          >
            Create new workspace
          </Button>
          <Button variant="outline" onClick={() => void reloadProject()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    uploadSampleFiles(files);
    e.target.value = "";
  };

  const uploadSampleFiles = (files: FileList) => {
    if (!projectId) return;

    void (async () => {
      const slice = Array.from(files).slice(0, 10 - sampleImages.length);
      const uploaded: string[] = [];
      for (const file of slice) {
        const item = await uploadSample(projectId, file);
        // Prefer relative sample URL for UI; avoid keeping multi-MB data URLs in memory.
        uploaded.push(item.url || item.data_url);
      }
      const prevCount = sampleImages.length;
      const allImages = [...sampleImages, ...uploaded].slice(0, REQUIRED_SAMPLE_IMAGES);
      setSampleImages(allImages);
      setSampleUrls(allImages);
      addEvent("Images uploaded", `${uploaded.length} sample(s) saved to storage`, "blue");
      const remaining = REQUIRED_SAMPLE_IMAGES - allImages.length;
      if (remaining > 0) {
        notify(`Sample images: ${allImages.length}/${REQUIRED_SAMPLE_IMAGES} — add ${remaining} more to start the assistant.`);
      } else if (prevCount < REQUIRED_SAMPLE_IMAGES) {
        notify("All 10 sample images uploaded — starting analysis…");
        setTimeout(() => void analyzeAndSuggest(allImages), 300);
      }
    })().catch((err) => {
      addEvent("Upload failed", err instanceof Error ? err.message : "Unknown error", "red");
    });
  };

  const handleClassImages = (className: string, e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length || !projectId) return;
    void (async () => {
      setClassUploading(className);
      setDatasetError(null);
      try {
        const result = await uploadClassificationImages(
          projectId,
          className,
          Array.from(files),
        );
        setProjectMeta(result.project);
        setClassCounts(result.class_counts);
        setTrainingStarted(false);
        const v = result.validation;
        if (v?.valid) {
          addEvent("Dataset validated", `${result.added} images added to ${className}`, "green");
        } else if (v?.warnings?.length) {
          addEvent("Dataset progress", v.warnings[0], "amber");
        }
      } catch (err) {
        setDatasetError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setClassUploading(null);
        e.target.value = "";
      }
    })();
  };

  const openClassPicker = (className: string) => {
    if (classUploading) return;
    classFileRefs.current[className]?.click();
  };

  const handleMultiLabelImages = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length || !projectId) return;
    void (async () => {
      setImagesUploading(true);
      setDatasetError(null);
      try {
        const result = await uploadMultiLabelImages(projectId, Array.from(files));
        setProjectMeta(result.project);
        setDatasetImageCount(result.image_count);
        await refreshDatasetStatus();
      } catch (err) {
        setDatasetError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setImagesUploading(false);
        e.target.value = "";
      }
    })();
  };

  const handleMultiLabelManifest = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !projectId) return;
    void (async () => {
      setManifestUploading(true);
      setDatasetError(null);
      try {
        const result = await uploadMultiLabelManifest(projectId, file);
        setProjectMeta(result.project);
        await refreshDatasetStatus();
      } catch (err) {
        setDatasetError(err instanceof Error ? err.message : "Manifest upload failed");
      } finally {
        setManifestUploading(false);
        e.target.value = "";
      }
    })();
  };

  const handleRegressionImages = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length || !projectId) return;
    void (async () => {
      setImagesUploading(true);
      setDatasetError(null);
      try {
        const result = await uploadRegressionImages(projectId, Array.from(files));
        setProjectMeta(result.project);
        setDatasetImageCount(result.image_count);
        await refreshDatasetStatus();
      } catch (err) {
        setDatasetError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setImagesUploading(false);
        e.target.value = "";
      }
    })();
  };

  const handleRegressionTargets = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !projectId) return;
    void (async () => {
      setTargetsUploading(true);
      setDatasetError(null);
      try {
        const result = await uploadRegressionTargets(projectId, file);
        setProjectMeta(result.project);
        await refreshDatasetStatus();
      } catch (err) {
        setDatasetError(err instanceof Error ? err.message : "Target CSV upload failed");
      } finally {
        setTargetsUploading(false);
        e.target.value = "";
      }
    })();
  };

  const handleAnnotatedUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !projectId) return;
    void (async () => {
      setAnnotatedUploading(true);
      setDatasetError(null);
      try {
        const result = await uploadAnnotatedDataset(projectId, file);
        setProjectMeta(result.project);
        await refreshDatasetStatus();
        if (result.validation?.valid) {
          addEvent("Dataset validated", "Annotated ZIP accepted", "green");
        }
      } catch (err) {
        setDatasetError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setAnnotatedUploading(false);
        e.target.value = "";
      }
    })();
  };

  const analyzeAndSuggest = async (images: string[]) => {
    const welcomeMsg: ChatMessage = {
      role: 'assistant',
      content: "Thanks for the sample photos — I'm taking a look…",
      timestamp: new Date()
    };
    setChatMessages([welcomeMsg]);
    setIsAnalyzing(true);

    const prompt = `The user uploaded sample photos for a vision project. VisionDock is NOT a labeling tool — users bring pre-labeled data.

In plain, friendly language:
1) Describe what you see in 1–2 sentences.
2) Suggest the most likely task type among: image classification (one label per photo / one folder per class), multi-label classification (several tags on the SAME photo), regression, object localization, or object detection — do not finalize yet. Several class names alone is not multi-label.
3) Ask what labels, categories, or numeric target they already have in their dataset (offer examples from the photos).
4) Ask where cameras run and whether they need instant alerts or daily review.
Do not suggest annotating inside VisionDock. Do not say "ready for configuration". No training jargon.`;

    firstVlmPromptRef.current = prompt;
    const result = await analyzeImagesWithVLM(images, [{ role: "user", content: prompt }], projectId);
    setIsAnalyzing(false);
    announceCreditSpend(result.credits, notify);

    const aiMessage: ChatMessage = {
      role: "assistant",
      content: result.text,
      timestamp: new Date(),
    };
    const next = [welcomeMsg, aiMessage];
    setChatMessages(next);
    void persistChat(next);
    setDiscovery(result.discovery);
    setReadyForConfig(result.readyForConfig);
    if (result.detectedTask) setDetectedTask(result.detectedTask);
    if (projectId) {
      void patchDiscovery(projectId, {
        ready_for_config: result.readyForConfig,
        detected_task: result.detectedTask,
      }).then((r) => setProjectMeta(r.project));
    }
    addEvent("VLM Analysis Complete", "Images analyzed — continue the conversation", "green");
  };

  const removeImage = (index: number) => {
    const next = sampleImages.filter((_, i) => i !== index);
    setSampleImages(next);
    setSampleUrls(next);
    if (next.length < REQUIRED_SAMPLE_IMAGES) {
      setChatMessages([]);
      setDetectedTask(null);
      setDiscovery(null);
      setReadyForConfig(false);
      setGeneratedConfig(null);
      setShowConfig(false);
      firstVlmPromptRef.current = null;
      if (next.length > 0) {
        notify(`Need ${REQUIRED_SAMPLE_IMAGES - next.length} more sample image(s) before chatting.`);
      }
    }
  };

  const handleSendMessage = async () => {
    if (!samplesComplete) {
      notify(`Upload ${REQUIRED_SAMPLE_IMAGES} sample images first (${sampleImages.length}/${REQUIRED_SAMPLE_IMAGES}).`);
      return;
    }
    const draft = chatInput.trim();
    if (!draft || isAnalyzing || isGeneratingConfig) return;

    const userMsg: ChatMessage = {
      role: "user",
      content: draft,
      images: chatMessages.length === 0 && sampleImages.length > 0 ? sampleImages : undefined,
      timestamp: new Date(),
    };

    const nextChat = [...chatMessages, userMsg];
    setChatInput("");
    setChatMessages(nextChat);
    void persistChat(nextChat);

    setIsAnalyzing(true);
    try {
      const apiMessages = buildVlmApiMessages(nextChat, firstVlmPromptRef.current);
      const result = await analyzeImagesWithVLM([], apiMessages, projectId);
      announceCreditSpend(result.credits, notify);

      const aiMessage: ChatMessage = {
        role: "assistant",
        content: result.text || "The assistant returned an empty reply. Please try again.",
        timestamp: new Date(),
      };
      const fullChat = [...nextChat, aiMessage];
      setChatMessages(fullChat);
      void persistChat(fullChat);
      setDiscovery(result.discovery);
      setReadyForConfig(result.readyForConfig);
      if (result.detectedTask) setDetectedTask(result.detectedTask);
      if (projectId) {
        void patchDiscovery(projectId, {
          ready_for_config: result.readyForConfig,
          detected_task: result.detectedTask,
        }).then((r) => setProjectMeta(r.project));
      }
    } catch (err) {
      console.error("Chat send failed:", err);
      notify(err instanceof Error ? err.message : "Message failed — please send again.");
      setChatInput(draft);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const generateStructuredConfig = async (chatOverride?: ChatMessage[], force = false) => {
    setConfigError(null);
    const draft = chatInput.trim();
    let chat = chatOverride ?? chatMessages;
    if (!chatOverride && draft) {
      const userMsg: ChatMessage = {
        role: "user",
        content: draft,
        timestamp: new Date(),
      };
      chat = [...chatMessages, userMsg];
      setChatInput("");
      setChatMessages(chat);
      void persistChat(chat);
    }

    setIsGeneratingConfig(true);
    try {
      const messages = buildVlmApiMessages(chat, firstVlmPromptRef.current);

      const response = await fetch(`${PYTHON_API}/api/vlm/generate-config`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages,
          // Config generation is text/transcript based — don't re-upload sample photos.
          force,
          project_id: projectId,
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (response.ok && data.config) {
        announceCreditSpend(data.credits, notify);
        const spec = data.config as ProjectSpec;
        setGeneratedConfig(spec);
        setShowConfig(true);
        if (projectId) {
          void saveSpec(projectId, spec).then(() => refreshProject(projectId));
        }
        const updating = Boolean(generatedConfig);
        addEvent(
          updating ? "Config updated" : "Config generated",
          updating ? "Project plan refreshed from the latest chat" : "ProjectSpec v1 saved to storage",
          "green",
        );
        if (updating) notify("Project plan updated from the latest chat.");
        if (!updating) {
          window.setTimeout(() => {
            configSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
          }, 180);
        }
        return;
      }
      const detail = data.detail;
      if (typeof detail === "object" && detail?.message) {
        setConfigError(detail.message);
      } else if (typeof detail === "string") {
        setConfigError(detail);
      } else {
        setConfigError("Could not generate configuration yet.");
      }
      if (response.status === 402) void refreshCredits();
    } catch (error) {
      console.error("Config generation error:", error);
      setConfigError("Network error while generating configuration.");
    } finally {
      setIsGeneratingConfig(false);
    }
  };

  const clearChat = () => {
    setChatMessages([]);
    setDetectedTask(null);
    setGeneratedConfig(null);
    setShowConfig(false);
    setDiscovery(null);
    setReadyForConfig(false);
    setConfigError(null);
    firstVlmPromptRef.current = null;
  };

  return (
    <div className="space-y-6">

      {/* Step 1: Chat-First VLM Task Definition */}
      {workflowStep === 1 && (
        <div className="space-y-10">
        <div
          ref={chatSectionRef}
          className="flex h-[calc(100dvh-6.5rem)] min-h-[520px] w-full flex-col overflow-hidden rounded-2xl border border-border/60 bg-card shadow-sm"
        >
          {isModelTemplate && (
            <div className="mx-6 mt-5 shrink-0 rounded-xl border border-indigo-200 bg-indigo-50 p-4">
              <div className="mb-2 flex items-center gap-2">
                <Cpu className="h-5 w-5 text-indigo-600" />
                <h4 className="text-sm font-semibold text-indigo-900">Model from Model Library</h4>
              </div>
              <p className="text-sm text-indigo-800">
                Architecture <strong>{modelTemplateArch}</strong> ({modelTemplateLabel}) is pre-selected.
                Sample photos are optional here — continue to Step 2 to upload <strong>your own training data</strong>.
              </p>
              <Button
                type="button"
                onClick={goToDatasetStep}
                disabled={!projectConfig}
                className="mt-3 h-9 bg-indigo-600 hover:bg-indigo-700"
              >
                Go to dataset upload
                <ChevronRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          )}

          <div className="shrink-0 border-b border-border/60 bg-gradient-to-r from-muted/30 to-card px-5 py-4 sm:px-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-white shadow-md shadow-primary/25">
                  <span className="text-sm font-bold">1</span>
                </div>
                <div className="min-w-0">
                  <h3 className="text-lg font-bold text-foreground">Define Your Vision Task</h3>
                  <p className="text-xs text-muted-foreground sm:text-sm">
                    Upload {REQUIRED_SAMPLE_IMAGES} samples, then chat to shape the project
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void newProject()}
                  className="border-primary/25 bg-primary/5 text-primary hover:bg-primary/10"
                >
                  <Plus className="mr-1.5 h-4 w-4" />
                  New session
                </Button>
                <ImageUploadTrigger
                  onClick={() => fileInputRef.current?.click()}
                  count={sampleImages.length}
                  required={REQUIRED_SAMPLE_IMAGES}
                  complete={samplesComplete}
                />
                <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleImageUpload} />
              </div>
            </div>

            {discovery && samplesComplete && chatMessages.length > 0 && !generatedConfig && (
              <div className="mt-3">
                <div className="mb-1.5 flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>{canGenerateConfig ? "Ready to build your plan" : "Understanding your project"}</span>
                  <span className="font-semibold">{discovery.progress_percent}%</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full rounded-full transition-all ${canGenerateConfig ? "bg-emerald-500" : "bg-primary"}`}
                    style={{ width: `${discovery.progress_percent}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="flex min-h-[240px] min-w-0 flex-1 flex-col overflow-hidden">
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-gradient-to-b from-muted/20 to-background">
                <PremiumChatPanel
                  messages={chatMessages}
                  isLoading={isAnalyzing}
                  loadingLabel={
                    sampleImages.length > 0 && chatMessages.length <= 1
                      ? "Analyzing your images…"
                      : "Assistant is thinking…"
                  }
                  endRef={chatEndRef}
                  empty={
                    <div className="flex h-full flex-col items-center justify-center px-6 py-8">
                      <FancyEmpty
                        icon={Brain}
                        title="Upload sample photos first"
                        description={`Add ${REQUIRED_SAMPLE_IMAGES} real photos — similar scenes to what the model will see later.`}
                        action={
                          <div className="mx-auto w-full max-w-md text-left">
                            <ImageUploadZone
                              images={sampleImages}
                              required={REQUIRED_SAMPLE_IMAGES}
                              onAdd={uploadSampleFiles}
                              onRemove={removeImage}
                              onBrowse={() => fileInputRef.current?.click()}
                              disabled={samplesComplete}
                            />
                          </div>
                        }
                      />
                    </div>
                  }
                />

                <div className="shrink-0 border-t border-border/60 bg-card px-4 py-3">
                  {sampleImages.length > 0 && chatMessages.length === 0 && (
                    <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1">
                      {sampleImages.map((img, idx) => (
                        <div key={idx} className="group relative shrink-0">
                          <img src={img} alt="" className="h-9 w-9 rounded-md border border-border/60 object-cover" />
                          <button
                            type="button"
                            onClick={() => removeImage(idx)}
                            className="absolute -right-1 -top-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-destructive text-destructive-foreground opacity-0 transition-opacity group-hover:opacity-100"
                          >
                            <X className="h-2 w-2" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  <PremiumChatInput
                    bare
                    value={chatInput}
                    onChange={setChatInput}
                    onSend={() => void handleSendMessage()}
                    disabled={!samplesComplete || isAnalyzing || isGeneratingConfig || !canAfford("vlm_analyze")}
                    isLoading={isAnalyzing}
                    placeholder={
                      samplesComplete
                        ? "Answer the assistant or add more detail…"
                        : `Upload ${REQUIRED_SAMPLE_IMAGES} samples to enable chat…`
                    }
                    trailing={
                      canGenerateConfig || generatedConfig ? (
                        <Button
                          type="button"
                          onClick={() => void generateStructuredConfig(undefined, true)}
                          disabled={isAnalyzing || isGeneratingConfig || !canAfford("generate_config")}
                          className="h-12 shrink-0 rounded-xl bg-emerald-600 px-4 hover:bg-emerald-700"
                        >
                          <Sparkles className="mr-2 h-4 w-4" />
                          {isGeneratingConfig
                            ? "Updating…"
                            : generatedConfig
                              ? "Update config"
                              : "Generate Config"}
                        </Button>
                      ) : undefined
                    }
                  />
                  <div className="mt-1.5 text-[11px] text-muted-foreground">
                    {!samplesComplete
                      ? `${sampleImages.length}/${REQUIRED_SAMPLE_IMAGES} samples`
                      : isAnalyzing
                        ? "Assistant is analyzing…"
                        : isGeneratingConfig
                          ? "Updating project plan…"
                        : chatCost > 0
                          ? `${chatCost} credit per message · Send to chat, Update config to refresh the plan`
                          : null}
                  </div>
                  {configError && <p className="mt-1 text-xs text-destructive">{configError}</p>}
                </div>
              </div>
            </div>
          </div>

          {generatedConfig && showConfig && (
            <button
              type="button"
              onClick={() => configSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
              className="shrink-0 border-t border-border/60 bg-gradient-to-b from-card to-muted/40 px-4 py-2.5 text-left transition hover:bg-muted/50"
            >
              <div className="flex items-center justify-center gap-2 text-xs font-medium text-muted-foreground">
                <span>Review project plan</span>
                <motion.span
                  animate={{ y: [0, 4, 0] }}
                  transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
                  className="inline-flex"
                >
                  <ChevronDown className="h-4 w-4 text-primary" />
                </motion.span>
              </div>
            </button>
          )}
        </div>

        <AnimatePresence>
          {showConfig && generatedConfig && (
            <motion.section
              ref={configSectionRef}
              id="project-plan"
              initial={{ opacity: 0, y: 56 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 24 }}
              transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
              className="scroll-mt-24"
            >
              <div className="flex h-[calc(100dvh-6.5rem)] min-h-[520px] w-full flex-col overflow-hidden rounded-2xl border border-border/60 bg-card shadow-sm">
                <div className="shrink-0 border-b border-border/60 bg-gradient-to-r from-emerald-50/80 via-card to-muted/30 px-5 py-4 sm:px-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">
                        Next screen
                      </p>
                      <h3 className="mt-1 text-lg font-bold text-foreground">Your project plan</h3>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Generated from the chat above. Keep talking, then tap Update config to refresh this page.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => chatSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
                      className="inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
                    >
                      <ChevronUp className="h-3.5 w-3.5" />
                      Back to chat
                    </button>
                  </div>
                </div>

                <motion.div
                  key={`${generatedConfig.project_name}-${(generatedConfig.classes ?? []).join("|")}`}
                  initial={{ opacity: 0.4, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.35 }}
                  className="flex min-h-0 flex-1 flex-col overflow-y-auto p-5 sm:p-6"
                >
                  <div className="flex min-h-full flex-1 flex-col overflow-hidden rounded-xl border border-border/60 bg-background">
                    <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border/60 bg-muted/40 px-5 py-3 sm:px-6">
                      <span className="truncate text-sm font-semibold text-foreground">{generatedConfig.project_name}</span>
                      <span className="shrink-0 rounded-full bg-primary/12 px-2 py-0.5 text-xs font-medium text-primary">
                        {TASK_LABELS[generatedConfig.task_type] ?? generatedConfig.task_type}
                      </span>
                    </div>
                    <div className="flex-1 p-5 sm:p-6">
                      <ConfigSummaryPanel
                        config={generatedConfig}
                        projectId={projectId}
                        inference={projectMeta?.inference}
                        onRotateApiKey={handleRotateApiKey}
                      />
                    </div>
                  </div>
                </motion.div>

                <div className="flex shrink-0 items-center justify-between gap-3 border-t border-border/60 bg-muted/30 px-5 py-3 sm:px-6">
                  <span className="inline-flex max-w-full items-center gap-1.5 truncate rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                    {TASK_LABELS[taskType] ?? "Vision task"} ready
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    onClick={goToDatasetStep}
                    disabled={!canContinueToDataset}
                    title={
                      isModelTemplate
                        ? !projectConfig
                          ? "Task configuration is still loading"
                          : undefined
                        : !samplesComplete
                          ? `Upload ${REQUIRED_SAMPLE_IMAGES} sample images first`
                          : !projectConfig
                            ? "Generate Config from the chat first"
                            : undefined
                    }
                    className="h-9 shrink-0"
                  >
                    Continue to dataset
                    <ChevronRight className="ml-1.5 h-4 w-4" />
                  </Button>
                </div>
              </div>
            </motion.section>
          )}
        </AnimatePresence>
        </div>
      )}

      {/* Step 2: Dataset Upload */}
      {workflowStep === 2 && (
        <div className="bg-card rounded-2xl border border-border/60 shadow-sm overflow-hidden">
          <div className="border-b border-border/60 bg-gradient-to-r from-muted/30 to-card px-8 py-6">
            <div className="flex items-center gap-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-white shadow-lg shadow-blue-200">
                <span className="text-sm font-bold">2</span>
              </div>
              <div>
                <h3 className="text-xl font-bold text-foreground">Add training photos</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Each photo needs an answer already. VisionDock does not label for you — it learns from the examples you provide.
                </p>
              </div>
            </div>
          </div>

          <div className="p-8 space-y-8">
            {projectConfig ? (
              <div className="bg-primary/8 border border-primary/15 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle2 className="h-5 w-5 text-primary" />
                  <h4 className="text-sm font-semibold text-primary">What your task expects</h4>
                </div>
                <p className="text-xs text-primary mb-3">{DATASET_FORMAT_HINTS[taskType]}</p>
                {configClasses.length > 0 && taskType !== "regression" && (
                  <div className="flex flex-wrap gap-2 mb-3">
                    {configClasses.map((cls: string, idx: number) => (
                      <span
                        key={idx}
                        className="px-3 py-1.5 bg-card border border-primary/20 rounded-lg text-sm font-medium text-primary"
                      >
                        {cls}
                      </span>
                    ))}
                  </div>
                )}
                <div className="text-xs text-primary">
                  <span className="font-medium">Task:</span> {TASK_LABELS[taskType]}
                  {taskType === "regression" && projectConfig?.target_name && (
                    <>
                      <span className="font-medium ml-2">Number to predict:</span>{" "}
                      {projectConfig.target_name}
                      {projectConfig.target_unit ? ` (${projectConfig.target_unit})` : ""}
                    </>
                  )}
                </div>
              </div>
            ) : (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="h-5 w-5 text-amber-600" />
                  <h4 className="text-sm font-semibold text-amber-900">Task not set up yet</h4>
                </div>
                <p className="text-xs text-amber-700">
                  Go back to Step 1 and chat with the assistant so we know what groups or numbers you need.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3 text-xs border-amber-300 text-amber-700 hover:bg-amber-100"
                  onClick={() => setWorkflowStep(1)}
                >
                  <ChevronLeft className="h-3 w-3 mr-1" />
                  Back to task setup
                </Button>
              </div>
            )}

            {marketplaceImporting && (
              <div className="bg-primary/8 border border-primary/20 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-2">
                  <Database className="h-5 w-5 text-primary animate-pulse" />
                  <h4 className="text-sm font-semibold text-primary">Connecting library dataset…</h4>
                </div>
                <p className="text-sm text-primary">
                  Linking <strong>{marketplaceDatasetLabel}</strong>. Large sets can take a minute.
                </p>
              </div>
            )}

            {isModelTemplate && !marketplaceDatasetReady && (
              <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-2">
                  <Cpu className="h-5 w-5 text-indigo-600" />
                  <h4 className="text-sm font-semibold text-indigo-900">Train on your photos</h4>
                </div>
                <p className="text-sm text-indigo-800">
                  Architecture <strong>{modelTemplateArch}</strong> is ready. Bring{" "}
                  <em>your</em> labeled images — catalog demo categories are not required.
                </p>
                {taskType === "classification" && modelTemplateExamples.length > 0 && configClasses.length === 0 && (
                  <p className="mt-2 text-xs text-indigo-700">
                    Reference demo labels (ignore these — add your own groups below):{" "}
                    {modelTemplateExamples.join(", ")}
                    {(projectMeta?.model_template?.example_classes?.length ?? 0) > 8 ? "…" : ""}
                  </p>
                )}
              </div>
            )}

            {!marketplaceImporting && (
              <DatasetUploadGuide
                taskType={taskType}
                checklist={uploadChecklist}
                targetName={projectConfig?.target_name || "target"}
                labels={configClasses}
                marketplaceLinked={marketplaceDatasetReady}
                marketplaceLabel={marketplaceDatasetLabel}
                minImagesPerClass={MIN_IMAGES_PER_CLASS}
              />
            )}

            {/* Task-specific upload UI */}
            {!marketplaceDatasetReady && !marketplaceImporting && taskType === "classification" && configClasses.length > 0 ? (
              <div className="space-y-4">
                <p className="text-sm font-semibold text-foreground/90">Add photos to each group</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {configClasses.map((cls) => {
                    const count = classCounts[cls] ?? 0;
                    const ready = count >= MIN_IMAGES_PER_CLASS;
                    const uploading = classUploading === cls;
                    return (
                      <div
                        key={cls}
                        onClick={() => openClassPicker(cls)}
                        className={`relative cursor-pointer rounded-xl border-2 border-dashed p-6 transition-all ${
                          ready
                            ? "border-emerald-300 bg-emerald-50/40 hover:border-emerald-400"
                            : "border-border bg-muted/40 hover:border-primary/40 hover:bg-primary/8/30"
                        }`}
                      >
                        <input
                          ref={(el) => {
                            classFileRefs.current[cls] = el;
                          }}
                          type="file"
                          className="hidden"
                          accept="image/*"
                          multiple
                          onChange={(e) => handleClassImages(cls, e)}
                        />
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h4 className="text-base font-semibold text-foreground">{cls}</h4>
                            <p className="text-xs text-muted-foreground mt-1">
                              {uploading
                                ? "Uploading…"
                                : ready
                                  ? `${count} photos — ready`
                                  : `${count}/${MIN_IMAGES_PER_CLASS} photos minimum`}
                            </p>
                          </div>
                          <div
                            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
                              ready ? "bg-emerald-100" : "bg-card border border-border/60"
                            }`}
                          >
                            {uploading ? (
                              <div className="h-4 w-4 border-2 border-primary/30 border-t-blue-600 rounded-full animate-spin" />
                            ) : ready ? (
                              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                            ) : (
                              <ImagePlus className="h-5 w-5 text-primary" />
                            )}
                          </div>
                        </div>
                        <p className="text-xs text-muted-foreground/70 mt-3">
                          Add photos for this group (click or drop JPG/PNG)
                        </p>
                      </div>
                    );
                  })}
                </div>
                {datasetError && (
                  <p className="text-sm text-red-600">{friendlyValidationMessage(datasetError)}</p>
                )}
                {projectMeta?.dataset?.validation?.warnings?.length ? (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
                    {projectMeta.dataset.validation.warnings.map(friendlyValidationMessage).join(" ")}
                  </div>
                ) : null}
              </div>
            ) : !marketplaceDatasetReady && !marketplaceImporting && taskType === "multi_label" ? (
              <div className="space-y-4">
                <div>
                  <p className="text-sm font-semibold text-foreground/90">1. Add all photos</p>
                  <p className="text-xs text-muted-foreground mt-1">Drag every training photo here.</p>
                </div>
                <UploadZone
                  title="Photos"
                  hint="JPG or PNG — all training photos"
                  uploading={imagesUploading}
                  ready={(datasetImageCount || projectMeta?.dataset?.validation?.stats?.image_count as number) > 0}
                  statusText={
                    imagesUploading
                      ? "Uploading…"
                      : `${datasetImageCount || 0} photos added`
                  }
                  inputId="multi-label-images"
                  accept="image/*"
                  multiple
                  onChange={handleMultiLabelImages}
                />
                <div>
                  <p className="text-sm font-semibold text-foreground/90">2. Which tags does each photo have?</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Download the example above, fill it in, then upload your finished list.
                  </p>
                </div>
                <UploadZone
                  title="Label list"
                  hint="CSV preferred — one row per photo with its tags"
                  uploading={manifestUploading}
                  ready={Boolean(projectMeta?.dataset?.file_name)}
                  statusText={
                    manifestUploading
                      ? "Uploading…"
                      : projectMeta?.dataset?.file_name
                        ? projectMeta.dataset.file_name
                        : "No list yet"
                  }
                  inputId="multi-label-manifest"
                  accept=".csv,.json"
                  onChange={handleMultiLabelManifest}
                />
                {datasetError && (
                  <p className="text-sm text-red-600">{friendlyValidationMessage(datasetError)}</p>
                )}
              </div>
            ) : !marketplaceDatasetReady && !marketplaceImporting && taskType === "regression" ? (
              <div className="space-y-4">
                <div>
                  <p className="text-sm font-semibold text-foreground/90">1. Add all photos</p>
                  <p className="text-xs text-muted-foreground mt-1">Drag every training photo here.</p>
                </div>
                <UploadZone
                  title="Photos"
                  hint="JPG or PNG — all training photos"
                  uploading={imagesUploading}
                  ready={datasetImageCount > 0}
                  statusText={
                    imagesUploading ? "Uploading…" : `${datasetImageCount || 0} photos added`
                  }
                  inputId="regression-images"
                  accept="image/*"
                  multiple
                  onChange={handleRegressionImages}
                />
                <div>
                  <p className="text-sm font-semibold text-foreground/90">2. Add the measurement list</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    One number per photo
                    {projectConfig?.target_name
                      ? ` (column name: ${projectConfig.target_name})`
                      : ""}
                    . Download the example above if you need a starting file.
                  </p>
                </div>
                <UploadZone
                  title="Measurement list"
                  hint="CSV — photo name and number on each row"
                  uploading={targetsUploading}
                  ready={Boolean(projectMeta?.dataset?.file_name)}
                  statusText={
                    targetsUploading
                      ? "Uploading…"
                      : projectMeta?.dataset?.file_name
                        ? projectMeta.dataset.file_name
                        : "No list yet"
                  }
                  inputId="regression-targets"
                  accept=".csv"
                  onChange={handleRegressionTargets}
                />
                {datasetError && (
                  <p className="text-sm text-red-600">{friendlyValidationMessage(datasetError)}</p>
                )}
              </div>
            ) : !marketplaceDatasetReady &&
              !marketplaceImporting &&
              (taskType === "object_localization" || taskType === "object_detection") ? (
              <div className="space-y-4">
                <div className="rounded-xl border border-border/50 bg-muted/40 px-4 py-3 text-sm text-foreground/80">
                  <p className="font-semibold text-foreground">Why a ZIP (not per-group photo upload)?</p>
                  <p className="mt-1 text-muted-foreground">
                    {taskType === "object_localization" ? (
                      <>
                        This task is <strong>object localization</strong> — each photo needs a single
                        drawn box around{" "}
                        {configClasses.length > 0 ? configClasses.join(", ") : "the object"}.
                        Classification can use one folder per group; localization needs a labeled
                        package from a labeling tool (YOLO / COCO / VOC).
                      </>
                    ) : (
                      <>
                        This task is <strong>object detection</strong> — each photo needs drawn boxes
                        around{" "}
                        {configClasses.length > 0 ? configClasses.join(", ") : "your objects"}.
                        Classification can use one folder per group; detection needs a labeled package
                        from a labeling tool (YOLO / COCO / VOC).
                      </>
                    )}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground/90">Upload your labeled package</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    {taskType === "object_localization"
                      ? "One ZIP where each photo has a single box around the object."
                      : "One ZIP where boxes are drawn around the objects in each photo."}
                  </p>
                </div>
                <UploadZone
                  title="Labeled package (ZIP)"
                  hint="Export from your labeling tool, then upload the ZIP here"
                  uploading={annotatedUploading}
                  ready={Boolean(projectMeta?.dataset?.uploaded && projectMeta?.dataset?.validated)}
                  statusText={
                    annotatedUploading
                      ? "Uploading & checking…"
                      : projectMeta?.dataset?.file_name
                        ? projectMeta.dataset.file_name
                        : "No package yet"
                  }
                  inputId="annotated-zip"
                  accept=".zip"
                  onChange={handleAnnotatedUpload}
                  className="max-w-xl"
                />
                {datasetError && (
                  <p className="text-sm text-red-600">{friendlyValidationMessage(datasetError)}</p>
                )}
              </div>
            ) : !marketplaceDatasetReady && !marketplaceImporting ? (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="h-5 w-5 text-amber-600" />
                  <h4 className="text-sm font-semibold text-amber-900">
                    {taskType === "classification" ? "No groups defined" : "Upload not available"}
                  </h4>
                </div>
                <p className="text-xs text-amber-700">
                  {taskType === "classification"
                    ? isModelTemplate
                      ? "Name the groups you want the model to learn (your product names, defect types, etc.), then upload photos for each."
                      : "Add at least two group names (e.g. cat, dog), then upload photos for each group."
                    : "Go back to Step 1 and finish the task setup, or pick a supported model from the Model Library."}
                </p>
                {taskType === "classification" && projectConfig && projectId ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <input
                      type="text"
                      placeholder="Group name"
                      className="h-9 rounded-lg border border-amber-300 bg-card px-3 text-sm outline-none focus:border-primary"
                      id="add-class-input"
                      onKeyDown={(e) => {
                        if (e.key !== "Enter") return;
                        e.preventDefault();
                        const input = e.currentTarget;
                        const name = input.value.trim();
                        if (!name) return;
                        const next = Array.from(new Set([...configClasses, name]));
                        const nextSpec = { ...projectConfig, classes: next };
                        setGeneratedConfig(nextSpec);
                        void saveSpec(projectId, nextSpec).catch((err) =>
                          notify(err instanceof Error ? err.message : "Could not save groups"),
                        );
                        input.value = "";
                      }}
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs border-amber-300 text-amber-700 hover:bg-amber-100"
                      onClick={() => {
                        const input = document.getElementById("add-class-input") as HTMLInputElement | null;
                        const name = input?.value.trim() ?? "";
                        if (!name || !projectConfig || !projectId) return;
                        const next = Array.from(new Set([...configClasses, name]));
                        const nextSpec = { ...projectConfig, classes: next };
                        setGeneratedConfig(nextSpec);
                        void saveSpec(projectId, nextSpec).catch((err) =>
                          notify(err instanceof Error ? err.message : "Could not save groups"),
                        );
                        if (input) input.value = "";
                      }}
                    >
                      <Plus className="h-3 w-3 mr-1" />
                      Add group
                    </Button>
                  </div>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-3 text-xs border-amber-300 text-amber-700 hover:bg-amber-100"
                    onClick={() => setWorkflowStep(1)}
                  >
                    <ChevronLeft className="h-3 w-3 mr-1" />
                    Back to task setup
                  </Button>
                )}
              </div>
            ) : null}

            <DatasetSummaryPanel
              taskType={taskType}
              validated={projectMeta?.dataset?.validated}
              validation={projectMeta?.dataset?.validation}
              classCounts={classCounts}
              totalImages={datasetImageCount}
            />

            <div className="pt-6 border-t border-border/60 flex items-center justify-between">
              <Button
                variant="ghost"
                onClick={() => setWorkflowStep(1)}
                className="text-muted-foreground hover:text-foreground/80"
              >
                <ChevronLeft className="mr-1 h-4 w-4" />
                Back
              </Button>

              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <div
                    className={`h-2 w-2 rounded-full ${datasetReady ? "bg-emerald-500" : "bg-muted-foreground/30"}`}
                  />
                  <span>{datasetReady ? "Ready" : "Still missing steps"}</span>
                </div>
                <Button
                  onClick={() => {
                    setDatasetUploaded(true);
                    setWorkflowStep(3);
                    addEvent("Dataset confirmed", "Review setup before training", "green");
                  }}
                  disabled={!datasetReady}
                  className=" text-white px-6 disabled:opacity-50"
                >
                  Review setup
                  <ChevronRight className="ml-2 h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Training Configuration */}
      {workflowStep === 3 && (
        <div className="bg-card rounded-2xl border border-border/60 shadow-sm overflow-hidden">
          {/* Header */}
          <div className="border-b border-border/60 bg-gradient-to-r from-muted/30 to-card px-8 py-6">
            <div className="flex items-center gap-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-white shadow-lg shadow-blue-200">
                <span className="text-sm font-bold">3</span>
              </div>
              <div>
                <h3 className="text-xl font-bold text-foreground">Review training setup</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Pipeline settings are chosen automatically from your dataset images — review below, then complete setup.
                </p>
              </div>
            </div>
          </div>

          <div className="p-8 space-y-6">
            {!datasetReady && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="h-5 w-5 text-amber-600" />
                  <h4 className="text-sm font-semibold text-amber-900">Training data still needed</h4>
                </div>
                <p className="text-sm text-amber-800">
                  Upload and validate your labeled photos in Step 2 before starting training.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3 text-xs border-amber-300 text-amber-700 hover:bg-amber-100"
                  onClick={() => setWorkflowStep(2)}
                >
                  Go to dataset upload
                  <ChevronRight className="ml-1 h-3 w-3" />
                </Button>
              </div>
            )}
            {generatedConfig ? (
              <div className="bg-muted/40 rounded-xl border border-border/60 p-6">
                <h4 className="text-lg font-bold text-foreground mb-4">
                  {generatedConfig.project_name}
                </h4>
                <ConfigSummaryPanel
                  config={generatedConfig}
                  projectId={projectId}
                  inference={projectMeta?.inference}
                  onRotateApiKey={handleRotateApiKey}
                />
                <ConfigPipelineEditor
                  config={generatedConfig}
                  readOnly
                  tuning={pipelineTuning}
                  rationale={pipelineRationale}
                />
                {trainingInfo?.mode === "azure" && (
                  <p className="mt-4 text-sm text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1">
                    <span className="inline-flex items-center gap-1">
                      <Server className="h-3.5 w-3.5" />
                      Cloud GPU training
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3.5 w-3.5" />
                      {trainingInfoLoading ? "…" : displayDuration}
                    </span>
                    <span className="inline-flex items-center gap-1 text-emerald-700">
                      <DollarSign className="h-3.5 w-3.5" />
                      {trainingInfoLoading ? "…" : stripLeadingDollar(displayCost) || displayCost}
                    </span>
                  </p>
                )}
              </div>
            ) : (
              <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-4">
                Go back to Step 1 and use <strong>Generate Config</strong> after chatting with the assistant.
              </p>
            )}

            <div className="bg-muted/40 rounded-xl border border-border/60 p-6">
              {/* Azure ML Training Progress */}
              {projectId &&
                ["ready_for_training", "training_complete", "training_failed"].includes(
                  projectMeta?.status ?? "",
                ) && (
                <TrainingProgress
                  projectId={projectId}
                  taskType={taskType}
                  datasetUrl={
                    (projectMeta?.dataset as { blob_url?: string; url?: string })?.blob_url ||
                    (projectMeta?.dataset as { url?: string })?.url ||
                    ""
                  }
                  datasetBlobKey={
                    (projectMeta?.dataset as { storage_key?: string })?.storage_key ||
                    (projectId && taskType === "classification"
                      ? `projects/${projectId}/datasets/classification/`
                      : "")
                  }
                  config={trainingHp}
                  trainingInfo={trainingInfo}
                  trainingInfoLoading={trainingInfoLoading}
                  trainingInfoError={trainingInfoError}
                  savedTraining={projectMeta?.training ?? null}
                  onComplete={(modelInfo) => {
                    const m = modelInfo.metrics;
                    const mapLabel =
                      m?.mAP50 != null
                        ? `mAP@50 ${(m.mAP50 <= 1 ? m.mAP50 * 100 : m.mAP50).toFixed(1)}%`
                        : modelInfo.job_id;
                    addEvent("Training completed", mapLabel, "green");
                    void refreshProject(projectId).then((b) => setProjectMeta(b.project));
                  }}
                  onJobStarted={() => {
                    /* Avoid refresh here — stale meta.training.status=Submitting overwrote live poll */
                  }}
                  onError={(error) => {
                    addEvent("Training failed", error, "red");
                    void refreshProject(projectId).then((b) => setProjectMeta(b.project));
                  }}
                />
              )}

              {!projectId &&
                ["ready_for_training", "training_complete", "training_failed"].includes(
                  projectMeta?.status ?? "",
                ) && (
                <div className="mt-6 bg-amber-50 rounded-lg border border-amber-200 p-4 text-sm text-amber-800">
                  Project ID not found. Cannot start training.
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="pt-6 border-t border-border/60 flex items-center justify-between">
              <Button 
                variant="ghost" 
                onClick={() => setWorkflowStep(2)}
                className="text-muted-foreground hover:text-foreground/80"
              >
                <ChevronLeft className="mr-1 h-4 w-4" />
                Back
              </Button>
              
              <div className="flex items-center gap-4">
                <Button
                  onClick={() => {
                    if (!projectId) return;
                    void completeSetup(projectId)
                      .then((r) => {
                        setProjectMeta(r.project);
                        setTrainingStarted(true);
                        addEvent("Ready for training", r.message, "green");
                      })
                      .catch((e) => addEvent("Setup incomplete", e.message, "amber"));
                  }}
                  className=" text-white px-6 disabled:opacity-50"
                  disabled={
                    trainingStarted ||
                    projectMeta?.status === "ready_for_training" ||
                    projectMeta?.status === "training_complete" ||
                    projectMeta?.status === "training_failed" ||
                    !generatedConfig ||
                    !datasetReady
                  }
                  title={
                    projectMeta?.status === "training_complete"
                      ? "Training already finished — use Train again or open Inference"
                      : !datasetReady
                        ? "Finish Step 2: upload and validate your training dataset first"
                        : projectMeta?.status === "ready_for_training" || trainingStarted
                          ? "Setup already marked ready"
                          : undefined
                  }
                >
                  {projectMeta?.status === "training_complete" ? (
                    <>
                      <Check className="mr-2 h-4 w-4" />
                      Training complete
                    </>
                  ) : projectMeta?.status === "ready_for_training" || trainingStarted ? (
                    <>
                      <Check className="mr-2 h-4 w-4" />
                      Ready for training
                    </>
                  ) : (
                    <>
                      Complete setup
                      <ChevronRight className="ml-2 h-4 w-4" />
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function UploadZone({
  title,
  hint,
  statusText,
  uploading,
  ready,
  inputId,
  accept,
  multiple,
  onChange,
  className = "",
}: {
  title: string;
  hint: string;
  statusText: string;
  uploading: boolean;
  ready: boolean;
  inputId: string;
  accept: string;
  multiple?: boolean;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  className?: string;
}) {
  return (
    <label
      htmlFor={inputId}
      className={`relative block cursor-pointer rounded-xl border-2 border-dashed p-6 transition-all ${
        ready
          ? "border-emerald-300 bg-emerald-50/40 hover:border-emerald-400"
          : "border-border bg-muted/40 hover:border-primary/40 hover:bg-primary/8/30"
      } ${className}`}
    >
      <input
        id={inputId}
        type="file"
        className="hidden"
        accept={accept}
        multiple={multiple}
        onChange={onChange}
      />
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-base font-semibold text-foreground">{title}</h4>
          <p className="text-xs text-muted-foreground mt-1">{uploading ? "Uploading…" : statusText}</p>
        </div>
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
            ready ? "bg-emerald-100" : "bg-card border border-border/60"
          }`}
        >
          {uploading ? (
            <div className="h-4 w-4 border-2 border-primary/30 border-t-blue-600 rounded-full animate-spin" />
          ) : ready ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-600" />
          ) : (
            <ImagePlus className="h-5 w-5 text-primary" />
          )}
        </div>
      </div>
      <p className="text-xs text-muted-foreground/70 mt-3">{hint}</p>
    </label>
  );
}
