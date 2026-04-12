import { useStore } from "@/lib/store";
import { ViewState } from "@/lib/store";
import { Activity, Bell, ChevronRight, Cpu, CreditCard, FolderGit2, Home, Library, Search, User } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Sidebar() {
  const { currentView, setCurrentView, workflowStep } = useStore();
  
  const items = [
    { id: 'home' as ViewState, label: 'Ana Sayfa', icon: Home },
    { id: 'projects' as ViewState, label: 'Projeler', icon: FolderGit2 },
    { id: 'models' as ViewState, label: 'Model Kütüphanesi', icon: Library },
    { id: 'inference' as ViewState, label: 'Çıkarım', icon: Cpu },
    { id: 'billing' as ViewState, label: 'Ödeme ve Planlar', icon: CreditCard },
  ];

  return (
    <aside className="flex w-72 flex-col border-r border-slate-200 bg-white shadow-sm fixed inset-y-0 left-0 z-20">
      <div className="flex items-center gap-3 border-b border-slate-200 px-6 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 shadow-sm">
          <Activity className="h-5 w-5 text-white" />
        </div>
        <div>
          <div className="text-lg font-bold tracking-tight text-slate-950">VisionDock</div>
          <div className="text-xs font-medium text-slate-500">Görsel Yapay Zeka Platformu</div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-4 py-6 overflow-y-auto">
        <div className="mb-3 px-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Çalışma Alanı</div>
        {items.map((item) => {
          const Icon = item.icon;
          const active = currentView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setCurrentView(item.id)}
              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold transition-all ${active ? 'bg-blue-50 text-blue-800 ring-1 ring-blue-200' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-950'}`}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-slate-200 bg-slate-50 p-4">
        <div className="mb-3 px-1 text-[11px] font-bold uppercase tracking-widest text-slate-400">Aktif Proje</div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-1 text-sm font-bold text-slate-950">Hata Tespiti</div>
          <div className="mb-5 font-mono text-xs font-semibold text-blue-700">PRJ-8821</div>

          <div className="space-y-4">
            {[1, 2, 3].map((step) => {
              const labels = ['Görev', 'Veri Seti', 'Öneri'];
              const active = workflowStep >= step;
              const completed = workflowStep > step;
              return (
                <div key={step} className="relative flex items-center gap-3">
                  {step > 1 && <div className={`absolute -top-4 left-3 h-4 w-px ${active ? 'bg-blue-500' : 'bg-slate-200'}`} />}
                  <div className={`flex h-6 w-6 items-center justify-center rounded-full border text-[11px] font-bold z-10 ${active ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300 bg-white text-slate-400'}`}>
                    {completed ? "✓" : step}
                  </div>
                  <span className={`text-xs font-semibold ${active ? 'text-slate-900' : 'text-slate-400'}`}>Adım {step} {labels[step - 1]}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </aside>
  );
}

export function Header() {
  const { currentView, notify } = useStore();

  const titles: Record<string, string> = {
    home: 'Ana Sayfa',
    projects: 'Projeler',
    models: 'Model Kütüphanesi',
    inference: 'Çıkarım',
    billing: 'Ödeme ve Planlar',
  };

  return (
    <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-slate-200 bg-white/95 px-8 backdrop-blur">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-bold text-slate-950">{titles[currentView] || "VisionDock"}</h1>
        {currentView === 'projects' && (
          <div className="flex items-center gap-2 text-sm">
            <ChevronRight className="h-4 w-4 text-slate-400" />
            <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-xs font-semibold text-slate-700">PRJ-8821</span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Kaynaklarda ara..."
            className="w-72 rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-4 text-sm text-slate-900 shadow-sm outline-none transition-all placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
        </div>
        <button onClick={() => notify("Bildirimler açıldı")} className="relative rounded-lg border border-slate-200 bg-white p-2 text-slate-500 shadow-sm transition-colors hover:bg-slate-50 hover:text-slate-900">
          <Bell className="h-5 w-5" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-red-500 ring-2 ring-white" />
        </button>
        <button onClick={() => notify("Profil menüsü açıldı")} className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-700 shadow-sm hover:bg-white">
          <User className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}

export function StatusPill({ children, tone = 'blue' }: { children: React.ReactNode; tone?: 'blue' | 'green' | 'amber' | 'red' | 'slate' }) {
  const tones = {
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    slate: 'bg-slate-100 text-slate-700 border-slate-200',
  };

  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
}

export function AuditLog() {
  const { events } = useStore();

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm w-80 fixed right-0 inset-y-0 overflow-y-auto hidden xl:block">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-slate-950">Denetim Günlüğü</h3>
        </div>
        <StatusPill tone="slate">Canlı</StatusPill>
      </div>
      <div className="space-y-3">
        {events.map((event) => (
          <div key={event.id} className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${event.tone === 'green' ? 'bg-emerald-600' : event.tone === 'amber' ? 'bg-amber-500' : event.tone === 'red' ? 'bg-red-600' : event.tone === 'blue' ? 'bg-blue-600' : 'bg-slate-500'}`} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-slate-950 text-sm truncate">{event.title}</div>
                <div className="font-mono text-[10px] text-slate-400 shrink-0">{event.time}</div>
              </div>
              <div className="mt-1 text-xs text-slate-600 leading-relaxed">{event.detail}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen w-full bg-slate-50">
      <Sidebar />
      <div className="flex-1 pl-72 xl:pr-80">
        <Header />
        <main className="p-8">
          {children}
        </main>
      </div>
      <AuditLog />
    </div>
  );
}
