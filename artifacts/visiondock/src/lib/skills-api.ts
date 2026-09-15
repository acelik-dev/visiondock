import { resolveApiBase } from "@/lib/api-base";

const API_BASE = resolveApiBase();

export type SkillStage = "preprocessing" | "postprocessing" | "augmentation";

export type SkillItem = {
  id: string;
  name: string;
  description: string;
  stage: SkillStage;
  task_types: string[];
  entrypoint: string;
  params_schema: Record<string, unknown>;
  default_params: Record<string, unknown>;
  enabled: boolean;
  version: number;
  updated_at?: string | null;
};

export type SkillEntrypoint = {
  id: string;
  label: string;
  module: string;
  symbol: string;
  stage: string;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  if (method !== "GET" && method !== "HEAD" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && typeof detail.message === "string"
          ? detail.message
          : `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data as T;
}

export async function fetchAdminSkills(): Promise<{ skills: SkillItem[]; updated_at?: string }> {
  return api("/api/admin/skills");
}

export async function fetchSkillEntrypoints(stage?: string): Promise<SkillEntrypoint[]> {
  const q = stage ? `?stage=${encodeURIComponent(stage)}` : "";
  const data = await api<{ entrypoints: SkillEntrypoint[] }>(`/api/skills/entrypoints${q}`);
  return data.entrypoints ?? [];
}

export async function createSkill(body: Partial<SkillItem> & { name: string; stage: SkillStage; entrypoint: string }): Promise<SkillItem> {
  const data = await api<{ skill: SkillItem }>("/api/admin/skills", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return data.skill;
}

export async function updateSkill(id: string, body: Partial<SkillItem> & { name: string; stage: SkillStage; entrypoint: string }): Promise<SkillItem> {
  const data = await api<{ skill: SkillItem }>(`/api/admin/skills/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  return data.skill;
}

export async function deleteSkill(id: string): Promise<void> {
  await api(`/api/admin/skills/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function reseedSkills(): Promise<void> {
  await api("/api/admin/skills/reseed", { method: "POST" });
}
