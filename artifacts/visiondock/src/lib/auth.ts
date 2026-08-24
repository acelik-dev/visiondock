import { resolveApiBase } from "@/lib/api-base";

const API_BASE = resolveApiBase();

export type AuthUser = {
  authenticated: boolean;
  username?: string;
  email?: string;
  name?: string;
  user_id?: number;
  session_id?: number;
  auth_method?: string;
  email_verified?: boolean;
  email_sent?: boolean;
  email_status?: string;
  message?: string;
  requires_email_verification?: boolean;
};

export type AuthConfig = {
  auth_enabled: boolean;
  google: boolean;
  microsoft: boolean;
  password: boolean;
  signup: boolean;
  email_delivery?: boolean;
  email_verify_required?: boolean;
};

async function authFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = `${API_BASE}${path}`;
  try {
    return await fetch(url, { credentials: "include", ...init });
  } catch (err) {
    const crossOrigin =
      typeof window !== "undefined" &&
      API_BASE &&
      !API_BASE.startsWith(window.location.origin);
    const hint = crossOrigin
      ? `Cannot reach API at ${API_BASE}. Is the backend running?`
      : "Cannot reach the server. Check your connection and try again.";
    throw new Error(err instanceof TypeError ? hint : "Network error");
  }
}

export async function fetchAuthConfig(): Promise<AuthConfig> {
  const res = await authFetch("/api/auth/config");
  if (!res.ok) {
    return { auth_enabled: true, google: false, microsoft: false, password: true, signup: false };
  }
  return res.json();
}

export async function fetchAuthMe(): Promise<AuthUser> {
  const res = await authFetch("/api/auth/me");
  if (!res.ok) return { authenticated: false };
  return res.json();
}

export async function register(
  email: string,
  password: string,
  name?: string,
): Promise<AuthUser> {
  const res = await authFetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name: name || undefined }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "Sign up failed";
    throw new Error(detail);
  }
  return data;
}

export async function login(username: string, password: string): Promise<AuthUser> {
  const res = await authFetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    if (detail && typeof detail === "object" && detail.message) {
      throw new Error(detail.message);
    }
    throw new Error(typeof detail === "string" ? detail : "Sign in failed");
  }
  return data;
}

export async function resendVerification(email: string): Promise<void> {
  const res = await authFetch("/api/auth/resend-verification", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(typeof data.detail === "string" ? data.detail : "Could not resend email");
  }
}

export function googleLoginUrl(): string {
  return `${API_BASE}/api/auth/google/login`;
}

export function microsoftLoginUrl(): string {
  return `${API_BASE}/api/auth/microsoft/login`;
}

export async function logout(): Promise<void> {
  await authFetch("/api/auth/logout", { method: "POST" });
}
