import type { ViewState, WorkflowStep } from "@/lib/store";
import { useStore } from "@/lib/store";

export const VIEW_TO_PATH: Record<ViewState, string> = {
  home: "/home",
  projects: "/projects/step/1",
  models: "/models",
  datasets: "/datasets",
  inference: "/inference",
  billing: "/billing",
  admin: "/admin",
  "admin-users": "/admin/users",
  "admin-ledger": "/admin/ledger",
  "admin-credits": "/admin/credits",
  "admin-membership": "/admin/membership",
  "admin-projects": "/admin/projects",
  "admin-marketplace": "/admin/marketplace",
  "admin-system": "/admin/system",
  skills: "/skills",
};

const PATH_TO_VIEW: Record<string, ViewState> = {
  "/": "home",
  "/home": "home",
  "/models": "models",
  "/datasets": "datasets",
  "/billing": "billing",
  "/admin": "admin",
  "/admin/users": "admin-users",
  "/admin/ledger": "admin-ledger",
  "/admin/credits": "admin-credits",
  "/admin/membership": "admin-membership",
  "/admin/projects": "admin-projects",
  "/admin/marketplace": "admin-marketplace",
  "/admin/system": "admin-system",
  "/skills": "skills",
};

const PROJECT_ID_RE = "prj-[a-f0-9]+";

let navigateFn: ((path: string) => void) | null = null;

export function bindAppRouter(navigate: (path: string) => void) {
  navigateFn = navigate;
}

export function pathToView(path: string): ViewState {
  const clean = path.split("?")[0].split("#")[0].replace(/\/$/, "") || "/";
  if (clean.startsWith("/projects")) return "projects";
  if (clean.startsWith("/inference")) return "inference";
  if (clean.startsWith("/admin")) return PATH_TO_VIEW[clean] ?? "admin";
  return PATH_TO_VIEW[clean] ?? "home";
}

export function projectsPath(step: WorkflowStep, projectId?: string | null): string {
  const stepSeg = `step/${step}`;
  if (projectId) return `/projects/${projectId}/${stepSeg}`;
  return `/projects/${stepSeg}`;
}

export function parseProjectsRoute(path: string): {
  step: WorkflowStep | null;
  projectId: string | null;
} {
  const clean = path.split("?")[0].split("#")[0];
  const withProject = clean.match(new RegExp(`^/projects/(${PROJECT_ID_RE})/step/([123])$`, "i"));
  if (withProject) {
    return {
      projectId: withProject[1],
      step: Number(withProject[2]) as WorkflowStep,
    };
  }
  const stepOnly = clean.match(/^\/projects\/step\/([123])$/);
  if (stepOnly) {
    return { projectId: null, step: Number(stepOnly[1]) as WorkflowStep };
  }
  if (clean === "/projects") {
    return { projectId: null, step: 1 };
  }
  return { projectId: null, step: null };
}

export function inferencePath(projectId?: string | null): string {
  if (projectId) return `/inference/${projectId}`;
  return "/inference";
}

export function parseInferenceProjectId(path: string): string | null {
  const clean = path.split("?")[0].split("#")[0];
  const m = clean.match(new RegExp(`^/inference/(${PROJECT_ID_RE})$`, "i"));
  return m ? m[1] : null;
}

export function viewToPath(view: ViewState): string {
  if (view === "projects") {
    const { workflowStep, activeProjectId } = useStore.getState();
    return projectsPath(workflowStep, activeProjectId);
  }
  if (view === "inference") {
    return inferencePath(useStore.getState().activeProjectId);
  }
  return VIEW_TO_PATH[view] ?? "/home";
}

export function navigateToPath(path: string) {
  if (navigateFn) {
    navigateFn(path);
    return;
  }
  // Login screen mounts before RouteSync — still update the URL so auth
  // success cannot leave a stale /projects/... path that RouteSync would reopen.
  if (typeof window !== "undefined") {
    window.history.replaceState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
}

/** Force Home after login/signup even if the browser still shows an old project URL. */
export function resetToHomeAfterAuth(opts?: { isAdmin?: boolean }) {
  const next = opts?.isAdmin ? "/admin" : "/home";
  if (typeof window !== "undefined") {
    if (window.location.pathname !== next || window.location.search || window.location.hash) {
      window.history.replaceState({}, "", next);
    }
  }
  useStore.setState({
    currentView: opts?.isAdmin ? "admin" : "home",
    activeProjectId: null,
    activeProjectName: null,
    workflowStep: 1,
    datasetUploaded: false,
    marketplaceSpecBootstrap: null,
  });
  if (navigateFn) {
    navigateFn(next);
  }
}

export function navigateToView(view: ViewState) {
  navigateToPath(viewToPath(view));
}

export function navigateToProjectsStep(step: WorkflowStep, projectId?: string | null) {
  const pid = projectId ?? useStore.getState().activeProjectId;
  navigateToPath(projectsPath(step, pid));
}

export function initialWorkflowStepFromUrl(): WorkflowStep {
  if (typeof window === "undefined") return 1;
  return parseProjectsRoute(window.location.pathname).step ?? 1;
}
