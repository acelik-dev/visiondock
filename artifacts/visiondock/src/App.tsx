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
import SkillsView from "./pages/skills";
import AdminOverviewPage from "./pages/admin";
import AdminUsersPage from "./pages/admin-users";
import AdminLedgerPage from "./pages/admin-ledger";
import AdminCreditsPage from "./pages/admin-credits";
import AdminMembershipPage from "./pages/admin-membership";
import AdminProjectsPage from "./pages/admin-projects";
import AdminMarketplacePage from "./pages/admin-marketplace";
import AdminSystemPage from "./pages/admin-system";
import LoginView from "./pages/login";
import { Toaster } from "@/components/ui/sonner";
import { RouteSync } from "@/components/route-sync";
import { Loader2 } from "lucide-react";

const LEGACY_PROJECT_KEY = "visiondock_active_project_id";

function AdminDenied() {
  return (
    <div className="mx-auto max-w-lg rounded-xl border border-amber-500/30 bg-amber-500/5 p-8 text-center">
      <p className="text-lg font-semibold text-foreground">Admin access required</p>
      <p className="mt-2 text-sm text-muted-foreground">
        This area is only available to accounts listed in{" "}
        <code className="text-xs">ADMIN_EMAILS</code>.
      </p>
    </div>
  );
}

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
  const [isAdmin, setIsAdmin] = useState(false);

  const enterApp = (user: AuthUser, opts?: { fresh?: boolean }) => {
    const scope = user.user_id ? String(user.user_id) : user.email ?? user.username ?? null;
    setProjectStorageScope(scope);
    try {
      localStorage.removeItem(LEGACY_PROJECT_KEY);
    } catch {
      /* ignore */
    }
    const admin = Boolean(user.is_admin);
    if (opts?.fresh) {
      clearStoredProjectId();
      // Only force Home on explicit login/signup — preserve deep links like /skills on refresh.
      resetToHomeAfterAuth({ isAdmin: admin });
    }
    setUsername(user.name ?? user.email ?? user.username ?? null);
    setIsAdmin(admin);
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
        isAdmin={isAdmin}
        onLogout={() => {
          setProjectStorageScope(null);
          clearStoredProjectId();
          try {
            localStorage.removeItem(LEGACY_PROJECT_KEY);
          } catch {
            /* ignore */
          }
          void authLogout();
          setIsAdmin(false);
          setAuthState("unauthenticated");
        }}
      >
        {currentView === "home" && <HomeView />}
        {currentView === "projects" && <ProjectsView />}
        {currentView === "models" && <ModelsView />}
        {currentView === "datasets" && <DatasetsView />}
        {currentView === "inference" && <InferenceView />}
        {currentView === "billing" && <BillingView />}
        {currentView === "admin" &&
          (isAdmin ? (
            <AdminOverviewPage />
          ) : (
            <AdminDenied />
          ))}
        {currentView === "admin-users" && (isAdmin ? <AdminUsersPage /> : <AdminDenied />)}
        {currentView === "admin-ledger" && (isAdmin ? <AdminLedgerPage /> : <AdminDenied />)}
        {currentView === "admin-credits" && (isAdmin ? <AdminCreditsPage /> : <AdminDenied />)}
        {currentView === "admin-membership" && (isAdmin ? <AdminMembershipPage /> : <AdminDenied />)}
        {currentView === "admin-projects" && (isAdmin ? <AdminProjectsPage /> : <AdminDenied />)}
        {currentView === "admin-marketplace" &&
          (isAdmin ? <AdminMarketplacePage /> : <AdminDenied />)}
        {currentView === "admin-system" && (isAdmin ? <AdminSystemPage /> : <AdminDenied />)}
        {currentView === "skills" &&
          (isAdmin ? (
            <SkillsView />
          ) : (
            <AdminDenied />
          ))}
      </Shell>
      <Toaster />
    </>
  );
}
