import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createSkill,
  deleteSkill,
  fetchAdminSkills,
  fetchSkillEntrypoints,
  reseedSkills,
  updateSkill,
  type SkillEntrypoint,
  type SkillItem,
  type SkillStage,
} from "@/lib/skills-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SpotlightCard } from "@/components/premium/spotlight-card";
import { FancyEmpty } from "@/components/premium/fancy-empty";
import { AlertCircle, Loader2, Plus, RefreshCw, Save, Trash2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const STAGES: { id: SkillStage | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "preprocessing", label: "Preprocessing" },
  { id: "augmentation", label: "Augmentation" },
  { id: "postprocessing", label: "Postprocessing" },
];

const TASK_OPTIONS = [
  { id: "*", label: "All tasks" },
  { id: "classification", label: "Classification" },
  { id: "multi_label", label: "Multi-label" },
  { id: "regression", label: "Regression" },
  { id: "object_localization", label: "Localization" },
  { id: "object_detection", label: "Detection" },
];

type Draft = {
  id: string;
  name: string;
  description: string;
  stage: SkillStage;
  task_types: string[];
  entrypoint: string;
  default_params_json: string;
  enabled: boolean;
};

function toDraft(skill?: SkillItem | null): Draft {
  if (!skill) {
    return {
      id: "",
      name: "",
      description: "",
      stage: "preprocessing",
      task_types: ["*"],
      entrypoint: "visiondock_preprocess.resize",
      default_params_json: "{}",
      enabled: true,
    };
  }
  return {
    id: skill.id,
    name: skill.name,
    description: skill.description,
    stage: skill.stage,
    task_types: skill.task_types?.length ? skill.task_types : ["*"],
    entrypoint: skill.entrypoint,
    default_params_json: JSON.stringify(skill.default_params ?? {}, null, 2),
    enabled: skill.enabled,
  };
}

function parseJsonField(raw: string, label: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(raw || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error(`${label} must be a JSON object`);
    }
    return parsed as Record<string, unknown>;
  } catch (e) {
    throw new Error(e instanceof Error ? e.message : `Invalid ${label}`);
  }
}

