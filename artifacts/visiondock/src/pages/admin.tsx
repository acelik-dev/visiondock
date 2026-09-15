import { useEffect, useState } from "react";
import { Link } from "wouter";
import {
  fetchAdminOverview,
  type AdminOverview,
} from "@/lib/admin-api";
import { AnimatedMetricCard } from "@/components/premium/animated-metric";
import {
  Coins,
  CreditCard,
  Database,
  FolderGit2,
  Loader2,
  Server,
  Shield,
  Sparkles,
  Users,
  Wand2,
} from "lucide-react";
import { cn } from "@/lib/utils";

const SECTIONS = [
  {
    href: "/admin/users",
    title: "Users",
    desc: "Search accounts, grant credits, assign plans.",
    icon: Users,
  },
  {
    href: "/admin/ledger",
    title: "Credit ledger",
    desc: "Full transaction history across all users.",
    icon: Coins,
  },
  {
    href: "/admin/credits",
    title: "Credit settings",
    desc: "Action costs, USD/credit rate, platform markup.",
    icon: CreditCard,
  },
  {
    href: "/admin/membership",
    title: "Membership",
    desc: "Plan names, included credits, and prices.",
    icon: Sparkles,
  },
  {
    href: "/admin/projects",
    title: "All projects",
    desc: "Cross-tenant project inventory and status.",
    icon: FolderGit2,
  },
  {
    href: "/admin/marketplace",
    title: "Marketplace",
    desc: "Catalog datasets and models by industry.",
    icon: Database,
  },
  {
    href: "/skills",
    title: "Pipeline Skills",
    desc: "Enable, edit, and reseed training skills.",
    icon: Wand2,
  },
  {
    href: "/admin/system",
    title: "System",
    desc: "Storage, allowlist, Azure ML settings.",
    icon: Server,
  },
];

export default function AdminOverviewPage() {
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void fetchAdminOverview()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 px-8 py-10 text-white shadow-xl">
        <div className="absolute -right-16 -top-16 h-56 w-56 rounded-full bg-emerald-500/20 blur-3xl" />
        <div className="absolute -bottom-20 left-1/3 h-48 w-48 rounded-full bg-sky-500/10 blur-3xl" />
        <div className="relative flex flex-wrap items-start justify-between gap-6">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
              <Shield className="h-3.5 w-3.5" />
              Admin console
            </div>
            <h2 className="text-3xl font-semibold tracking-tight">Platform control</h2>
            <p className="mt-2 max-w-xl text-sm text-slate-300">
              Manage users, credits, projects, marketplace catalog, pipeline skills, and system
              configuration — separate from the customer workspace.
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Allowlist
            </div>
            <div className="mt-1 font-semibold text-white">
              {data ? `${data.admin_email_count} admin email(s)` : "—"}
            </div>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading overview…
        </div>
      ) : error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-6 text-sm text-destructive">
          {error}
        </div>
      ) : data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <AnimatedMetricCard label="Users" value={data.users} icon={Users} />
          <AnimatedMetricCard
            label="Credits in circulation"
            value={data.credits_in_circulation}
            icon={Coins}
          />
          <AnimatedMetricCard label="Projects" value={data.projects} icon={FolderGit2} />
          <AnimatedMetricCard
            label="Marketplace datasets"
            value={data.marketplace_datasets}
            icon={Database}
          />
        </div>
      ) : null}

      {data && (
        <div className="grid gap-3 sm:grid-cols-3">
          <StatChip label="In training" value={data.projects_training} />
          <StatChip label="With models" value={data.projects_with_models} />
          <StatChip
            label="Skills enabled"
            value={`${data.skills_enabled}/${data.skills_total}`}
          />
        </div>
      )}

      <div>
        <h3 className="mb-3 text-sm font-semibold text-foreground">Manage</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {SECTIONS.map((s) => {
            const Icon = s.icon;
            return (
              <Link
                key={s.href}
                href={s.href}
                className={cn(
                  "group rounded-xl border border-border/70 bg-card p-5 transition",
                  "hover:border-primary/40 hover:bg-primary/5",
                )}
              >
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-slate-900 text-white group-hover:bg-primary">
                  <Icon className="h-5 w-5" />
                </div>
                <div className="text-sm font-semibold text-foreground">{s.title}</div>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{s.desc}</p>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function StatChip({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-border/60 bg-muted/30 px-4 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold text-foreground">{value}</div>
    </div>
  );
}
