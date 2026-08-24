import { useState, useEffect, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { TrainingMetricsPanel } from "@/components/training-metrics-panel";
import { DeploymentTimeline, GpuUtilBar } from "@/components/premium/deployment-timeline";
import { parseJsonResponse } from "@/lib/projects-api";
import { resolveApiBase } from "@/lib/api-base";
import type { TrainingInfo, SavedTrainingJob, TrainingMetrics } from "@/lib/training-api";
import { useStore } from "@/lib/store";
import { announceCreditSpend, refreshCreditsShared, useCredits } from "@/hooks/use-credits";
import { costLabel } from "@/lib/credits-api";
import {
  Play,
  Square,
  RotateCw,
  ExternalLink,
  Clock,
  CheckCircle2,
  AlertCircle,
  Cpu,
  BarChart3,
  Cloud,
} from "lucide-react";

interface TrainingJob {
  job_id: string;
  status: string;
  display_name: string;
  experiment: string;
  start_time?: string;
  end_time?: string;
  duration_seconds?: number;
  compute?: string;
  metrics?: TrainingMetrics;
  logs_url?: string;
  job_url?: string;
  status_message?: string;
  error?: string;
}

interface TrainingProgressProps {
  projectId: string;
  taskType: string;
  datasetUrl: string;
  datasetBlobKey?: string;
  config: Record<string, any>;
  trainingInfo?: TrainingInfo | null;
  trainingInfoLoading?: boolean;
  trainingInfoError?: string | null;
  savedTraining?: SavedTrainingJob | null;
  onComplete?: (modelInfo: TrainingJob) => void;
  onError?: (error: string) => void;
  onJobStarted?: (modelInfo: TrainingJob) => void;
}

function InferenceNavButton() {
  const setCurrentView = useStore((s) => s.setCurrentView);
  return (
    <Button size="sm" variant="outline" onClick={() => setCurrentView("inference")}>
      <Cloud className="mr-1 h-4 w-4" />
      Inference & API keys
    </Button>
  );
}

const PYTHON_API = resolveApiBase();

const TERMINAL_STATUSES = ["Completed", "Failed", "Cancelled"];
const POLL_MS = 2000;

const STATUS_RANK: Record<string, number> = {
  Submitting: 1,
  Queued: 2,
  Starting: 3,
  Running: 4,
  Finalizing: 5,
  Completed: 6,
  Failed: 6,
  Cancelled: 6,
};

function statusRank(status: string): number {
  return STATUS_RANK[status] ?? 0;
}

function mergeJobState(current: TrainingJob | null, incoming: TrainingJob): TrainingJob {
  if (!current || current.job_id !== incoming.job_id) {
    return incoming;
  }
  if (statusRank(incoming.status) >= statusRank(current.status)) {
    return { ...current, ...incoming };
  }
  return { ...incoming, ...current, status: current.status };
}

function trainingTimelineSteps(job: TrainingJob): { id: string; label: string; status: "pending" | "active" | "done" | "error"; detail?: string }[] {
  const rank = statusRank(job.status);
  const step = (id: string, label: string, threshold: number, detail?: string) => {
    if (job.status === "Failed" && threshold >= rank) {
      return { id, label, status: "error" as const, detail: job.error || job.status_message };
    }
    if (rank > threshold) return { id, label, status: "done" as const, detail };
    if (rank === threshold) return { id, label, status: "active" as const, detail: job.status_message || detail };
    return { id, label, status: "pending" as const, detail };
  };
  return [
    step("submit", "Submit to Azure ML", 1, "Registering job and uploading scripts"),
    step("queue", "GPU cluster starting", 2, "Scale-up from idle — often 3–8 min"),
    step("train", "Training in progress", 4, job.compute || "gpu-cluster"),
    step("finalize", "Finalizing model", 5),
    step("done", "Complete", 6),
  ];
}

function estimateGpuUtil(job: TrainingJob): number {
  if (job.status === "Completed") return 0;
  if (job.status === "Running") return 72 + Math.round((calculateProgressFromJob(job) % 20));
  if (job.status === "Queued" || job.status === "Starting") return 12;
  return 0;
}

function calculateProgressFromJob(job: TrainingJob): number {
  if (job.status === "Completed") return 100;
  if (job.status === "Failed" || job.status === "Cancelled") return 0;
  const epoch = job.metrics?.epoch;
  const total = (job as { config?: { epochs?: number } }).config?.epochs;
  if (epoch != null && total) return Math.min(95, Math.round((epoch / total) * 100));
  const rank = statusRank(job.status);
  return Math.min(90, rank * 18);
}

function hasTrainingMetrics(metrics?: TrainingMetrics): boolean {
  if (!metrics) return false;
  return Boolean(
    metrics.mAP50 ??
      metrics.mAP ??
      metrics.precision ??
      metrics.accuracy ??
      metrics.val_accuracy ??
      metrics.f1 ??
      metrics.macro_f1 ??
      metrics.mae ??
      metrics.rmse ??
      metrics.loss,
  );
}

function savedToJob(saved: SavedTrainingJob): TrainingJob {
  return {
    job_id: saved.job_id,
    status: saved.status,
    display_name: saved.display_name || saved.job_id,
    experiment: saved.experiment || "",
    start_time: saved.start_time,
    end_time: saved.end_time,
    duration_seconds: saved.duration_seconds,
    compute: saved.compute,
    metrics: saved.metrics,
    logs_url: saved.logs_url,
    job_url: saved.job_url,
    status_message: saved.status_message,
  };
}

export function TrainingProgress({
  projectId,
  taskType,
  datasetUrl,
  datasetBlobKey = "",
  config,
  trainingInfo = null,
  trainingInfoLoading = false,
  trainingInfoError = null,
  savedTraining = null,
  onComplete,
  onError,
  onJobStarted,
}: TrainingProgressProps) {
  const dismissedJobIdRef = useRef<string | null>(null);
  const [job, setJob] = useState<TrainingJob | null>(
    savedTraining?.job_id ? savedToJob(savedTraining) : null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);
  const { account, canAfford, cost } = useCredits();
  const trainCost = cost("training_submit");
  const enoughCredits = canAfford("training_submit");
  const notify = useStore((s) => s.notify);

  const trainingMode: "loading" | "azure" | "mock" | "error" = trainingInfoLoading
    ? "loading"
    : trainingInfo?.mode === "azure"
      ? "azure"
      : trainingInfo
        ? "mock"
        : "error";

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      Queued: "bg-yellow-500",
      Submitting: "bg-yellow-500",
      Starting: "bg-primary",
      Running: "bg-green-500",
      Finalizing: "bg-purple-500",
      Completed: "bg-emerald-600",
      Failed: "bg-red-500",
      Cancelled: "bg-gray-500",
    };
    return colors[status] || "bg-gray-400";
  };

  const stopPolling = useCallback(() => {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      setPollingInterval(null);
    }
  }, [pollingInterval]);

  const pollStatus = useCallback(
    async (jobId: string) => {
      try {
        const response = await fetch(`${PYTHON_API}/api/training/status/${jobId}`, {
          credentials: "include",
        });
        const result = await parseJsonResponse(response);

        if (result.success && result.data) {
          const jobData = result.data as TrainingJob;
          setJob((current) => mergeJobState(current, jobData));

          if (jobData.status === "Submitting") {
            return;
          }

          // Live balance: AML accepted the job and credits were charged in the background.
          void refreshCreditsShared();

          if (TERMINAL_STATUSES.includes(jobData.status)) {
            const hasMetrics = hasTrainingMetrics(jobData.metrics);
            if (jobData.status !== "Completed" || hasMetrics) {
              stopPolling();
            }

            if (jobData.status === "Completed" && hasMetrics) {
              stopPolling();
              onComplete?.(jobData);
            } else if (jobData.status === "Failed") {
              stopPolling();
              onError?.(jobData.error || "Training job failed");
            }
          }
        } else if (!response.ok) {
          const detail =
            typeof result.detail === "string"
              ? result.detail
              : "Training status check failed";
          setJob((current) =>
            current
              ? {
                  ...current,
                  status: "Failed",
                  error: detail,
                }
              : current,
          );
          stopPolling();
          onError?.(detail);
        }
      } catch (err) {
        console.error("Failed to poll status:", err);
      }
    },
    [onComplete, onError, stopPolling],
  );

  const startPolling = useCallback(
    (jobId: string) => {
      void pollStatus(jobId);
      const interval = setInterval(() => {
        void pollStatus(jobId);
      }, POLL_MS);
      setPollingInterval(interval);
    },
    [pollStatus],
  );

  const restoredJobIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!savedTraining?.job_id) return;
    if (dismissedJobIdRef.current === savedTraining.job_id) return;
    const restored = savedToJob(savedTraining);
    setJob((current) => mergeJobState(current, restored));
    if (restoredJobIdRef.current !== savedTraining.job_id) {
      restoredJobIdRef.current = savedTraining.job_id;
      const needsMetrics =
        restored.status === "Completed" && !hasTrainingMetrics(restored.metrics);
      const needsTiming =
        restored.status === "Completed" &&
        restored.duration_seconds == null &&
        !restored.end_time;
      if (!TERMINAL_STATUSES.includes(restored.status) || needsMetrics || needsTiming) {
        startPolling(restored.job_id);
      }
    }
  }, [savedTraining?.job_id, startPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const startTraining = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${PYTHON_API}/api/training/submit`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          dataset_url: datasetUrl,
          dataset_blob_key: datasetBlobKey,
          task_type: taskType,
          config: {
            epochs: Number(config.epochs) || 50,
            imgsz: Number(config.imgsz) || 640,
            batch: Number(config.batch) || 16,
            learning_rate: Number(config.learning_rate) || 0.01,
            validation_split: Number((config as { validation_split?: number }).validation_split) || 0.2,
            model_name: (config as { model_name?: string }).model_name || "efficientnet_b0",
            yolo_weights: (config as { yolo_weights?: string }).yolo_weights,
            patience: Number((config as { patience?: number }).patience) || 20,
            augmentation: (config as { augmentation?: boolean }).augmentation !== false,
            mixup: Boolean((config as { mixup?: boolean }).mixup),
            cutmix: Boolean((config as { cutmix?: boolean }).cutmix),
            label_smoothing: Number((config as { label_smoothing?: number }).label_smoothing) || 0,
            optimizer: (config as { optimizer?: string }).optimizer || "AdamW",
            scheduler: (config as { scheduler?: string }).scheduler || "cosine",
            auto_tune_thresholds:
              (config as { auto_tune_thresholds?: boolean }).auto_tune_thresholds !== false,
            preprocessing: (config as { preprocessing?: Record<string, unknown> }).preprocessing,
            postprocessing: (config as { postprocessing?: Record<string, unknown> }).postprocessing,
            nodes: 1,
          },
        }),
      });

      const result = await parseJsonResponse(response);

      if (!response.ok || !result.success) {
        const detail = result.detail;
        const msg =
          typeof detail === "string"
            ? detail
            : typeof detail === "object" && detail && "message" in detail
              ? String((detail as { message?: string }).message)
              : Array.isArray(detail)
                ? detail
                    .map((d) =>
                      typeof d === "object" && d && "msg" in d
                        ? String((d as { msg?: string }).msg)
                        : "",
                    )
                    .join(", ")
                : "Failed to submit training job";
        throw new Error(msg);
      }

      if (result.credits) {
        announceCreditSpend(result.credits as { balance?: number; debited?: number }, notify);
      }

      const data = result.data as TrainingJob | undefined;
      if (!data?.job_id) {
        throw new Error("Training started but no job_id was returned");
      }
      setJob(data);
      dismissedJobIdRef.current = null;
      startPolling(data.job_id);
      onJobStarted?.(data);
      setIsLoading(false);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Unknown error";
      setError(errorMsg);
      onError?.(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  const cancelTraining = async () => {
    if (!job) return;

    try {
      const response = await fetch(`${PYTHON_API}/api/training/cancel/${job.job_id}`, {
        method: "POST",
      });
      const result = await response.json();

      if (result.success) {
        stopPolling();
        setJob((prev) => (prev ? { ...prev, status: "Cancelled" } : null));
      }
    } catch (err) {
      console.error("Failed to cancel job:", err);
    }
  };

  const handleRetrain = () => {
    if (job?.job_id) {
      dismissedJobIdRef.current = job.job_id;
    }
    stopPolling();
    setError(null);
    void startTraining();
  };

  const calculateProgress = () => {
    if (!job) return 0;
    if (job.status === "Completed") return 100;
    if (job.status === "Failed" || job.status === "Cancelled") return 0;
    if (job.metrics?.epoch && config.epochs) {
      return Math.min((job.metrics.epoch / config.epochs) * 100, 99);
    }
    const byStatus: Record<string, number> = {
      Submitting: 8,
      Queued: 12,
      Starting: 20,
      Running: 55,
      Finalizing: 90,
    };
    return byStatus[job.status] ?? 15;
  };

  const formatDuration = () => {
    const formatSeconds = (totalSeconds: number) => {
      const hours = Math.floor(totalSeconds / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = Math.floor(totalSeconds % 60);
      return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
    };

    if (job?.duration_seconds != null && job.duration_seconds > 0) {
      return formatSeconds(job.duration_seconds);
    }

    if (!job?.start_time) return "--:--:--";

    const start = new Date(job.start_time);
    const isDone = job.status === "Completed" || job.status === "Failed" || job.status === "Cancelled";
    const end = job.end_time
      ? new Date(job.end_time)
      : isDone
        ? null
        : new Date();
    if (!end) return "--:--:--";

    const diff = Math.max(0, end.getTime() - start.getTime());
    return formatSeconds(diff / 1000);
  };

  if (!job) {
    return (
      <Card className="border-dashed">
        <CardContent className="pt-6">
          <div className="text-center space-y-4">
            <div className="p-4 bg-primary/8 rounded-full w-fit mx-auto">
              <Cpu className="h-8 w-8 text-primary" />
            </div>
            <div>
              <h3 className="text-lg font-semibold">Start Model Training</h3>
              <p className="text-sm text-muted-foreground">
                Train a {taskType} model on Azure ML with GPU acceleration
              </p>
              {trainingMode === "loading" && (
                <p className="text-xs text-muted-foreground mt-2">Checking Azure ML connection…</p>
              )}
              {trainingMode === "mock" && (
                <p className="text-xs text-amber-700 mt-2">
                  {trainingInfo?.init_error ||
                    trainingInfo?.sdk_import_error ||
                    "Mock mode — Azure ML is not configured on the server."}
                </p>
              )}
              {trainingMode === "azure" && trainingInfo && (
                <p className="text-xs text-emerald-700 mt-2">
                  Azure ML · {trainingInfo.workspace} · {trainingInfo.compute} ({trainingInfo.gpu})
                </p>
              )}
            </div>
            <div className="flex flex-wrap justify-center gap-4 text-sm text-muted-foreground">
              <span className="flex items-center gap-1">
                <Clock className="h-4 w-4" />
                {trainingInfo?.estimated_duration ??
                  `~${Math.round((config.epochs || 100) * (trainingInfo?.minutes_per_epoch ?? 4))} min`}
              </span>
              <span className="flex items-center gap-1">
                <BarChart3 className="h-4 w-4" />
                Automated training setup
              </span>
              {trainingInfo?.estimated_cost && (
                <span className="flex items-center gap-1">Est. {trainingInfo.estimated_cost}</span>
              )}
              <span className="flex items-center gap-1 font-medium text-amber-800">
                Needs {costLabel(account?.costs, "training_submit")}
              </span>
            </div>
            <Button
              onClick={startTraining}
              disabled={
                isLoading ||
                trainingMode === "loading" ||
                trainingMode === "error" ||
                !enoughCredits
              }
              className="w-full sm:w-auto"
            >
              {isLoading ? (
                <>
                  <RotateCw className="mr-2 h-4 w-4 animate-spin" />
                  Submitting...
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Start Training
                </>
              )}
            </Button>
            {!enoughCredits && (
              <p className="text-sm text-amber-800">
                Need {trainCost} credits (balance {account?.balance ?? 0}). Activate a plan under Billing.
              </p>
            )}
            {error && (
              <p className="text-sm text-red-500 flex items-center justify-center gap-1">
                <AlertCircle className="h-4 w-4" />
                {error}
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  const isComplete = job.status === "Completed";
  const isFailed = job.status === "Failed";
  const isCancelled = job.status === "Cancelled";
  const isQueued = job.status === "Queued" || job.status === "Starting";
  const canRetrain = isComplete || isFailed || isCancelled;
  const showProgress = !isComplete && !isFailed && !isCancelled;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-full ${getStatusColor(job.status)}`}>
              {isComplete ? (
                <CheckCircle2 className="h-4 w-4 text-white" />
              ) : isFailed ? (
                <AlertCircle className="h-4 w-4 text-white" />
              ) : job.status === "Running" ? (
                <Cpu className="h-4 w-4 text-white animate-pulse" />
              ) : (
                <Clock className="h-4 w-4 text-white" />
              )}
            </div>
            <div>
              <CardTitle className="text-base">
                {isComplete
                  ? "Training complete"
                  : isFailed
                    ? "Training failed"
                    : "Training job"}
              </CardTitle>
              <p className="text-xs text-muted-foreground">{job.display_name}</p>
            </div>
          </div>
          <Badge className={getStatusColor(job.status)}>{job.status}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isFailed && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            Training did not finish successfully. Check logs in Azure ML, then use{" "}
            <strong>Train again</strong> to start a new run with the same dataset.
          </div>
        )}

        {job.status === "Submitting" && (
          <div className="rounded-lg border border-primary/20 bg-primary/8 px-4 py-3 text-sm text-primary flex items-center gap-2">
            <RotateCw className="h-4 w-4 animate-spin shrink-0" />
            Registering job with Azure ML — this usually takes under a minute.
          </div>
        )}

        {isQueued && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <p className="flex items-center gap-2 font-medium">
              <Clock className="h-4 w-4 shrink-0" />
              GPU cluster is starting
            </p>
            <p className="mt-1 text-amber-800">
              {job.status_message ||
                "Azure is resizing gpu-cluster (scale-up from idle). First start after a break often takes 3–8 minutes — this is normal, not a VisionDock bug."}
            </p>
          </div>
        )}

        {showProgress && (
          <div className="space-y-4">
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-border/40 bg-muted/20 p-4">
                <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Deployment pipeline</p>
                <DeploymentTimeline steps={trainingTimelineSteps(job)} />
              </div>
              {(job.status === "Running" || job.status === "Queued" || job.status === "Starting") && (
                <GpuUtilBar percent={estimateGpuUtil(job)} />
              )}
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Progress</span>
                <span className="font-medium">{Math.round(calculateProgress())}%</span>
              </div>
              <Progress value={calculateProgress()} className="h-2" />
            </div>
          </div>
        )}

        <TrainingMetricsPanel
          metrics={job.metrics || {}}
          completed={isComplete}
        />

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 text-sm">
          <div className="rounded-lg bg-muted/40 px-3 py-2">
            <p className="text-xs text-muted-foreground">Duration</p>
            <p className="font-medium">{formatDuration()}</p>
          </div>
          <div className="rounded-lg bg-muted/40 px-3 py-2">
            <p className="text-xs text-muted-foreground">Compute</p>
            <p className="font-medium">{job.compute || "gpu-cluster"}</p>
          </div>
          <div className="rounded-lg bg-muted/40 px-3 py-2">
            <p className="text-xs text-muted-foreground">Job ID</p>
            <p className="font-medium truncate">{job.job_id}</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 pt-1">
          {canRetrain && (
            <Button
              size="sm"
              onClick={handleRetrain}
              disabled={isLoading || trainingMode === "loading" || trainingMode === "error"}
              className=" text-white"
            >
              {isLoading ? (
                <>
                  <RotateCw className="mr-1 h-4 w-4 animate-spin" />
                  Starting…
                </>
              ) : (
                <>
                  <RotateCw className="mr-1 h-4 w-4" />
                  Train again
                </>
              )}
            </Button>
          )}
          {job.status === "Running" && (
            <Button variant="outline" size="sm" onClick={cancelTraining}>
              <Square className="mr-1 h-4 w-4" />
              Cancel
            </Button>
          )}
          {(job.logs_url || job.job_url) && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open(job.logs_url || job.job_url!, "_blank")}
            >
              <ExternalLink className="mr-1 h-4 w-4" />
              View in Azure ML
            </Button>
          )}
          {isComplete && <InferenceNavButton />}
        </div>

        {job.start_time && (
          <p className="text-xs text-muted-foreground border-t pt-3">
            Started: {new Date(job.start_time).toLocaleString()}
            {job.end_time && ` · Finished: ${new Date(job.end_time).toLocaleString()}`}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default TrainingProgress;
