import { resolveApiBase } from "@/lib/api-base";
import { parseJsonResponse } from "@/lib/projects-api";

const PYTHON_API = resolveApiBase();

export type TrainingInfo = {
  mode: "azure" | "mock";
  sdk_installed: boolean;
  sdk_import_error: string | null;
  init_error: string | null;
  workspace: string;
  resource_group: string;
  subscription_id_set: boolean;
  storage_configured: boolean;
  compute: string;
  vm_size?: string;
  gpu?: string;
  vram_gb?: number | null;
  environment?: string;
  location?: string;
  estimated_duration?: string;
  estimated_cost?: string;
  minutes_per_epoch?: number;
};

export function parseImageSize(imgsz?: string | number): number {
  if (typeof imgsz === "number") return imgsz;
  if (!imgsz) return 224;
  const m = String(imgsz).match(/(\d+)/);
  return m ? Number(m[1]) : 224;
}

export function yoloWeightsFromSpec(spec: {
  task_type?: string;
  recommended_model?: string;
} | null): string {
  const task = spec?.task_type ?? "object_detection";
  const recommended = (spec?.recommended_model ?? "").toLowerCase().replace(/[-_\s]/g, "");
  for (const family of ["yolo11", "yolov10", "yolov9", "yolov8"]) {
    for (const size of ["n", "s", "m", "l", "x"]) {
      if (recommended.includes(`${family}${size}`)) {
        return `${family}${size}.pt`;
      }
    }
  }
  if (task === "object_localization") return "yolov8n.pt";
  return "yolov8m.pt";
}

export function trainingConfigFromSpec(spec: {
  task_type?: string;
  recommended_model?: string;
  training_config?: {
    epochs?: number;
    batch_size?: number;
    learning_rate?: number;
    image_size?: string;
    validation_split?: number;
    early_stopping_patience?: number;
    augmentation?: boolean;
    mixup?: boolean;
    cutmix?: boolean;
    label_smoothing?: number;
    optimizer?: string;
    scheduler?: string;
  };
  preprocessing?: {
    resize?: string;
    normalize?: { mean: number[]; std: number[] };
    grayscale?: boolean;
    denoise?: boolean;
    contrast_enhancement?: boolean;
    auto_orientation?: boolean;
  };
  postprocessing?: {
    auto_tune_thresholds?: boolean;
    confidence_threshold?: number;
    nms_iou_threshold?: number;
    tta?: boolean;
    ensemble?: boolean;
    sahi?: boolean;
    sahi_slice_size?: number;
    sahi_overlap_ratio?: number;
    export_format?: string[];
  };
} | null) {
  const tc = spec?.training_config;
  const recommended = (spec?.recommended_model ?? "").toLowerCase();
  const isYolo = spec?.task_type === "object_detection" || spec?.task_type === "object_localization";
  let model_name = "efficientnet_b0";
  if (recommended.includes("b2") || recommended.includes("efficientnet-b2")) {
    model_name = "efficientnet_b2";
  }
  const base = {
    epochs: tc?.epochs ?? (isYolo ? 100 : 30),
    imgsz: parseImageSize(tc?.image_size ?? (isYolo ? "640x640" : "224x224")),
    batch: tc?.batch_size ?? 16,
    learning_rate: tc?.learning_rate ?? (isYolo ? 0.01 : 0.001),
    validation_split: tc?.validation_split ?? 0.2,
    model_name,
    patience: tc?.early_stopping_patience ?? 20,
    augmentation: tc?.augmentation ?? true,
    mixup: tc?.mixup ?? false,
    cutmix: tc?.cutmix ?? false,
    label_smoothing: tc?.label_smoothing ?? 0,
    optimizer: tc?.optimizer ?? "AdamW",
    scheduler: tc?.scheduler ?? "cosine",
    auto_tune_thresholds: spec?.postprocessing?.auto_tune_thresholds !== false,
    preprocessing: spec?.preprocessing,
    postprocessing: spec?.postprocessing,
  };
  if (isYolo) {
    return { ...base, yolo_weights: yoloWeightsFromSpec(spec) };
  }
  return base;
}

export type TrainingMetrics = {
  epoch?: number;
  loss?: number;
  mAP?: number;
  mAP50?: number;
  mAP50_95?: number;
  precision?: number;
  recall?: number;
  accuracy?: number;
  val_accuracy?: number;
  f1?: number;
  micro_f1?: number;
  macro_f1?: number;
  mae?: number;
  rmse?: number;
  mse?: number;
  r2?: number;
};

export type SavedTrainingJob = {
  job_id: string;
  status: string;
  status_message?: string;
  display_name?: string;
  experiment?: string;
  start_time?: string;
  end_time?: string;
  duration_seconds?: number;
  compute?: string;
  metrics?: TrainingMetrics;
  logs_url?: string;
  job_url?: string;
  submitted_at?: string;
  updated_at?: string;
};

export function formatMetricPercent(value: number | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const pct = value <= 1 ? value * 100 : value;
  return `${pct.toFixed(1)}%`;
}

export function formatMetricNumber(value: number | undefined, digits = 4): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export async function fetchTrainingInfo(epochs = 100): Promise<TrainingInfo> {
  const res = await fetch(
    `${PYTHON_API}/api/training/info?epochs=${encodeURIComponent(String(epochs))}`,
    { credentials: "include" },
  );
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    throw new Error(
      typeof data.detail === "string" ? data.detail : "Failed to load training info",
    );
  }
  return data as TrainingInfo;
}
