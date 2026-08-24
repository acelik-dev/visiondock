import { resolveApiBase } from "@/lib/api-base";
import type { ProjectSpec } from "@/lib/project-spec";

const API_BASE = resolveApiBase();

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Parse API body safely — avoids opaque JSON.parse errors on HTML/502 pages. */
export async function parseJsonResponse(res: Response): Promise<Record<string, unknown>> {
  const text = await res.text();
  if (!text.trim()) {
    return {};
  }
  try {
    const data = JSON.parse(text) as Record<string, unknown>;
    return data && typeof data === "object" ? data : {};
  } catch {
    const snippet = text.replace(/\s+/g, " ").slice(0, 280);
    throw new ApiError(
      `Server returned non-JSON (${res.status}). ${snippet}`,
      res.status,
    );
  }
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
        : typeof detail === "object" && detail?.message
          ? detail.message
          : `Request failed (${res.status})`;
    throw new ApiError(msg, res.status);
  }
  return data as T;
}

import type { InferenceMeta } from "@/lib/inference-api";
import type { SavedTrainingJob } from "@/lib/training-api";

export type DatasetValidation = {
  valid: boolean;
  errors: string[];
  warnings: string[];
  stats: Record<string, unknown>;
};

export type ProjectMeta = {
  id: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
  sample_count: number;
  training?: SavedTrainingJob;
  inference?: InferenceMeta;
  model?: Record<string, unknown>;
  model_template?: {
    source?: string;
    marketplace_item_id?: string;
    marketplace_name?: string;
    architecture?: string;
    input_resolution?: string;
    reference_metrics?: Record<string, number>;
    trained_on?: string | null;
    /** Catalog demo labels — never used as the project's required classes. */
    example_classes?: string[];
  };
  dataset?: {
    mode?: "classification" | "multi_label" | "regression" | "object_detection" | "object_localization" | string;
    source?: string;
    marketplace_item_id?: string;
    marketplace_name?: string;
    import_status?: "in_progress" | "completed";
    uploaded: boolean;
    validated: boolean;
    size_bytes: number;
    file_name: string | null;
    classes?: Record<string, { count: number; storage_dir?: string }>;
    validation?: DatasetValidation | null;
  };
};

export type DatasetStatus = {
  mode: string;
  task_type?: string;
  classes?: Record<string, number>;
  total_images?: number;
  validated: boolean;
  validation?: ProjectMeta["dataset"] extends { validation: infer V } ? V : never;
  summary?: Record<string, unknown>;
  dataset?: ProjectMeta["dataset"];
};

export type ClassificationDatasetStatus = {
  mode: "classification";
  classes: Record<string, number>;
  total_images: number;
  validated: boolean;
  validation: DatasetValidation | null | undefined;
  dataset?: ProjectMeta["dataset"];
};

export type ProjectBundle = {
  project: ProjectMeta;
  spec: ProjectSpec | null;
  chat: { role: string; content: string; timestamp?: string }[];
  samples: { id: string; url: string }[];
};

const PROJECT_KEY = "visiondock_active_project_id";
const FORCE_NEW_KEY = "visiondock_force_new_project";

let projectStorageScope: string | null = null;

export function setProjectStorageScope(scope: string | null) {
  projectStorageScope = scope?.trim() || null;
}

function scopedProjectKey(): string {
  return projectStorageScope ? `${PROJECT_KEY}:${projectStorageScope}` : PROJECT_KEY;
}

/** User chose "Create workspace" — next project load must create a new project. */
export function markForceNewProject() {
  sessionStorage.setItem(FORCE_NEW_KEY, "1");
}

export function shouldForceNewProject(): boolean {
  return sessionStorage.getItem(FORCE_NEW_KEY) === "1";
}

export function clearForceNewProject() {
  sessionStorage.removeItem(FORCE_NEW_KEY);
}

export function beginNewWorkspace() {
  clearStoredProjectId();
  markForceNewProject();
}

const FRESH_LOGIN_KEY = "visiondock_fresh_login";

export function markFreshLogin() {
  sessionStorage.setItem(FRESH_LOGIN_KEY, "1");
}

export function consumeFreshLogin(): boolean {
  const url = new URL(window.location.href);
  if (url.searchParams.get("fresh_login") === "1") {
    url.searchParams.delete("fresh_login");
    const next = `${url.pathname}${url.search}${url.hash}`;
    window.history.replaceState({}, "", next);
    return true;
  }
  if (sessionStorage.getItem(FRESH_LOGIN_KEY) === "1") {
    sessionStorage.removeItem(FRESH_LOGIN_KEY);
    return true;
  }
  return false;
}

export function getStoredProjectId(): string | null {
  return localStorage.getItem(scopedProjectKey());
}

export function setStoredProjectId(id: string) {
  localStorage.setItem(scopedProjectKey(), id);
}

export function clearStoredProjectId() {
  localStorage.removeItem(scopedProjectKey());
}

