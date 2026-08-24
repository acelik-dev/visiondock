import { useState } from "react";
import { useStore } from "@/lib/store";
import { ViewState } from "@/lib/store";
import { pathToView, projectsPath } from "@/lib/navigation";
import type { WorkflowStep } from "@/lib/store";
import { CommandPalette, useCommandPalette } from "@/components/premium/command-palette";
import {
  Activity,
  Bell,
  ChevronRight,
  Coins,
  Cpu,
  CreditCard,
  Database,
  FolderGit2,
  Home,
  Library,
  LogOut,
  Search,
  Sparkles,
} from "lucide-react";
import { logout } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Link, useLocation } from "wouter";
import { useCredits } from "@/hooks/use-credits";
import { cn } from "@/lib/utils";

export function Sidebar() {
  const { workflowStep, activeProjectId, activeProjectName, datasetUploaded } = useStore();
  const [location] = useLocation();

  const items = [
    { id: "home" as ViewState, label: "Home", icon: Home },
    { id: "projects" as ViewState, label: "Discovery & Projects", icon: FolderGit2 },
    { id: "models" as ViewState, label: "Model Library", icon: Library },
    { id: "datasets" as ViewState, label: "Dataset Library", icon: Database },
    { id: "inference" as ViewState, label: "Inference", icon: Cpu },
    { id: "billing" as ViewState, label: "Billing & Plans", icon: CreditCard },
  ];

  return (
    <aside className="vd-sidebar fixed inset-y-0 left-0 z-20 shadow-2xl shadow-black/20">
      <div className="flex items-center gap-3 border-b border-sidebar-border px-5 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet-600 shadow-lg shadow-primary/30">
          <Activity className="h-5 w-5 text-white" />
        </div>
        <div>
          <div className="text-base font-semibold tracking-tight text-sidebar-foreground">VisionDock</div>
          <div className="text-[11px] font-medium text-sidebar-foreground/50">Computer Vision Platform</div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-5">
        <div className="vd-label mb-3 px-3 text-sidebar-foreground/40">Workspace</div>
        {items.map((item) => {
          const Icon = item.icon;
          const href =
            item.id === "projects"
              ? projectsPath(workflowStep, activeProjectId)
              : item.id === "inference" && activeProjectId
                ? `/inference/${activeProjectId}`
                : `/${item.id === "home" ? "home" : item.id}`;
          const active = pathToView(location) === item.id;
          return (
            <Link
              key={item.id}
              href={href}
              className={cn("vd-nav-item", active ? "vd-nav-item-active" : "vd-nav-item-idle")}
            >
              <Icon className={cn("h-4 w-4", active && "text-primary")} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-sidebar-border p-4">
        <div className="vd-label mb-3 px-1 text-sidebar-foreground/40">Active project</div>
        <div className="rounded-xl border border-sidebar-border bg-sidebar-accent/80 p-4">
          <div className="mb-1 truncate text-sm font-semibold text-sidebar-foreground">
            {activeProjectName ?? "No project loaded"}
          </div>
          <div className="mb-4 truncate font-mono text-[11px] font-medium text-primary">
            {activeProjectId ?? "—"}
          </div>

          <div className="space-y-3">
            {([1, 2, 3] as WorkflowStep[]).map((step) => {
              const labels = ["Task", "Dataset", "Training"];
              const completed =
                step === 1
                  ? workflowStep > 1
                  : step === 2
                    ? datasetUploaded
                    : workflowStep > step;
              const active =
                step === 2 ? workflowStep >= 2 || datasetUploaded : workflowStep >= step;
              const href = projectsPath(step, activeProjectId);
              const stepActive = workflowStep === step;
              return (
                <Link
                  key={step}
                  href={href}
                  className={cn(
                    "relative flex items-center gap-3 rounded-lg px-1 py-0.5 transition-colors",
                    stepActive ? "text-sidebar-foreground" : "text-sidebar-foreground/50 hover:text-sidebar-foreground/80",
                  )}
                >
                  {step > 1 && (
                    <div
                      className={cn(
                        "absolute -top-3 left-3 h-3 w-px",
                        active ? "bg-primary/60" : "bg-sidebar-border",
                      )}
                    />
                  )}
                  <div
                    className={cn(
                      "z-10 flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-bold",
                      stepActive
                        ? "border-primary bg-primary text-primary-foreground"
                        : completed || (active && !stepActive)
                          ? "border-primary/50 bg-primary/15 text-primary"
                          : "border-sidebar-border bg-sidebar-accent text-sidebar-foreground/40",
                    )}
                  >
                    {completed ? "✓" : step}
                  </div>
                  <span className="text-xs font-medium">
                    Step {step} · {labels[step - 1]}
                  </span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </aside>
  );
}

export function Header({
  username,
  onLogout,
  onOpenCommand,
}: {
  username?: string | null;
  onLogout?: () => void;
  onOpenCommand?: () => void;
}) {
  const { currentView, notify, activeProjectId } = useStore();
  const { account } = useCredits();
  const balance = account?.balance;
  const [, navigate] = useLocation();

  const handleLogout = async () => {
    await logout();
    onLogout?.();
  };

  const titles: Record<string, string> = {
    home: "Home",
    projects: "Projects",
    models: "Model Library",
    datasets: "Dataset Library",
    inference: "Inference",
    billing: "Billing & Plans",
  };

  return (
    <header className="vd-header">
      <div className="flex items-center gap-3">
        <h1 className="text-base font-semibold tracking-tight text-foreground">{titles[currentView] || "VisionDock"}</h1>
        {(currentView === "projects" || currentView === "inference") && activeProjectId && (
          <div className="flex items-center gap-2 text-sm">
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="rounded-md border border-border/60 bg-muted/50 px-2 py-0.5 font-mono text-[11px] font-medium text-muted-foreground">
              {activeProjectId}
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <div className="relative hidden md:block">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            readOnly
            placeholder="Search… ⌘K"
            onClick={onOpenCommand}
            onFocus={onOpenCommand}
            className="h-9 w-64 cursor-pointer border-border/60 bg-background/80 pl-9 text-sm shadow-sm"
          />
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => notify("Notifications opened")}
          className="relative h-9 w-9 text-muted-foreground"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-destructive ring-2 ring-background" />
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => navigate("/billing")}
          className="h-9 gap-2 border-amber-500/25 bg-amber-500/8 text-amber-900 hover:bg-amber-500/12"
        >
          <Coins className="h-4 w-4" />
          <span className="font-semibold">{typeof balance === "number" ? balance.toLocaleString() : "—"}</span>
          <span className="hidden font-medium text-amber-800/70 sm:inline">credits</span>
        </Button>
        {username && (
          <span className="hidden max-w-[140px] truncate text-sm font-medium text-muted-foreground lg:block">
            {username}
          </span>
        )}
        <Button variant="ghost" size="sm" onClick={handleLogout} className="h-9 gap-2 text-muted-foreground">
          <LogOut className="h-4 w-4" />
          <span className="hidden sm:inline">Sign out</span>
        </Button>
      </div>
    </header>
  );
}

export function StatusPill({
  children,
  tone = "primary",
}: {
  children: React.ReactNode;
  tone?: "primary" | "green" | "amber" | "red" | "muted";
}) {
  const tones = {
    primary: "bg-primary/10 text-primary border-primary/20",
    green: "bg-emerald-500/10 text-emerald-700 border-emerald-500/20",
    amber: "bg-amber-500/10 text-amber-800 border-amber-500/20",
    red: "bg-destructive/10 text-destructive border-destructive/20",
    muted: "bg-muted text-muted-foreground border-border",
  };

  return (
    <span className={cn("inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium", tones[tone])}>
      {children}
    </span>
  );
}

export function Shell({
  children,
  username,
  onLogout,
}: {
  children: React.ReactNode;
  username?: string | null;
  onLogout?: () => void;
}) {
  const { open, setOpen } = useCommandPalette();
  const currentView = useStore((state) => state.currentView);
  const fullBleed = currentView === "projects";

  return (
    <div className="vd-shell-bg flex min-h-screen w-full">
      <CommandPalette open={open} onOpenChange={setOpen} />
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col pl-[17.5rem]">
        <Header username={username} onLogout={onLogout} onOpenCommand={() => setOpen(true)} />
        <main className={cn("flex-1", fullBleed ? "p-4 lg:p-5" : "p-6 lg:p-8")}>
          <div
            className={cn(
              "animate-in fade-in duration-300",
              fullBleed ? "w-full max-w-none" : "mx-auto max-w-[1400px]",
            )}
          >
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
