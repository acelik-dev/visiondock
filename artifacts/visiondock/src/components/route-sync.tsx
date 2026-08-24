import { useEffect } from "react";
import { useLocation } from "wouter";
import {
  bindAppRouter,
  parseInferenceProjectId,
  parseProjectsRoute,
  pathToView,
  projectsPath,
} from "@/lib/navigation";
import { useStore } from "@/lib/store";
import { setStoredProjectId } from "@/lib/projects-api";

/** Keep Zustand state in sync with the browser URL (back/forward, direct links). */
export function RouteSync() {
  const [location, navigate] = useLocation();

  useEffect(() => {
    bindAppRouter(navigate);
  }, [navigate]);

  useEffect(() => {
    const view = pathToView(location);
    const state = useStore.getState();

    if (state.currentView !== view) {
      useStore.setState({ currentView: view });
    }

    if (view === "projects") {
      const route = parseProjectsRoute(location);
      if (location === "/projects") {
        navigate(projectsPath(state.workflowStep, state.activeProjectId), { replace: true });
        return;
      }
      if (route.step && state.workflowStep !== route.step) {
        useStore.setState({ workflowStep: route.step });
      }
      if (route.projectId && route.projectId !== state.activeProjectId) {
        setStoredProjectId(route.projectId);
      }
    }

    if (view === "inference") {
      const inferenceId = parseInferenceProjectId(location);
      if (inferenceId && inferenceId !== state.activeProjectId) {
        setStoredProjectId(inferenceId);
      }
    }
  }, [location, navigate]);

  return null;
}