export default function SkillsView() {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [entrypoints, setEntrypoints] = useState<SkillEntrypoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stageFilter, setStageFilter] = useState<SkillStage | "all">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(toDraft());
  const [isNew, setIsNew] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [catalog, eps] = await Promise.all([fetchAdminSkills(), fetchSkillEntrypoints()]);
      setSkills(catalog.skills ?? []);
      setEntrypoints(eps);
      if (!selectedId && catalog.skills?.length) {
        setSelectedId(catalog.skills[0].id);
        setDraft(toDraft(catalog.skills[0]));
        setIsNew(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load skills");
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(
    () => (stageFilter === "all" ? skills : skills.filter((s) => s.stage === stageFilter)),
    [skills, stageFilter],
  );

  const entrypointOptions = useMemo(
    () => entrypoints.filter((e) => e.stage === draft.stage),
    [entrypoints, draft.stage],
  );

  const selectSkill = (skill: SkillItem) => {
    setSelectedId(skill.id);
    setDraft(toDraft(skill));
    setIsNew(false);
  };

  const startNew = () => {
    setIsNew(true);
    setSelectedId(null);
    setDraft(toDraft());
  };

  const toggleTask = (taskId: string) => {
    setDraft((d) => {
      if (taskId === "*") return { ...d, task_types: ["*"] };
      const withoutStar = d.task_types.filter((t) => t !== "*");
      const next = withoutStar.includes(taskId)
        ? withoutStar.filter((t) => t !== taskId)
        : [...withoutStar, taskId];
      return { ...d, task_types: next.length ? next : ["*"] };
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const body = {
        id: draft.id.trim().toLowerCase() || undefined,
        name: draft.name.trim(),
        description: draft.description.trim(),
        stage: draft.stage,
        task_types: draft.task_types,
        entrypoint: draft.entrypoint,
        default_params: parseJsonField(draft.default_params_json, "default_params"),
        enabled: draft.enabled,
      };
      if (!body.name) throw new Error("Name is required");
      if (!body.entrypoint) throw new Error("Entrypoint is required");
      const saved = isNew
        ? await createSkill(body as Parameters<typeof createSkill>[0])
        : await updateSkill(selectedId || draft.id, body as Parameters<typeof updateSkill>[1]);
      toast.success(isNew ? "Skill created" : "Skill updated");
      setIsNew(false);
      setSelectedId(saved.id);
      setDraft(toDraft(saved));
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedId || isNew) return;
    if (!window.confirm(`Delete skill "${selectedId}"?`)) return;
    try {
      await deleteSkill(selectedId);
      toast.success("Skill deleted");
      setSelectedId(null);
      setDraft(toDraft());
      setIsNew(false);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    }
  };

  const handleReseed = async () => {
    if (!window.confirm("Replace the entire skills catalog with the built-in seed?")) return;
    try {
      await reseedSkills();
      toast.success("Catalog reseeded from prompt defaults");
      setSelectedId(null);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Reseed failed");
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-700/60 bg-slate-950 p-6 text-slate-100 shadow-xl">
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-amber-500 text-slate-950 shadow-lg shadow-amber-500/30">
            <Wand2 className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300">
                Admin
              </span>
              <h2 className="text-lg font-semibold tracking-tight">Pipeline Skills</h2>
            </div>
            <p className="mt-1 text-sm leading-relaxed text-slate-300">
              Manage VLM prompt skills and whitelist code entrypoints (
              <code className="text-xs text-amber-200/90">module.function</code>). Generate Config enables
              skills; runtime applies <code className="text-xs text-amber-200/90">default_params</code> via
              the code registry.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              className="border-slate-600 bg-slate-900 text-slate-100 hover:bg-slate-800"
              onClick={() => void load()}
            >
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              Refresh
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="border-slate-600 bg-slate-900 text-slate-100 hover:bg-slate-800"
              onClick={() => void handleReseed()}
            >
              Reseed
            </Button>
            <Button size="sm" className="bg-amber-500 text-slate-950 hover:bg-amber-400" onClick={startNew}>
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              New skill
            </Button>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {STAGES.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setStageFilter(s.id)}
            className={cn(
              "rounded-full px-4 py-1.5 text-sm font-medium transition-all",
              stageFilter === s.id
                ? "bg-primary text-primary-foreground shadow-md shadow-primary/20"
                : "border border-border/60 bg-card/80 text-muted-foreground hover:text-foreground",
            )}
          >
            {s.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-20 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
          Loading skills…
        </div>
      ) : error ? (
        <div className="flex items-center gap-3 rounded-xl border border-destructive/20 bg-destructive/8 px-5 py-4 text-destructive">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <div>
            <p className="font-semibold">Could not load skills</p>
            <p className="mt-0.5 text-sm">{error}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {/not authenticated/i.test(error)
                ? "Session cookie missing — Sign out, sign back in as an admin, then reopen Admin · Skills."
                : "Requires ADMIN_EMAILS (or AUTH_USERNAME) matching your login."}
            </p>
          </div>
        </div>
      ) : (
        /* items-start: columns keep their own height — no stretched empty white under list or form */
        <div className="grid items-start gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
          <div className="space-y-2 lg:sticky lg:top-4 lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto lg:pr-1">
            {filtered.length === 0 ? (
              <FancyEmpty icon={Wand2} title="No skills" description="Create one or reseed the catalog." />
            ) : (
              filtered.map((skill) => (
                <button
                  key={skill.id}
                  type="button"
                  onClick={() => selectSkill(skill)}
                  className={cn(
                    "w-full rounded-xl border px-4 py-3 text-left transition-all",
                    selectedId === skill.id && !isNew
                      ? "border-primary/40 bg-primary/5 shadow-sm"
                      : "border-border/50 bg-card hover:border-primary/25",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-foreground">{skill.name}</span>
                    <span
                      className={cn(
                        "rounded-md px-2 py-0.5 text-[10px] font-bold uppercase",
                        skill.enabled ? "bg-emerald-500/10 text-emerald-700" : "bg-muted text-muted-foreground",
                      )}
                    >
                      {skill.enabled ? "on" : "off"}
                    </span>
                  </div>
                  <div className="mt-1 font-mono text-[11px] text-muted-foreground">{skill.id}</div>
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    {skill.stage} · {skill.entrypoint}
                  </div>
                </button>
              ))
            )}
          </div>

          <SpotlightCard className="self-start p-6">
            <div className="mb-5 flex items-center justify-between gap-3">
              <h3 className="text-base font-semibold">{isNew ? "New skill" : `Edit · ${draft.id || "—"}`}</h3>
              <div className="flex gap-2">
                {!isNew && selectedId ? (
                  <Button variant="outline" size="sm" onClick={() => void handleDelete()}>
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                    Delete
                  </Button>
                ) : null}
                <Button size="sm" disabled={saving} onClick={() => void handleSave()}>
                  {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
                  Save
                </Button>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1.5 text-sm">
                <span className="text-xs font-semibold uppercase text-muted-foreground">ID</span>
                <Input
                  value={draft.id}
                  disabled={!isNew}
                  placeholder="pre.resize.letterbox_cls"
                  onChange={(e) => setDraft((d) => ({ ...d, id: e.target.value }))}
                />
              </label>
              <label className="space-y-1.5 text-sm">
                <span className="text-xs font-semibold uppercase text-muted-foreground">Name</span>
                <Input value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
              </label>
              <label className="space-y-1.5 text-sm">
                <span className="text-xs font-semibold uppercase text-muted-foreground">Stage</span>
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={draft.stage}
                  onChange={(e) => {
                    const stage = e.target.value as SkillStage;
                    const first = entrypoints.find((ep) => ep.stage === stage);
                    setDraft((d) => ({
                      ...d,
                      stage,
                      entrypoint: first?.id || d.entrypoint,
                    }));
                  }}
                >
                  <option value="preprocessing">preprocessing</option>
                  <option value="augmentation">augmentation</option>
                  <option value="postprocessing">postprocessing</option>
                </select>
              </label>
              <label className="space-y-1.5 text-sm">
                <span className="text-xs font-semibold uppercase text-muted-foreground">Entrypoint (code)</span>
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 font-mono text-xs"
                  value={draft.entrypoint}
                  onChange={(e) => setDraft((d) => ({ ...d, entrypoint: e.target.value }))}
                >
                  {entrypointOptions.map((ep) => (
                    <option key={ep.id} value={ep.id}>
                      {ep.id} — {ep.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="mt-4 block space-y-1.5 text-sm">
              <span className="text-xs font-semibold uppercase text-muted-foreground">
                VLM description (prompt context)
              </span>
              <textarea
                className="min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={draft.description}
                onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
              />
            </label>

            <div className="mt-4 space-y-2">
              <span className="text-xs font-semibold uppercase text-muted-foreground">Task types</span>
              <div className="flex flex-wrap gap-2">
                {TASK_OPTIONS.map((t) => {
                  const active = draft.task_types.includes(t.id) || (t.id === "*" && draft.task_types.includes("*"));
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => toggleTask(t.id)}
                      className={cn(
                        "rounded-full px-3 py-1 text-xs font-medium",
                        active ? "bg-primary text-primary-foreground" : "border border-border text-muted-foreground",
                      )}
                    >
                      {t.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <label className="mt-4 block space-y-1.5 text-sm">
              <span className="text-xs font-semibold uppercase text-muted-foreground">default_params (JSON)</span>
              <textarea
                className="min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
                value={draft.default_params_json}
                onChange={(e) => setDraft((d) => ({ ...d, default_params_json: e.target.value }))}
              />
            </label>

            <label className="mt-4 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(e) => setDraft((d) => ({ ...d, enabled: e.target.checked }))}
              />
              Enabled in VLM catalog
            </label>
          </SpotlightCard>
        </div>
      )}
    </div>
  );
}
