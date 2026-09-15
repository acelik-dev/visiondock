import { resolveApiBase } from "@/lib/api-base";

const API_BASE = resolveApiBase();

async function adminFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail?.message || body.detail || body.message || detail;
      if (typeof detail === "object") detail = JSON.stringify(detail);
    } catch {
      /* ignore */
    }
    throw new Error(String(detail));
  }
  return res.json() as Promise<T>;
}

export type AdminOverview = {
  users: number;
  credits_in_circulation: number;
  active_sessions: number;
  projects: number;
  projects_training: number;
  projects_with_models: number;
  project_status_counts: Record<string, number>;
  marketplace_datasets: number;
  marketplace_models: number;
  skills_total: number;
  skills_enabled: number;
  admin_email_count: number;
};

export type AdminUser = {
  id: number;
  email: string;
  name: string | null;
  credits_balance: number;
  active_plan: string;
  email_verified: boolean;
  is_admin: boolean;
  created_at: string | null;
  last_login: string | null;
};

export type AdminProject = {
  id: string;
  name: string;
  status?: string;
  training_status?: string;
  inference_status?: string;
  owner_email?: string;
  owner_user_id?: number;
  updated_at?: string;
  created_at?: string;
  detected_task?: string;
  has_dataset?: boolean;
  marketplace_dataset?: string;
};

export type AdminMarketplace = {
  updated_at?: string | null;
  version?: string;
  dataset_count: number;
  model_count: number;
  by_industry: Record<string, number>;
  by_task: Record<string, number>;
  datasets: Array<{
    id: string;
    name: string;
    task_type: string;
    image_count: number;
    industries: string[];
    license: string;
    size_label: string;
  }>;
  models: Array<{
    id: string;
    name: string;
    task_type: string;
    architecture: string;
    industries: string[];
  }>;
};

export type AdminSystem = {
  storage_backend: string;
  storage_container: string;
  admin_emails: string[];
  auth_username_fallback: boolean;
  azure_ml_workspace?: string | null;
  azure_resource_group?: string | null;
  public_api_url?: string | null;
  skills_catalog_updated_at?: string | null;
  skills_version?: string;
  blob_reachable: boolean;
  blob_store_type: string;
};

export type AdminLedgerEntry = {
  id: number;
  user_id: number;
  email: string;
  delta: number;
  balance_after: number;
  reason: string;
  ref?: string | null;
  note?: string | null;
  created_at: string | null;
};

export type AdminBillingConfig = {
  version?: string;
  updated_at?: string | null;
  credit_usd: number;
  platform_markup: number;
  action_credits: Record<string, number>;
  plans: Record<
    string,
    {
      id?: string;
      name?: string;
      credits?: number;
      price_usd?: number | null;
      description?: string;
    }
  >;
};

export function fetchAdminOverview() {
  return adminFetch<AdminOverview>("/api/admin/overview");
}

export function fetchAdminUsers(q?: string) {
  const qs = q?.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  return adminFetch<{ users: AdminUser[]; count: number }>(`/api/admin/users${qs}`);
}

export function adjustUserCredits(userId: number, delta: number, note?: string) {
  return adminFetch<{ success: boolean; data: { balance: number; delta: number; email: string } }>(
    `/api/admin/users/${userId}/credits`,
    { method: "POST", body: JSON.stringify({ delta, note: note || null }) },
  );
}

export function setUserPlan(userId: number, planId: string, grantCredits = true) {
  return adminFetch<{ success: boolean; data: { plan: string; balance: number; email: string } }>(
    `/api/admin/users/${userId}/plan`,
    { method: "POST", body: JSON.stringify({ plan_id: planId, grant_credits: grantCredits }) },
  );
}

export function fetchAdminLedger(q?: string) {
  const qs = q?.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  return adminFetch<{ entries: AdminLedgerEntry[]; count: number }>(`/api/admin/ledger${qs}`);
}

export function fetchAdminBilling() {
  return adminFetch<AdminBillingConfig>("/api/admin/billing");
}

export function saveAdminBilling(patch: Partial<AdminBillingConfig>) {
  return adminFetch<AdminBillingConfig>("/api/admin/billing", {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

export function fetchAdminProjects() {
  return adminFetch<{ projects: AdminProject[]; count: number }>("/api/admin/projects");
}

export function fetchAdminMarketplace() {
  return adminFetch<AdminMarketplace>("/api/admin/marketplace");
}

export function fetchAdminSystem() {
  return adminFetch<AdminSystem>("/api/admin/system");
}
