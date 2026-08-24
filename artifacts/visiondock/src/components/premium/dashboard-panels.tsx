import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  BookOpen,
  Cpu,
  Database,
  FolderGit2,
  Layers,
  Library,
  Rocket,
  Sparkles,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ProjectListItem } from "@/lib/projects-api";
import { taskBadgeClass } from "@/lib/task-colors";
import { TASK_LABELS } from "@/lib/project-spec";

const PIPELINE = [
  { id: 1, label: "Discovery", desc: "Chat + sample photos", icon: Sparkles, color: "from-violet-500 to-primary" },
  { id: 2, label: "Dataset", desc: "Upload labeled data", icon: Upload, color: "from-cyan-500 to-blue-500" },
  { id: 3, label: "Training", desc: "GPU on Azure ML", icon: Layers, color: "from-amber-500 to-orange-500" },
  { id: 4, label: "Deploy", desc: "Live inference API", icon: Rocket, color: "from-emerald-500 to-teal-500" },
] as const;

const TIPS = [
  "Upload 10 sample photos before chatting — the VLM uses them to suggest task type and labels.",
  "Model Library starts you with a pretrained architecture; Dataset Library skips Step 2 upload.",
  "Training runs on Azure gpu-cluster — first cold start after idle can take 3–8 minutes.",
  "Deploy from Step 3 to get a REST endpoint and test predictions in the Inference tab.",
  "Use ⌘K (Ctrl+K) to jump between Home, Projects, Models, and Inference instantly.",
];

export function DashboardHero({
  projectCount,
  credits,
  onStart,
}: {
  projectCount: number;
  credits: number | null;
  onStart: () => void;
}) {
  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden rounded-2xl border border-border/50 bg-card p-6 shadow-lg md:p-8"
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <motion.div
          className="absolute -left-20 -top-20 h-64 w-64 rounded-full bg-primary/20 blur-3xl"
          animate={{ x: [0, 30, 0], y: [0, 20, 0] }}
          transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          className="absolute -bottom-16 -right-16 h-72 w-72 rounded-full bg-violet-500/15 blur-3xl"
          animate={{ x: [0, -25, 0], y: [0, -15, 0] }}
          transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      <div className="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">{greeting}</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-foreground md:text-3xl">
            VisionDock Dashboard
          </h1>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
            Build, train, and deploy computer vision models — from a VLM-guided discovery chat to
            Azure ML endpoints.{" "}
            {projectCount > 0
              ? `You have ${projectCount} workspace${projectCount === 1 ? "" : "s"} in progress.`
              : "Start your first workspace in under 5 minutes."}
          </p>
          {credits != null && (
            <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-amber-500/25 bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-900">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
              {credits.toLocaleString()} credits available
            </div>
          )}
        </div>
        <Button onClick={onStart} size="lg" className="shrink-0 shadow-xl shadow-primary/25">
          <Sparkles className="mr-2 h-4 w-4" />
          {projectCount > 0 ? "Open workspace" : "Start discovery"}
        </Button>
      </div>
    </motion.div>
  );
}

