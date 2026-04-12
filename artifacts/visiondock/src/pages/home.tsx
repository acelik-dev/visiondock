import { useStore } from "@/lib/store";
import { FolderGit2, Play, Database, Server } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function HomeView() {
  const { setCurrentView, models, events, addEvent } = useStore();

  const recentProjects = [
    { id: 'PRJ-8821', name: 'Hata Tespiti - Montaj Hattı A', status: 'Eğitimde', progress: 68 },
    { id: 'PRJ-8820', name: 'Paketleme Doğrulama', status: 'Tamamlandı', progress: 100 },
    { id: 'PRJ-8819', name: 'İş Güvenliği Ekipman Kontrolü', status: 'Oluşturuldu', progress: 0 },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-blue-50 text-blue-700 rounded-lg"><FolderGit2 className="h-5 w-5" /></div>
            <div className="font-semibold text-slate-700">Aktif Projeler</div>
          </div>
          <div className="text-3xl font-bold text-slate-900">3</div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-emerald-50 text-emerald-700 rounded-lg"><Database className="h-5 w-5" /></div>
            <div className="font-semibold text-slate-700">Eğitilmiş Modeller</div>
          </div>
          <div className="text-3xl font-bold text-slate-900">{models.length}</div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-amber-50 text-amber-700 rounded-lg"><Server className="h-5 w-5" /></div>
            <div className="font-semibold text-slate-700">GPU Kullanımı</div>
          </div>
          <div className="text-3xl font-bold text-slate-900">45s</div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-purple-50 text-purple-700 rounded-lg"><Play className="h-5 w-5" /></div>
            <div className="font-semibold text-slate-700">Aylık Çıkarım</div>
          </div>
          <div className="text-3xl font-bold text-slate-900">12.4K</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-bold text-slate-900">Son Projeler</h2>
            <Button variant="outline" onClick={() => setCurrentView('projects')} className="h-8">Tümünü Gör</Button>
          </div>
          <div className="space-y-4">
            {recentProjects.map(project => (
              <div key={project.id} className="flex items-center justify-between p-4 rounded-xl border border-slate-100 bg-slate-50">
                <div className="flex items-center gap-4">
                  <div className="h-10 w-10 rounded-lg bg-white border border-slate-200 flex items-center justify-center font-mono text-xs font-bold text-slate-600 shadow-sm">
                    {project.id.split('-')[1]}
                  </div>
                  <div>
                    <div className="font-bold text-slate-900">{project.name}</div>
                    <div className="text-xs text-slate-500 font-mono mt-0.5">{project.id}</div>
                  </div>
                </div>
                <div className="flex items-center gap-6">
                  <div className="w-32 hidden md:block">
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="font-medium text-slate-600">{project.status}</span>
                      <span className="font-bold text-slate-900">%{project.progress}</span>
                    </div>
                    <div className="h-1.5 w-full bg-slate-200 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${project.progress === 100 ? 'bg-emerald-500' : 'bg-blue-500'}`} style={{ width: `${project.progress}%` }} />
                    </div>
                  </div>
                  <Button variant="ghost" onClick={() => setCurrentView('projects')}>Aç</Button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm flex flex-col items-center justify-center text-center">
          <div className="h-16 w-16 bg-blue-50 text-blue-600 rounded-full flex items-center justify-center mb-4">
            <FolderGit2 className="h-8 w-8" />
          </div>
          <h3 className="text-lg font-bold text-slate-900 mb-2">Yeni Proje Başlat</h3>
          <p className="text-sm text-slate-500 mb-6 px-4">Kendi verinizle özel bir bilgisayarlı görü modeli eğitin.</p>
          <Button onClick={() => {
            addEvent('Yeni proje başlatıldı', 'Kullanıcı panodan yeni proje oluşturma ekranına geçti.', 'blue');
            setCurrentView('projects');
          }} className="w-full bg-blue-700 hover:bg-blue-800 text-white">Çalışma Alanı Oluştur</Button>
        </div>
      </div>
    </div>
  );
}
