import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { Shell } from "@/components/layout";
import { useStore } from "@/lib/store";
import { fetchAuthMe, logout as authLogout, type AuthUser } from "@/lib/auth";
import {
  clearStoredProjectId,
  setProjectStorageScope,
} from "@/lib/projects-api";
import { bindAppRouter, resetToHomeAfterAuth } from "@/lib/navigation";
import HomeView from "./pages/home";
import ProjectsView from "./pages/projects";
import ModelsView from "./pages/models";
import DatasetsView from "./pages/datasets";
import InferenceView from "./pages/inference";
import BillingView from "./pages/billing";
import LoginView from "./pages/login";
import { Toaster } from "@/components/ui/sonner";
import { RouteSync } from "@/components/route-sync";
import { Loader2 } from "lucide-react";

const LEGACY_PROJECT_KEY = "visiondock_active_project_id";

/** Keep navigateFn available during login (before RouteSync mounts). */
function RouterBinder() {
  const [, navigate] = useLocation();
  useEffect(() => {
    bindAppRouter(navigate);
  }, [navigate]);
  return null;
}

export default function App() {
  const currentView = useStore((state) => state.currentView);
  const [authState, setAuthState] = useState<"loading" | "authenticated" | "unauthenticated">(
    "loading",
  );
  const [username, setUsername] = useState<string | null>(null);

  const enterApp = (user: AuthUser, opts?: { fresh?: boolean }) => {
    const scope = user.user_id ? String(user.user_id) : user.email ?? user.username ?? null;
    setProjectStorageScope(scope);
    try {
      localStorage.removeItem(LEGACY_PROJECT_KEY);
    } catch {
      /* ignore */
    }
    if (opts?.fresh) {
      clearStoredProjectId();
    }
    setUsername(user.name ?? user.email ?? user.username ?? null);
    resetToHomeAfterAuth();
    setAuthState("authenticated");
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const fresh =
      params.get("fresh_login") === "1" || params.get("email_verified") === "1";
    fetchAuthMe()
      .then((data) => {
        if (data.authenticated) {
          enterApp(data, { fresh });
        } else {
          setProjectStorageScope(null);
          setAuthState("unauthenticated");
        }
      })
      .catch(() => {
        setProjectStorageScope(null);
        setAuthState("unauthenticated");
      });
  }, []);

  if (authState === "loading") {
    return (
      <>
        <RouterBinder />
        <div className="vd-shell-bg flex min-h-screen flex-col items-center justify-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Loading VisionDock…</p>
        </div>
      </>
    );
  }

  if (authState === "unauthenticated") {
    return (
      <>
        <RouterBinder />
        <LoginView
          onSuccess={(user) => {
            enterApp(user, { fresh: true });
          }}
        />
        <Toaster />
      </>
    );
  }

  return (
    <>
      <RouterBinder />
      <RouteSync />
      <Shell
        username={username}
        onLogout={() => {
          setProjectStorageScope(null);
          clearStoredProjectId();
          try {
            localStorage.removeItem(LEGACY_PROJECT_KEY);
          } catch {
            /* ignore */
          }
          void authLogout();
          setAuthState("unauthenticated");
        }}
      >
        {currentView === "home" && <HomeView />}
        {currentView === "projects" && <ProjectsView />}
        {currentView === "models" && <ModelsView />}
        {currentView === "datasets" && <DatasetsView />}
        {currentView === "inference" && <InferenceView />}
        {currentView === "billing" && <BillingView />}
      </Shell>
      <Toaster />
    </>
  );
}