export function WorkflowPipeline({ activeStep = 1 }: { activeStep?: number }) {
  return (
    <div className="rounded-2xl border border-border/40 bg-card/90 p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Platform workflow</h3>
        <span className="text-xs text-muted-foreground">4 steps to production</span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {PIPELINE.map((step, i) => {
          const Icon = step.icon;
          const done = step.id < activeStep;
          const active = step.id === activeStep;
          return (
            <motion.div
              key={step.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08 }}
              whileHover={{ y: -4 }}
              className={cn(
                "relative rounded-xl border p-4 transition-shadow",
                active
                  ? "border-primary/40 bg-primary/5 shadow-md shadow-primary/10"
                  : done
                    ? "border-emerald-500/30 bg-emerald-500/5"
                    : "border-border/50 bg-muted/20",
              )}
            >
              {i < PIPELINE.length - 1 && (
                <div className="absolute -right-2 top-1/2 z-10 hidden h-px w-4 bg-border md:block" />
              )}
              <div
                className={cn(
                  "mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br text-white shadow-sm",
                  step.color,
                  !active && !done && "opacity-60 grayscale",
                )}
              >
                <Icon className="h-4 w-4" />
              </div>
              <p className="text-xs font-bold text-foreground">{step.label}</p>
              <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">{step.desc}</p>
              {active && (
                <motion.span
                  layoutId="pipeline-active"
                  className="absolute inset-x-3 bottom-2 h-0.5 rounded-full bg-primary"
                />
              )}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

type StatusSlice = { name: string; value: number; color: string };

export function ProjectStatusChart({ projects }: { projects: ProjectListItem[] }) {
  const slices = useMemo(() => {
    const draft = projects.filter(
      (p) => !p.has_model && !p.training_status?.toLowerCase().includes("train"),
    ).length;
    const training = projects.filter((p) =>
      (p.training_status || "").toLowerCase().match(/train|running|queued/),
    ).length;
    const trained = projects.filter((p) => p.has_model && p.inference_status !== "deployed").length;
    const live = projects.filter((p) => p.inference_status === "deployed").length;
    const data: StatusSlice[] = [
      { name: "Draft", value: draft, color: "hsl(var(--muted-foreground))" },
      { name: "Training", value: training, color: "hsl(var(--primary))" },
      { name: "Trained", value: trained, color: "hsl(38 92% 50%)" },
      { name: "Live API", value: live, color: "hsl(152 69% 40%)" },
    ].filter((d) => d.value > 0);
    return data.length ? data : [{ name: "No projects", value: 1, color: "hsl(var(--border))" }];
  }, [projects]);

  const total = projects.length;

  return (
    <div className="rounded-2xl border border-border/40 bg-card/90 p-5">
      <h3 className="mb-1 text-sm font-semibold text-foreground">Workspace overview</h3>
      <p className="mb-4 text-xs text-muted-foreground">
        {total === 0 ? "Create a project to see status breakdown" : `${total} total workspace${total === 1 ? "" : "s"}`}
      </p>
      <div className="flex items-center gap-4">
        <div className="h-[120px] w-[120px] shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={slices}
                dataKey="value"
                innerRadius={36}
                outerRadius={52}
                paddingAngle={3}
                strokeWidth={0}
              >
                {slices.map((s) => (
                  <Cell key={s.name} fill={s.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  borderRadius: 8,
                  border: "1px solid hsl(var(--border))",
                  background: "hsl(var(--card))",
                  fontSize: 11,
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="min-w-0 flex-1 space-y-2">
          {slices.map((s) => (
            <li key={s.name} className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2 text-muted-foreground">
                <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
                {s.name}
              </span>
              <span className="font-semibold tabular-nums text-foreground">{s.value}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function QuickActions({
  actions,
}: {
  actions: { label: string; desc: string; icon: LucideIcon; onClick: () => void; accent?: string }[];
}) {
  return (
    <div className="grid grid-cols-2 gap-3">
      {actions.map((a, i) => {
        const Icon = a.icon;
        return (
          <motion.button
            key={a.label}
            type="button"
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.06 }}
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.98 }}
            onClick={a.onClick}
            className="group rounded-xl border border-border/50 bg-card/90 p-4 text-left shadow-sm transition-shadow hover:border-primary/30 hover:shadow-md hover:shadow-primary/5"
          >
            <div
              className={cn(
                "mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br text-white",
                a.accent ?? "from-primary to-violet-600",
              )}
            >
              <Icon className="h-4 w-4" />
            </div>
            <p className="text-sm font-semibold text-foreground">{a.label}</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">{a.desc}</p>
            <ArrowRight className="mt-2 h-3.5 w-3.5 text-primary opacity-0 transition-opacity group-hover:opacity-100" />
          </motion.button>
        );
      })}
    </div>
  );
}

export function TipCarousel() {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % TIPS.length), 6000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="rounded-2xl border border-border/40 bg-gradient-to-br from-primary/5 to-violet-500/5 p-5">
      <div className="mb-3 flex items-center gap-2">
        <BookOpen className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold text-foreground">Did you know?</h3>
      </div>
      <motion.p
        key={idx}
        initial={{ opacity: 0, x: 12 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -12 }}
        className="min-h-[3rem] text-sm leading-relaxed text-muted-foreground"
      >
        {TIPS[idx]}
      </motion.p>
      <div className="mt-3 flex gap-1">
        {TIPS.map((_, i) => (
          <button
            key={i}
            type="button"
            aria-label={`Tip ${i + 1}`}
            onClick={() => setIdx(i)}
            className={cn(
              "h-1 rounded-full transition-all",
              i === idx ? "w-6 bg-primary" : "w-2 bg-border",
            )}
          />
        ))}
      </div>
    </div>
  );
}

export function MarketplaceSnapshot({
  modelCount,
  datasetCount,
  onModels,
  onDatasets,
}: {
  modelCount: number | null;
  datasetCount: number | null;
  onModels: () => void;
  onDatasets: () => void;
}) {
  return (
    <div className="rounded-2xl border border-border/40 bg-card/90 p-5">
      <h3 className="mb-4 text-sm font-semibold text-foreground">Marketplace catalog</h3>
      <div className="space-y-3">
        <button
          type="button"
          onClick={onModels}
          className="flex w-full items-center justify-between rounded-xl border border-border/40 bg-muted/20 px-4 py-3 text-left transition-colors hover:bg-primary/5"
        >
          <div className="flex items-center gap-3">
            <Library className="h-4 w-4 text-primary" />
            <div>
              <p className="text-sm font-medium text-foreground">Pretrained models</p>
              <p className="text-[11px] text-muted-foreground">Classification, detection, regression</p>
            </div>
          </div>
          <span className="text-lg font-bold tabular-nums text-primary">{modelCount ?? "—"}</span>
        </button>
        <button
          type="button"
          onClick={onDatasets}
          className="flex w-full items-center justify-between rounded-xl border border-border/40 bg-muted/20 px-4 py-3 text-left transition-colors hover:bg-emerald-500/5"
        >
          <div className="flex items-center gap-3">
            <Database className="h-4 w-4 text-emerald-600" />
            <div>
              <p className="text-sm font-medium text-foreground">Curated datasets</p>
              <p className="text-[11px] text-muted-foreground">Skip upload — train immediately</p>
            </div>
          </div>
          <span className="text-lg font-bold tabular-nums text-emerald-600">{datasetCount ?? "—"}</span>
        </button>
      </div>
    </div>
  );
}

export function RecentProjectCard({
  project,
  title,
  progress,
  statusLabel,
  onOpen,
  delay = 0,
}: {
  project: ProjectListItem;
  title: string;
  progress: number;
  statusLabel: string;
  onOpen: () => void;
  delay?: number;
}) {
  const taskLabel =
    project.task_type && project.task_type in TASK_LABELS
      ? TASK_LABELS[project.task_type as keyof typeof TASK_LABELS]
      : project.task_type;

  return (
    <motion.button
      type="button"
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay }}
      whileHover={{ x: 4 }}
      onClick={onOpen}
      className="flex w-full items-center justify-between rounded-xl border border-border/50 bg-muted/20 p-4 text-left transition-colors hover:border-primary/30 hover:bg-muted/40"
    >
      <div className="flex min-w-0 items-center gap-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-card font-mono text-xs font-bold text-muted-foreground">
          {project.id.split("-")[1]?.slice(0, 4) ?? "—"}
        </div>
        <div className="min-w-0">
          <div className="truncate font-semibold text-foreground">{title}</div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] text-muted-foreground">{project.id}</span>
            {taskLabel && (
              <span
                className={cn(
                  "rounded-md border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide",
                  taskBadgeClass(project.task_type || ""),
                )}
              >
                {taskLabel}
              </span>
            )}
            {project.inference_status === "deployed" && (
              <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase text-emerald-700">
                Live
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="hidden shrink-0 items-center gap-4 sm:flex">
        <div className="w-28">
          <div className="mb-1 flex justify-between text-[10px]">
            <span className="text-muted-foreground">{statusLabel}</span>
            <span className="font-semibold">{progress}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-primary to-violet-500"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ type: "spring", stiffness: 60, damping: 18, delay: delay + 0.2 }}
            />
          </div>
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
      </div>
    </motion.button>
  );
}

export function CreditCostGuide({
  costs,
}: {
  costs?: { vlm_analyze?: number; generate_config?: number; training_submit?: number; inference_predict?: number };
}) {
  const rows = [
    { label: "VLM chat message", value: costs?.vlm_analyze ?? 1 },
    { label: "Generate config", value: costs?.generate_config ?? 2 },
    { label: "Start training", value: costs?.training_submit ?? 50 },
    { label: "Inference test", value: costs?.inference_predict ?? 1 },
  ];

  return (
    <div className="rounded-2xl border border-border/40 bg-card/90 p-5">
      <div className="mb-3 flex items-center gap-2">
        <Cpu className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold text-foreground">Credit costs</h3>
      </div>
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.label} className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">{r.label}</span>
            <span className="font-semibold tabular-nums text-foreground">{r.value} cr</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