export type ProjectListItem = {
  id: string;
  name: string;
  display_name?: string;
  subtitle?: string | null;
  task_type?: string | null;
  dataset_name?: string | null;
  status: string;
  updated_at: string;
  training_status?: string;
  inference_status?: string;
  has_model?: boolean;
};

export function projectListTitle(project: Pick<ProjectListItem, "display_name" | "name">): string {
  return project.display_name?.trim() || project.name;
}

export async function listProjects() {
  return api<{ projects: ProjectListItem[] }>("/api/projects");
}

export async function createProject(name?: string) {
  return api<{ project: ProjectMeta }>("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function fetchProject(projectId: string) {
  return api<ProjectBundle>(`/api/projects/${projectId}`);
}

export async function saveChat(projectId: string, messages: ProjectBundle["chat"]) {
  return api<{ ok: boolean }>(`/api/projects/${projectId}/chat`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
}

export async function saveSpec(projectId: string, spec: ProjectSpec) {
  return api<{ spec: ProjectSpec }>(`/api/projects/${projectId}/spec`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ spec }),
  });
}

export async function tunePipelineFromDataset(
  projectId: string,
  force = false,
): Promise<{
  success: boolean;
  cached?: boolean;
  spec: ProjectSpec;
  rationale?: string;
  image_count?: number;
}> {
  const res = await fetch(
    `${API_BASE}/api/projects/${projectId}/pipeline/tune?force=${force ? "true" : "false"}`,
    { method: "POST", credentials: "include" },
  );
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : "Pipeline auto-config failed");
  }
  return data as {
    success: boolean;
    cached?: boolean;
    spec: ProjectSpec;
    rationale?: string;
    image_count?: number;
  };
}

export async function uploadSample(projectId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/samples`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Sample upload failed");
  return data as { id: string; url: string; data_url: string };
}

export async function uploadDataset(projectId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/dataset`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail : "Dataset upload failed");
  }
  return data as {
    project: ProjectMeta;
    validation: DatasetValidation | null | undefined;
  };
}

export async function fetchClassificationDataset(projectId: string) {
  return api<ClassificationDatasetStatus>(`/api/projects/${projectId}/dataset/classification`);
}

export async function fetchDatasetStatus(projectId: string) {
  return api<DatasetStatus>(`/api/projects/${projectId}/dataset/status`);
}

export async function uploadMultiLabelImages(projectId: string, files: File[]) {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/dataset/multi-label/images`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(typeof data.detail === "string" ? data.detail : "Upload failed", res.status);
  return data as { project: ProjectMeta; added: number; image_count: number; validation: ProjectMeta["dataset"] extends { validation: infer V } ? V : never };
}

export async function uploadMultiLabelManifest(projectId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/dataset/multi-label/manifest`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(typeof data.detail === "string" ? data.detail : "Manifest upload failed", res.status);
  return data as { project: ProjectMeta; validation: ProjectMeta["dataset"] extends { validation: infer V } ? V : never };
}

export async function uploadRegressionImages(projectId: string, files: File[]) {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/dataset/regression/images`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(typeof data.detail === "string" ? data.detail : "Upload failed", res.status);
  return data as { project: ProjectMeta; added: number; image_count: number; validation: ProjectMeta["dataset"] extends { validation: infer V } ? V : never };
}

export async function uploadRegressionTargets(projectId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/dataset/regression/targets`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(typeof data.detail === "string" ? data.detail : "Target CSV upload failed", res.status);
  return data as { project: ProjectMeta; validation: ProjectMeta["dataset"] extends { validation: infer V } ? V : never };
}

export async function uploadAnnotatedDataset(projectId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/dataset/annotated`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(typeof data.detail === "string" ? data.detail : "Annotated dataset upload failed", res.status);
  return data as {
    project: ProjectMeta;
    validation: DatasetValidation | null | undefined;
  };
}

export async function uploadClassificationImages(
  projectId: string,
  className: string,
  files: File[],
) {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  const res = await fetch(
    `${API_BASE}/api/projects/${projectId}/dataset/class/${encodeURIComponent(className)}/images`,
    {
      method: "POST",
      credentials: "include",
      body: form,
    },
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail : "Image upload failed");
  }
  return data as {
    project: ProjectMeta;
    added: number;
    class_name: string;
    class_counts: Record<string, number>;
    validation: DatasetValidation | null | undefined;
  };
}

export async function clearClassificationClass(projectId: string, className: string) {
  return api<{ success: boolean } & ClassificationDatasetStatus>(
    `/api/projects/${projectId}/dataset/class/${encodeURIComponent(className)}`,
    { method: "DELETE" },
  );
}

export async function completeSetup(projectId: string) {
  return api<{ project: ProjectMeta; message: string }>(
    `/api/projects/${projectId}/complete-setup`,
    { method: "POST" },
  );
}

export async function patchDiscovery(
  projectId: string,
  patch: { ready_for_config?: boolean; detected_task?: string | null },
) {
  return api<{ project: ProjectMeta }>(`/api/projects/${projectId}/discovery`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}
