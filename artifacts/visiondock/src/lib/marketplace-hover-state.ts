/** One marketplace hover panel at a time — avoids stacked tooltips. */
let activeKey: string | null = null;
const listeners = new Set<() => void>();

export function subscribeMarketplaceHover(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getActiveMarketplaceHoverKey(): string | null {
  return activeKey;
}

export function setActiveMarketplaceHoverKey(key: string | null): void {
  if (activeKey === key) return;
  activeKey = key;
  listeners.forEach((fn) => fn());
}
