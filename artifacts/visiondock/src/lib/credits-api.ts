import { resolveApiBase } from "@/lib/api-base";

const API_BASE = resolveApiBase();

export type CreditCostKey =
  | "vlm_analyze"
  | "generate_config"
  | "pipeline_tune"
  | "training_submit"
  | "inference_deploy"
  | "inference_predict";

export type CreditPlan = {
  id: string;
  name: string;
  credits: number;
  description: string;
  price_usd?: number | null;
};

export type CreditLedgerEntry = {
  id: number;
  delta: number;
  balance_after: number;
  reason: string;
  ref?: string | null;
  note?: string | null;
  azure_cost_usd?: number | null;
  created_at?: string | null;
};

export type CreditUsageEntry = {
  id: number;
  action: string;
  status: string;
  credits_delta: number;
  azure_cost_usd?: number | null;
  project_id?: string | null;
  ref?: string | null;
  note?: string | null;
  session_id?: number | null;
  created_at?: string | null;
};

export type CreditsPricing = {
  credit_usd?: number;
  platform_markup?: number;
  region_note?: string;
  vm_size?: string;
  vm_hourly_usd?: number;
  training_billing?: string;
  cost_notes?: Record<string, string>;
};

export type CreditsAccount = {
  user_id: number;
  email: string;
  balance: number;
  plan: string;
  session_id?: number | null;
  plans: CreditPlan[];
  costs: Record<string, number>;
  pricing?: CreditsPricing;
  ledger: CreditLedgerEntry[];
  usage?: CreditUsageEntry[];
};

async function parseJson(res: Response) {
  return res.json().catch(() => ({}));
}

export async function fetchCredits(): Promise<CreditsAccount> {
  const res = await fetch(`${API_BASE}/api/credits/me`, { credentials: "include" });
  const data = await parseJson(res);
  if (!res.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : data.detail?.message || "Failed to load credits";
    throw new Error(detail);
  }
  return data.data as CreditsAccount;
}

export async function activatePlan(plan: string): Promise<{
  balance: number;
  plan: string;
  granted: number;
}> {
  const res = await fetch(`${API_BASE}/api/credits/activate-plan`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan }),
  });
  const data = await parseJson(res);
  if (!res.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : data.detail?.message || "Failed to activate plan";
    throw new Error(detail);
  }
  return data.data;
}

/** Fallback estimates aligned with api/services/azure_pricing.py (D4s_v3 / gpt-4.1-mini). */
export const DEFAULT_COSTS: Record<CreditCostKey, number> = {
  vlm_analyze: 1,
  generate_config: 1,
  pipeline_tune: 1,
  training_submit: 11,
  inference_deploy: 23,
  inference_predict: 1,
};

export function costLabel(costs: Record<string, number> | undefined, key: CreditCostKey): string {
  const n = costs?.[key] ?? DEFAULT_COSTS[key];
  if (key === "training_submit") {
    return `~${n} credit${n === 1 ? "" : "s"} reserve (billed by Azure job time)`;
  }
  return `${n} credit${n === 1 ? "" : "s"}`;
}
