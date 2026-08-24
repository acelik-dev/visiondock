import { useCallback, useEffect, useState } from "react";
import {
  type CreditsAccount,
  fetchCredits,
  DEFAULT_COSTS,
  type CreditCostKey,
} from "@/lib/credits-api";

type CreditsState = {
  account: CreditsAccount | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  cost: (key: CreditCostKey) => number;
  canAfford: (key: CreditCostKey) => boolean;
};

let sharedAccount: CreditsAccount | null = null;
const listeners = new Set<(account: CreditsAccount | null) => void>();

function publish(account: CreditsAccount | null) {
  sharedAccount = account;
  listeners.forEach((fn) => fn(account));
}

export async function refreshCreditsShared(): Promise<CreditsAccount | null> {
  try {
    const account = await fetchCredits();
    publish(account);
    return account;
  } catch {
    return sharedAccount;
  }
}

export function applyCreditsFromResponse(
  credits?: { balance?: number; debited?: number; reason?: string } | null,
) {
  if (!credits || typeof credits.balance !== "number") {
    void refreshCreditsShared();
    return;
  }
  if (sharedAccount) {
    publish({ ...sharedAccount, balance: credits.balance });
  } else {
    void refreshCreditsShared();
  }
}

/** Toast + header balance update after a successful paid action. */
export function announceCreditSpend(
  credits?: { balance?: number; debited?: number; reason?: string } | null,
  notify?: (message: string) => void,
) {
  applyCreditsFromResponse(credits);
  if (!credits || typeof credits.debited !== "number" || credits.debited <= 0) return;
  const n = credits.debited;
  const bal = typeof credits.balance === "number" ? credits.balance : null;
  const msg =
    bal == null
      ? `−${n} credit${n === 1 ? "" : "s"}`
      : `−${n} credit${n === 1 ? "" : "s"} · balance ${bal.toLocaleString()}`;
  notify?.(msg);
}

export function useCredits(): CreditsState {
  const [account, setAccount] = useState<CreditsAccount | null>(sharedAccount);
  const [loading, setLoading] = useState(!sharedAccount);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const listener = (next: CreditsAccount | null) => setAccount(next);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await fetchCredits();
      publish(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load credits");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const onFocus = () => {
      void refreshCreditsShared();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  const cost = useCallback(
    (key: CreditCostKey) => account?.costs?.[key] ?? DEFAULT_COSTS[key],
    [account],
  );

  const canAfford = useCallback(
    (key: CreditCostKey) => (account?.balance ?? 0) >= cost(key),
    [account, cost],
  );

  return { account, loading, error, refresh, cost, canAfford };
}
