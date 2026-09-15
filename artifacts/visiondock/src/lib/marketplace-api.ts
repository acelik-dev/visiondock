import { resolveApiBase } from "@/lib/api-base";
import type { TaskType } from "@/lib/project-spec";
import { parseJsonResponse } from "@/lib/projects-api";

const API_BASE = resolveApiBase();

export type MarketplaceDataset = {
  id: string;
  name: string;
  task_type: TaskType;
  description: string;
  license: string;
  storage_prefix: string;
  format: string;
  size_bytes: number;
  size_label: string;
  image_count: number;
  class_count: number;
  classes: string[];
  target_name?: string;
  target_unit?: string;
  year?: number | null;
  tags?: string[];
  industries?: string[];
  source_url?: string | null;
};

export type MarketplaceModel = {
  id: string;
  name: string;
  task_type: TaskType;
  description: string;
  license: string;
  storage_prefix: string;
  architecture: string;
  input_resolution: string;
  metrics: Record<string, number>;
  classes: string[];
  target_name?: string;
  target_unit?: string;
  tags?: string[];
  industries?: string[];
  trained_on?: string | null;
};

export const MARKETPLACE_TASK_TYPES: { id: TaskType | "all"; label: string }[] = [
  { id: "all", label: "All tasks" },
  { id: "classification", label: "Classification" },
  { id: "multi_label", label: "Multi-label" },
  { id: "regression", label: "Regression" },
  { id: "object_localization", label: "Localization" },
  { id: "object_detection", label: "Detection" },
];

export const MARKETPLACE_INDUSTRIES = [
  "Manufacturing",
  "Agriculture",
  "Construction",
  "Logistics",
  "Sports",
  "Self Driving",
  "Gaming",
  "Documents",
] as const;

export type MarketplaceIndustry = (typeof MARKETPLACE_INDUSTRIES)[number];

export const MARKETPLACE_INDUSTRY_OPTIONS: { id: MarketplaceIndustry | "all"; label: string }[] = [
  { id: "all", label: "All industries" },
  ...MARKETPLACE_INDUSTRIES.map((id) => ({ id, label: id })),
];

export function taskTypeLabel(task: TaskType | string): string {
  return MARKETPLACE_TASK_TYPES.find((t) => t.id === task)?.label ?? task.replace(/_/g, " ");
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...init,
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const detail = data.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : typeof detail === "object" && detail && "message" in detail
          ? String((detail as { message: string }).message)
          : `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data as T;
}

export async function fetchMarketplaceDatasets(taskType?: TaskType, industry?: MarketplaceIndustry) {
  const params = new URLSearchParams();
  if (taskType) params.set("task_type", taskType);
  if (industry) params.set("industry", industry);
  const q = params.toString() ? `?${params}` : "";
  return api<{
    datasets: MarketplaceDataset[];
    task_types: TaskType[];
    industries?: string[];
  }>(`/api/marketplace/datasets${q}`);
}

export async function fetchMarketplaceModels(taskType?: TaskType, industry?: MarketplaceIndustry) {
  const params = new URLSearchParams();
  if (taskType) params.set("task_type", taskType);
  if (industry) params.set("industry", industry);
  const q = params.toString() ? `?${params}` : "";
  return api<{ models: MarketplaceModel[]; task_types: TaskType[]; industries?: string[] }>(
    `/api/marketplace/models${q}`,
  );
}

export async function startProjectFromModel(itemId: string) {
  return api<{
    success: boolean;
    project_id?: string;
    item_id: string;
    item_name: string;
    task_type: TaskType;
    architecture?: string;
    project: Record<string, unknown>;
    spec?: Record<string, unknown>;
  }>(`/api/marketplace/models/${encodeURIComponent(itemId)}/start-project`, {
    method: "POST",
  });
}

export async function startProjectFromDataset(itemId: string) {
  return api<{
    success: boolean;
    project_id: string;
    item_id: string;
    item_name: string;
    task_type: TaskType;
    project: Record<string, unknown>;
    validation?: { valid: boolean; errors?: string[] };
    import_status?: "in_progress" | "completed";
    spec?: Record<string, unknown>;
  }>(`/api/marketplace/datasets/${encodeURIComponent(itemId)}/start-project`, {
    method: "POST",
  });
}

export async function importMarketplaceDataset(projectId: string, itemId: string) {
  return api<{
    success: boolean;
    item_id: string;
    item_name: string;
    task_type: TaskType;
    project: Record<string, unknown>;
    validation?: { valid: boolean; errors?: string[] };
    import_status?: "in_progress" | "completed";
    spec?: Record<string, unknown>;
  }>(`/api/projects/${projectId}/dataset/import-marketplace`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ item_id: itemId }),
  });
}

export async function importMarketplaceModel(projectId: string, itemId: string) {
  return api<{
    success: boolean;
    item_id: string;
    item_name: string;
    task_type: TaskType;
    job_id: string;
    project: Record<string, unknown>;
    deploy_status?: { status: string; error?: string };
  }>(`/api/projects/${projectId}/model/import-marketplace`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ item_id: itemId }),
  });
}

export function formatMetric(metrics: Record<string, number>): string {
  const entries = Object.entries(metrics);
  if (!entries.length) return "—";
  const [key, val] = entries[0];
  const pct = key.includes("accuracy") || key.includes("mAP") || key.includes("f1");
  if (pct && val <= 1) return `${(val * 100).toFixed(1)}%`;
  return `${val}`;
}

export type MarketplacePreviewPayload = {
  previews: string[];
  classes: string[];
  preview_dataset_id?: string | null;
  license?: string;
  format?: string;
  image_count?: number;
  class_count?: number;
  target_name?: string;
  target_unit?: string;
};

export function marketplaceDatasetPreviewUrl(itemId: string, filename: string): string {
  return `${API_BASE}/api/marketplace/datasets/${encodeURIComponent(itemId)}/previews/${encodeURIComponent(filename)}`;
}

export function marketplaceModelPreviewUrl(datasetId: string, filename: string): string {
  return marketplaceDatasetPreviewUrl(datasetId, filename);
}

export async function fetchDatasetPreviews(itemId: string) {
  return api<MarketplacePreviewPayload & MarketplaceDataset>(
    `/api/marketplace/datasets/${encodeURIComponent(itemId)}/previews`,
  );
}

export async function fetchModelPreviews(itemId: string) {
  return api<MarketplacePreviewPayload & MarketplaceModel>(
    `/api/marketplace/models/${encodeURIComponent(itemId)}/previews`,
  );
}
