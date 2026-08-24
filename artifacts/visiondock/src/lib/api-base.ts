/** Shared API origin for browser fetches (same-origin in production). */
export function resolveApiBase(): string {
  const configured = import.meta.env.VITE_API_URL?.trim();
  // Never call localhost from a production bundle served on Azure / 127.0.0.1.
  if (configured && !(import.meta.env.PROD && /localhost|127\.0\.0\.1/.test(configured))) {
    return configured.replace(/\/$/, "");
  }
  if (import.meta.env.DEV) return "http://localhost:8000";
  if (typeof window !== "undefined") return window.location.origin;
  return "";
}
