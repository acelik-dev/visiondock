export type TaskType =
  | "classification"
  | "multi_label"
  | "regression"
  | "object_localization"
  | "object_detection";

export type DiscoveryInfo = {
  ready_for_config: boolean;
  detected_task: TaskType | null;
  user_turn_count: number;
  slots: Record<string, boolean>;
  missing_slots: string[];
  progress_percent: number;
  vlm_ready_signal: boolean;
  needs_class_list?: boolean;
};

export type ProjectSpec = {
  spec_version?: string;
  project_name: string;
  task_type: TaskType;
  recommended_model: string;
  description?: string;
  classes: string[];
  target_name?: string;
  target_unit?: string;
  estimated_dataset_size?: string;
  training_config?: {
    epochs?: number;
    batch_size?: number;
    learning_rate?: number;
    image_size?: string;
    optimizer?: string;
    scheduler?: string;
    early_stopping_patience?: number;
    validation_split?: number;
    augmentation?: boolean;
    mixup?: boolean;
    cutmix?: boolean;
    label_smoothing?: number;
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
    confidence_threshold?: number;
    nms_iou_threshold?: number;
    tta?: boolean;
    ensemble?: boolean;
    sahi?: boolean;
    sahi_slice_size?: number;
    sahi_overlap_ratio?: number;
    auto_tune_thresholds?: boolean;
    export_format?: string[];
  };
  hardware_requirements?: {
    gpu?: string;
    vram_gb?: number;
    estimated_training_time?: string;
    estimated_cost?: string;
  };
};

export const SLOT_LABELS: Record<string, string> = {
  use_case: "Your goal",
  task_type: "How the AI should work",
  objects_or_defects: "What to look for",
  environment: "Where cameras run",
  throughput: "How fast you need answers",
};

export const DISCOVERY_HINTS: Record<string, string> = {
  use_case: "what you want the system to do",
  task_type: "whether you need categories, multiple labels, a numeric score, or bounding boxes",
  objects_or_defects: "which labels, classes, or target value matter",
  environment: "factory line, fixed camera, outdoor site, etc.",
  throughput: "real-time alerts vs batch review",
};

export const TASK_LABELS: Record<TaskType, string> = {
  classification: "One group per photo",
  multi_label: "Several tags per photo",
  regression: "Predict a number",
  object_localization: "Find one object",
  object_detection: "Find several objects",
};

export const DATASET_FORMAT_HINTS: Record<TaskType, string> = {
  classification:
    "Upload photos into a separate folder for each group (for example: OK or Defect).",
  multi_label:
    "Add your photos, then a simple list that says which tags each photo has.",
  regression:
    "Add your photos, then a list with one number for each photo (age, thickness, score…).",
  object_localization:
    "Upload a labeled package (ZIP) where each photo has one box drawn around the object.",
  object_detection:
    "Upload a labeled package (ZIP) where boxes are drawn around the objects in each photo.",
};
