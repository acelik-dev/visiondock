import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "wouter";
import type { ProjectSpec } from "@/lib/project-spec";
import { parseProjectsRoute } from "@/lib/navigation";
import { resolveApiBase } from "@/lib/api-base";
import { useStore } from "@/lib/store";
import {
  ApiError,
  clearForceNewProject,
  clearStoredProjectId,
  createProject,
  fetchProject,
  getStoredProjectId,
  setStoredProjectId,
  shouldForceNewProject,
  type ProjectMeta,
} from "@/lib/projects-api";

async function ensureProject(urlProjectId?: string | null): Promise<string> {
  if (urlProjectId) {
    try {
      await fetchProject(urlProjectId);
      setStoredProjectId(urlProjectId);
      return urlProjectId;
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 403)) {
        clearStoredProjectId();
      } else {
        throw e;
      }
    }
  }

  let id = getStoredProjectId();
  if (!id) {
    const created = await createProject("Vision workspace");
    id = created.project.id;
    setStoredProjectId(id);
    return id;
  }

  try {
    await fetchProject(id);
    return id;
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 403)) {
      clearStoredProjectId();
      const created = await createProject("Vision workspace");
      const newId = created.project.id;
      setStoredProjectId(newId);
      return newId;
    }
    throw e;
  }
}

export function useActiveProject() {
  const [location] = useLocation();
  const urlProjectId = parseProjectsRoute(location).projectId;
  const setActiveProject = useStore((s) => s.setActiveProject);
  const pendingNewProject = useStore((s) => s.pendingNewProject);
  const setPendingNewProject = useStore((s) => s.setPendingNewProject);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectMeta, setProjectMeta] = useState<ProjectMeta | null>(null);
  const [initialSpec, setInitialSpec] = useState<ProjectSpec | null>(null);
  const [initialChat, setInitialChat] = useState<{ role: string; content: string }[]>([]);
  const [sampleUrls, setSampleUrls] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const creatingNewRef = useRef(false);

  const refresh = useCallback(
    async (id: string) => {
      const bundle = await fetchProject(id);
      setProjectMeta(bundle.project);
      setInitialSpec(bundle.spec);
      setInitialChat(bundle.chat ?? []);
      const base = resolveApiBase();
      setSampleUrls(bundle.samples.map((s) => `${base}${s.url}`));
      setActiveProject(bundle.project.id, bundle.project.name);
      return bundle;
    },
    [setActiveProject],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let id: string;
      const storedId = getStoredProjectId();
      const forceNew = (pendingNewProject || shouldForceNewProject()) && !storedId;
      if (forceNew) {
        if (creatingNewRef.current) return;
        creatingNewRef.current = true;
        clearStoredProjectId();
        const created = await createProject("Vision workspace");
        id = created.project.id;
        setStoredProjectId(id);
        clearForceNewProject();
        setPendingNewProject(false);
      } else {
        id = await ensureProject(urlProjectId);
      }
      setProjectId(id);
      await refresh(id);
      if (storedId) {
        clearForceNewProject();
        setPendingNewProject(false);
      }
    } catch (e) {
      setActiveProject(null, null);
      setError(e instanceof Error ? e.message : "Failed to load project");
    } finally {
      creatingNewRef.current = false;
      setLoading(false);
    }
  }, [refresh, setActiveProject, pendingNewProject, setPendingNewProject, urlProjectId]);

  useEffect(() => {
    if (!urlProjectId || urlProjectId === projectId || loading) return;
    void (async () => {
      setLoading(true);
      try {
        setStoredProjectId(urlProjectId);
        setProjectId(urlProjectId);
        await refresh(urlProjectId);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load project");
      } finally {
        setLoading(false);
      }
    })();
  }, [urlProjectId, projectId, loading, refresh]);

  useEffect(() => {
    void load();
  }, [load]);

  const newProject = useCallback(async () => {
    clearStoredProjectId();
    clearForceNewProject();
    setPendingNewProject(false);
    setLoading(true);
    setError(null);
    try {
      const created = await createProject();
      setStoredProjectId(created.project.id);
      setProjectId(created.project.id);
      await refresh(created.project.id);
    } catch (e) {
      setActiveProject(null, null);
      setError(e instanceof Error ? e.message : "Failed to create project");
    } finally {
      setLoading(false);
    }
  }, [refresh, setActiveProject]);

  return {
    projectId,
    projectMeta,
    setProjectMeta,
    initialSpec,
    initialChat,
    sampleUrls,
    setSampleUrls,
    loading,
    error,
    refresh,
    newProject,
    reload: load,
  };
}
