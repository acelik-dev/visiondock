import React, { useMemo, useState } from 'react';
import {
  Activity,
  AlertCircle,
  Bell,
  BoxSelect,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Clock,
  Cloud,
  CreditCard,
  Cpu,
  Database,
  Download,
  Edit3,
  Eye,
  FileImage,
  FileJson,
  Folder,
  FolderGit2,
  Home,
  Layers,
  Library,
  MoreVertical,
  Play,
  Plus,
  ReceiptText,
  Search,
  Server,
  Settings,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
  User,
  WalletCards,
} from 'lucide-react';

type ViewState = 'home' | 'projects' | 'models' | 'inference' | 'billing';
type WorkflowStep = 1 | 2 | 3;
type EventTone = 'blue' | 'green' | 'amber' | 'red' | 'slate';

type AuditEvent = {
  id: number;
  title: string;
  detail: string;
  time: string;
  tone: EventTone;
};

type ModelItem = {
  id: number;
  name: string;
  type: string;
  params: string;
  accuracy: string;
  res: string;
};

const initialModels: ModelItem[] = [
  { id: 1, name: 'beit_base_patch16_224', type: 'Sınıflandırma', params: '86.5M', accuracy: '%85.2', res: '224px' },
  { id: 2, name: 'convnext_base', type: 'Sınıflandırma', params: '88.6M', accuracy: '%83.8', res: '224px' },
  { id: 3, name: 'vit_large_patch16_384', type: 'Sınıflandırma', params: '304M', accuracy: '%87.1', res: '384px' },
  { id: 4, name: 'resnet50', type: 'Sınıflandırma', params: '25.6M', accuracy: '%79.8', res: '224px' },
  { id: 5, name: 'yolov8_m', type: 'Nesne Tespiti', params: '25.9M', accuracy: '50.2 mAP', res: '640px' },
  { id: 6, name: 'efficientdet_d3', type: 'Nesne Tespiti', params: '12.0M', accuracy: '45.4 mAP', res: '512px' },
];

const recentProjects = [
  { id: 'PRJ-8821', name: 'Hata Tespiti - Montaj Hattı A', status: 'Eğitimde', progress: 68 },
  { id: 'PRJ-8820', name: 'Paketleme Doğrulama', status: 'Tamamlandı', progress: 100 },
  { id: 'PRJ-8819', name: 'İş Güvenliği Ekipman Kontrolü', status: 'Oluşturuldu', progress: 0 },
];

const initialEvents: AuditEvent[] = [
  { id: 1, title: 'Proje oluşturuldu', detail: 'PRJ-8821 için hata tespiti çalışma alanı açıldı.', time: '09:12', tone: 'blue' },
  { id: 2, title: 'Görev tanımı kaydedildi', detail: 'Doğal dil açıklaması modele öneri üretmek için hazırlandı.', time: '09:18', tone: 'slate' },
  { id: 3, title: 'Eğitim onayı bekliyor', detail: 'GPU tahsisi ve maliyet onayı kullanıcıya gösterildi.', time: '09:24', tone: 'amber' },
];

const Button = ({ children, variant = 'primary', className = '', ...props }: any) => {
  const base = 'inline-flex items-center justify-center rounded-lg text-sm font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:pointer-events-none disabled:opacity-50 h-10 px-4 py-2 active:scale-[0.98]';
  const variants = {
    primary: 'bg-blue-700 text-white hover:bg-blue-800 shadow-sm border border-blue-700',
    secondary: 'bg-slate-900 text-white hover:bg-slate-800 border border-slate-900 shadow-sm',
    outline: 'border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 shadow-sm',
    ghost: 'hover:bg-slate-100 text-slate-600',
    danger: 'bg-white text-red-700 hover:bg-red-50 border border-red-200',
    success: 'bg-emerald-700 text-white hover:bg-emerald-800 border border-emerald-700 shadow-sm',
  };

  return (
    <button className={`${base} ${variants[variant as keyof typeof variants]} ${className}`} {...props}>
      {children}
    </button>
  );
};

const Card = ({ children, className = '' }: any) => (
  <div className={`rounded-2xl border border-slate-200 bg-white shadow-sm ${className}`}>{children}</div>
);

const StatusPill = ({ children, tone = 'blue' }: { children: React.ReactNode; tone?: EventTone }) => {
  const tones = {
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    slate: 'bg-slate-100 text-slate-700 border-slate-200',
  };

  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
};

const Sidebar = ({ currentView, navigateTo, workflowStep }: { currentView: ViewState; navigateTo: (v: ViewState) => void; workflowStep: WorkflowStep }) => {
  const items = [
    { id: 'home' as ViewState, label: 'Ana Sayfa', icon: Home },
    { id: 'projects' as ViewState, label: 'Projeler', icon: FolderGit2 },
    { id: 'models' as ViewState, label: 'Model Kütüphanesi', icon: Library },
    { id: 'inference' as ViewState, label: 'Çıkarım', icon: Cpu },
    { id: 'billing' as ViewState, label: 'Ödeme ve Planlar', icon: CreditCard },
  ];

  return (
    <aside className="flex w-72 flex-col border-r border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-3 border-b border-slate-200 px-6 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 shadow-sm">
          <Activity className="h-5 w-5 text-white" />
        </div>
        <div>
          <div className="text-lg font-bold tracking-tight text-slate-950">VisionDock</div>
          <div className="text-xs font-medium text-slate-500">Görsel Yapay Zeka Platformu</div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-4 py-6">
        <div className="mb-3 px-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Çalışma Alanı</div>
        {items.map((item) => {
          const Icon = item.icon;
          const active = currentView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => navigateTo(item.id)}
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
                  <div className={`flex h-6 w-6 items-center justify-center rounded-full border text-[11px] font-bold ${active ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300 bg-white text-slate-400'}`}>
                    {completed ? <CheckCircle2 className="h-3.5 w-3.5" /> : step}
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
};

const Header = ({ currentView, notice, onNotify }: { currentView: ViewState; notice: string; onNotify: () => void }) => {
  const titles = {
    home: 'Ana Sayfa',
    projects: 'Projeler',
    models: 'Model Kütüphanesi',
    inference: 'Çıkarım',
    billing: 'Ödeme ve Planlar',
  };

  return (
    <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-slate-200 bg-white/95 px-8 backdrop-blur">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-bold text-slate-950">{titles[currentView]}</h1>
        {currentView === 'projects' && (
          <div className="flex items-center gap-2 text-sm">
            <ChevronRight className="h-4 w-4 text-slate-400" />
            <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-xs font-semibold text-slate-700">PRJ-8821</span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-4">
        {notice && <div className="hidden max-w-sm truncate rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-800 lg:block">{notice}</div>}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Kaynaklarda ara..."
            className="w-72 rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-4 text-sm text-slate-900 shadow-sm outline-none transition-all placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
        </div>
        <button onClick={onNotify} className="relative rounded-lg border border-slate-200 bg-white p-2 text-slate-500 shadow-sm transition-colors hover:bg-slate-50 hover:text-slate-900">
          <Bell className="h-5 w-5" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-red-500 ring-2 ring-white" />
        </button>
        <button onClick={onNotify} className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-700 shadow-sm hover:bg-white">
          <User className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
};

const AuditLog = ({ events }: { events: AuditEvent[] }) => (
  <Card className="p-6">
    <div className="mb-5 flex items-center justify-between">
      <div>
        <h3 className="text-lg font-bold text-slate-950">Kurumsal Denetim Günlüğü</h3>
        <p className="mt-1 text-sm text-slate-500">Veri yükleme, eğitim onayı, model ve dağıtım olayları.</p>
      </div>
      <StatusPill tone="slate">Canlı UI kaydı</StatusPill>
    </div>
    <div className="space-y-3">
      {events.map((event) => (
        <div key={event.id} className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
          <span className={`mt-1 h-2.5 w-2.5 rounded-full ${event.tone === 'green' ? 'bg-emerald-600' : event.tone === 'amber' ? 'bg-amber-500' : event.tone === 'red' ? 'bg-red-600' : event.tone === 'blue' ? 'bg-blue-600' : 'bg-slate-500'}`} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-3">
              <div className="font-semibold text-slate-950">{event.title}</div>
              <div className="font-mono text-xs text-slate-400">{event.time}</div>
            </div>
            <div className="mt-1 text-sm text-slate-600">{event.detail}</div>
          </div>
        </div>
      ))}
    </div>
  </Card>
);

const ProjectDashboard = ({ datasetUploaded, trainingStarted, modelCount }: { datasetUploaded: boolean; trainingStarted: boolean; modelCount: number }) => (
  <div className="grid grid-cols-4 gap-5">
    <Card className="p-5">
      <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Durum</div>
      <div className="mt-3 flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${trainingStarted ? 'bg-emerald-600' : datasetUploaded ? 'bg-blue-600' : 'bg-amber-500'}`} />
        <span className="text-lg font-bold text-slate-950">{trainingStarted ? 'Eğitimde' : datasetUploaded ? 'Veri Hazır' : 'Yapılandırılıyor'}</span>
      </div>
    </Card>
    <Card className="p-5">
      <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Proje ID</div>
      <div className="mt-3 font-mono text-lg font-bold text-blue-700">PRJ-8821</div>
    </Card>
    <Card className="p-5">
      <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Oluşturulan Model</div>
      <div className="mt-3 text-lg font-bold text-slate-950">{trainingStarted ? 1 : 0}</div>
    </Card>
    <Card className="p-5">
      <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Veri Seti Boyutu</div>
      <div className={`mt-3 text-lg font-bold ${datasetUploaded ? 'text-slate-950' : 'text-slate-400'}`}>{datasetUploaded ? '18.4 GB' : 'Yüklenmedi'}</div>
    </Card>
  </div>
);

const TaskStep = ({ taskText, setTaskText, setWorkflowStep, onAction }: any) => (
  <Card className="overflow-hidden">
    <div className="border-b border-slate-200 bg-slate-50 px-8 py-5">
      <h3 className="flex items-center gap-3 text-xl font-bold text-slate-950">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-700 text-sm font-bold text-white">1</span>
        Görev Tanımı
      </h3>
      <p className="mt-2 max-w-2xl text-sm text-slate-600">Problemi doğal dille tarif edin. VisionDock, görev tipini ve uygun model ailesini buna göre önerir.</p>
    </div>
    <div className="p-8">
      <textarea
        value={taskText}
        onChange={(e) => setTaskText(e.target.value)}
        placeholder="Örn. Montaj hattındaki metal parçalarda çizik, göçük ve eksik vida durumlarını tespit et..."
        className="h-36 w-full resize-none rounded-xl border border-slate-300 bg-white p-5 text-base text-slate-900 shadow-sm outline-none transition-all placeholder:text-slate-400 focus:border-blue-600 focus:ring-4 focus:ring-blue-100"
      />

      <div className="mt-8">
        <h4 className="mb-4 text-xs font-bold uppercase tracking-widest text-slate-500">Örnekler</h4>
        <div className="grid grid-cols-3 gap-5">
          <button onClick={() => { setTaskText('Ürünleri görsel kalite kriterlerine göre Geçti veya Kaldı olarak sınıflandır.'); onAction('Sınıflandırma örneği seçildi', 'Görev açıklaması otomatik dolduruldu.', 'blue'); }} className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md">
            <Layers className="mb-3 h-6 w-6 text-blue-700" />
            <div className="mb-1 text-sm font-bold text-slate-950">Sınıflandırma</div>
            <div className="text-xs text-slate-500">Tüm görüntüyü kategoriye ayırır</div>
          </button>
          <button onClick={() => { setTaskText('Forklift, operatör ve güvenlik konilerinin etrafına sınırlayıcı kutular çizerek tespit et.'); onAction('Nesne tespiti örneği seçildi', 'Görev açıklaması otomatik dolduruldu.', 'blue'); }} className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md">
            <BoxSelect className="mb-3 h-6 w-6 text-cyan-700" />
            <div className="mb-1 text-sm font-bold text-slate-950">Nesne Tespiti</div>
            <div className="text-xs text-slate-500">Belirli nesneleri konumlandırır</div>
          </button>
          <button onClick={() => { setTaskText('Normal üretim referansından sapan görsel anomalileri belirle.'); onAction('Anomali tespiti örneği seçildi', 'Görev açıklaması otomatik dolduruldu.', 'blue'); }} className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md">
            <AlertCircle className="mb-3 h-6 w-6 text-red-600" />
            <div className="mb-1 text-sm font-bold text-slate-950">Anomali Tespiti</div>
            <div className="text-xs text-slate-500">Beklenmeyen kusurları bulur</div>
          </button>
        </div>
      </div>

      <div className="mt-10 flex justify-end border-t border-slate-200 pt-6">
        <Button onClick={() => { setWorkflowStep(2); onAction('Görev tanımı kaydedildi', 'Kullanıcı veri seti yükleme adımına geçti.', 'green'); }} className="w-40 group">Sonraki Adım <ChevronRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" /></Button>
      </div>
    </div>
  </Card>
);

const DatasetStep = ({ setWorkflowStep, datasetUploaded, syntheticGenerated, setDatasetUploaded, setSyntheticGenerated, onAction }: any) => (
  <Card className="overflow-hidden">
    <div className="border-b border-slate-200 bg-slate-50 px-8 py-5">
      <h3 className="flex items-center gap-3 text-xl font-bold text-slate-950">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-700 text-sm font-bold text-white">2</span>
        Veri Seti Yükleme
      </h3>
      <p className="mt-2 text-sm text-slate-600">Görüntü ve etiket dosyalarını yükleyin. <span className="font-bold text-amber-700">Her .zip için 32GB limit</span></p>
    </div>
    <div className="p-8">
      <button onClick={() => { setDatasetUploaded(true); onAction('Veri seti yüklendi', '18.4 GB büyüklüğünde dataset.zip algılandı ve klasör yapısı doğrulandı.', 'green'); }} className={`flex w-full cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-12 text-center transition-all ${datasetUploaded ? 'border-emerald-300 bg-emerald-50' : 'border-slate-300 bg-slate-50 hover:border-blue-400 hover:bg-blue-50/40'}`}>
        <div className="mb-5 flex h-20 w-20 items-center justify-center rounded-full border border-slate-200 bg-white shadow-sm">
          {datasetUploaded ? <CheckCircle2 className="h-10 w-10 text-emerald-700" /> : <UploadCloud className="h-10 w-10 text-blue-700" />}
        </div>
        <h4 className="mb-2 text-lg font-bold text-slate-950">{datasetUploaded ? 'dataset.zip yüklendi' : 'Veri setinizi buraya sürükleyip bırakın'}</h4>
        <p className="mb-6 text-sm text-slate-500">{datasetUploaded ? '18.4 GB, 12.840 görüntü, 12.840 etiket dosyası doğrulandı.' : 'YOLO formatı, COCO JSON veya klasör yapılı görüntü setleri desteklenir.'}</p>
        <Button variant={datasetUploaded ? 'success' : 'outline'}>{datasetUploaded ? 'Yükleme Tamamlandı' : 'Dosya Seç'}</Button>
      </button>

      <div className="mt-8 grid grid-cols-5 gap-6">
        <div className="col-span-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h5 className="mb-4 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-500"><Database className="h-4 w-4 text-blue-700" /> Klasör Algılama</h5>
          <div className="space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-sm text-slate-600">
            <div className="flex items-center gap-2"><Folder className="h-4 w-4 text-slate-500" /> dataset/ <StatusPill tone={datasetUploaded ? 'green' : 'slate'}>{datasetUploaded ? 'algılandı' : 'bekleniyor'}</StatusPill></div>
            <div className="flex items-center gap-2 pl-6"><Folder className="h-4 w-4 text-blue-700" /> images/</div>
            <div className="flex items-center gap-2 pl-12"><FileImage className="h-4 w-4 text-slate-400" /> img_001.jpg</div>
            <div className="flex items-center gap-2 pl-12"><FileImage className="h-4 w-4 text-slate-400" /> img_002.jpg</div>
            <div className="flex items-center gap-2 pl-6"><Folder className="h-4 w-4 text-emerald-700" /> labels/</div>
            <div className="flex items-center gap-2 pl-12"><FileJson className="h-4 w-4 text-slate-400" /> img_001.txt</div>
            <div className="flex items-center gap-2 pl-12"><FileJson className="h-4 w-4 text-slate-400" /> img_002.txt</div>
          </div>
        </div>

        <div className={`col-span-2 flex flex-col justify-center rounded-2xl border p-6 text-center shadow-sm ${syntheticGenerated ? 'border-emerald-200 bg-emerald-50' : 'border-blue-200 bg-blue-50'}`}>
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-xl border border-blue-200 bg-white shadow-sm">
            {syntheticGenerated ? <CheckCircle2 className="h-7 w-7 text-emerald-700" /> : <Sparkles className="h-7 w-7 text-blue-700" />}
          </div>
          <h5 className="mb-2 text-base font-bold text-slate-950">Verin yetersiz mi?</h5>
          <p className="mb-6 text-sm leading-relaxed text-slate-600">{syntheticGenerated ? 'Sentetik 2.400 ek görüntü üretim kuyruğuna alındı.' : 'Üretken yapay zeka ile sentetik veri üret.'}</p>
          <Button variant={syntheticGenerated ? 'success' : 'secondary'} className="w-full" onClick={() => { setSyntheticGenerated(true); onAction('Sentetik veri üretimi başlatıldı', '2.400 ek üretim görüntüsü oluşturma kuyruğuna alındı.', 'green'); }}>{syntheticGenerated ? 'Sentetik Veri Hazırlandı' : 'Sentetik Veri Üret'}</Button>
        </div>
      </div>

      <div className="mt-10 flex items-center justify-between border-t border-slate-200 pt-6">
        <Button variant="ghost" onClick={() => setWorkflowStep(1)}>Geri</Button>
        <Button onClick={() => { setWorkflowStep(3); onAction('Veri seti onaylandı', 'Model öneri ve eğitim onayı adımına geçildi.', 'green'); }} className="w-40 group">Sonraki Adım <ChevronRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" /></Button>
      </div>
    </div>
  </Card>
);

const RecommendStep = ({ setWorkflowStep, trainingStarted, setTrainingStarted, onAction }: any) => (
  <Card className="overflow-hidden">
    <div className="border-b border-slate-200 bg-slate-50 px-8 py-5">
      <h3 className="flex items-center gap-3 text-xl font-bold text-slate-950">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-700 text-sm font-bold text-white">3</span>
        Model Önerisi ve Eğitim
      </h3>
      <p className="mt-2 text-sm text-slate-600">Eğitimi başlatmadan önce model önerisini, GPU tahsisini ve tahmini maliyeti onaylayın.</p>
    </div>
    <div className="p-8">
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6">
        <div className="mb-6 flex items-center justify-between border-b border-slate-200 pb-6">
          <div>
            <div className="text-xs font-bold uppercase tracking-widest text-slate-500">Önerilen Model Mimarisi</div>
            <div className="mt-2 text-2xl font-bold text-slate-950">YOLOv8 Medium</div>
          </div>
          <div className="text-right">
            <div className="text-xs font-bold uppercase tracking-widest text-slate-500">Görev Tipi</div>
            <div className="mt-2 text-lg font-bold text-slate-950">Nesne Tespiti</div>
          </div>
        </div>

        <h4 className="mb-4 text-xs font-bold uppercase tracking-widest text-slate-500">Kaynak Tahsisi</h4>
        <div className="grid grid-cols-3 gap-5">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-500"><Server className="h-4 w-4" /> Hesaplama Birimi</div>
            <div className="font-bold text-slate-950">1x NVIDIA A100</div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-500"><Clock className="h-4 w-4" /> Tahmini Süre</div>
            <div className="font-bold text-slate-950">~4.5 Saat</div>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-500"><CircleDollarSign className="h-4 w-4 text-emerald-700" /> Maliyet Tahmini</div>
            <div className="font-bold text-emerald-700">$12.40</div>
          </div>
        </div>
        {trainingStarted && (
          <div className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
            <div className="mb-2 flex items-center justify-between text-sm font-bold text-emerald-800">
              <span>Eğitim çalışması başlatıldı</span>
              <span>%18</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-emerald-100">
              <div className="h-full w-[18%] rounded-full bg-emerald-700" />
            </div>
          </div>
        )}
      </div>

      <div className="mt-10 flex items-center justify-between border-t border-slate-200 pt-6">
        <Button variant="ghost" onClick={() => setWorkflowStep(2)}>Geri</Button>
        <Button variant="success" className="h-12 px-8" onClick={() => { setTrainingStarted(true); onAction('Eğitim onaylandı', 'A100 GPU tahsisi ve $12.40 maliyet onayı kayda alındı.', 'green'); }}><Play className="mr-2 h-5 w-5 fill-current" /> {trainingStarted ? 'Eğitim Devam Ediyor' : 'Eğitimi Başlat'}</Button>
      </div>
    </div>
  </Card>
);

const ProjectsView = ({ workflowStep, setWorkflowStep, taskText, setTaskText, datasetUploaded, syntheticGenerated, setDatasetUploaded, setSyntheticGenerated, trainingStarted, setTrainingStarted, events, onAction, modelCount }: any) => (
  <div className="space-y-8">
    <div className="flex items-center justify-between">
      <div>
        <h2 className="mb-2 text-2xl font-bold tracking-tight text-slate-950">Hata Tespiti - Montaj Hattı A</h2>
        <p className="text-sm text-slate-600">Görsel görevi yapılandırın ve özel model eğitimini başlatın.</p>
      </div>
      <Button variant="outline" onClick={() => onAction('Proje ayarları açıldı', 'Rol, maliyet limiti ve veri saklama ayarları görüntülendi.', 'slate')}><Settings className="mr-2 h-4 w-4" /> Proje Ayarları</Button>
    </div>

    <ProjectDashboard datasetUploaded={datasetUploaded} trainingStarted={trainingStarted} modelCount={modelCount} />
    {workflowStep === 1 && <TaskStep taskText={taskText} setTaskText={setTaskText} setWorkflowStep={setWorkflowStep} onAction={onAction} />}
    {workflowStep === 2 && <DatasetStep setWorkflowStep={setWorkflowStep} datasetUploaded={datasetUploaded} syntheticGenerated={syntheticGenerated} setDatasetUploaded={setDatasetUploaded} setSyntheticGenerated={setSyntheticGenerated} onAction={onAction} />}
    {workflowStep === 3 && <RecommendStep setWorkflowStep={setWorkflowStep} trainingStarted={trainingStarted} setTrainingStarted={setTrainingStarted} onAction={onAction} />}
    <AuditLog events={events} />
  </div>
);

const ModelsView = ({ models, setModels, selectedModel, setSelectedModel, editingModel, setEditingModel, onAction }: any) => {
  const importModel = () => {
    const newModel = { id: Date.now(), name: 'custom_qualitynet_v1', type: 'Sınıflandırma', params: '42.1M', accuracy: '%82.4', res: '320px' };
    setModels([newModel, ...models]);
    onAction('Özel model içe aktarıldı', 'custom_qualitynet_v1 model kütüphanesine eklendi.', 'green');
  };

  const deleteModel = (model: ModelItem) => {
    setModels(models.filter((item: ModelItem) => item.id !== model.id));
    onAction('Model silindi', `${model.name} kullanıcı arayüzünden kaldırıldı.`, 'red');
  };

  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h2 className="mb-2 text-2xl font-bold tracking-tight text-slate-950">Model Kütüphanesi</h2>
          <p className="text-sm text-slate-600">İnce ayar ve üretim dağıtımı için hazır temel modeller.</p>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" onClick={() => onAction('Model filtreleri uygulandı', 'Sınıflandırma ve nesne tespiti modelleri listelendi.', 'blue')}><Search className="mr-2 h-4 w-4" /> Filtrele</Button>
          <Button onClick={importModel}><Plus className="mr-2 h-4 w-4" /> Özel Model Ekle</Button>
        </div>
      </div>

      {(selectedModel || editingModel) && (
        <Card className="mb-6 border-blue-200 bg-blue-50 p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="mb-1 text-sm font-bold text-blue-900">{editingModel ? 'Düzenleme Paneli' : 'Model Detayı'}</div>
              <div className="font-mono text-lg font-bold text-slate-950">{(editingModel || selectedModel).name}</div>
              <div className="mt-2 text-sm text-slate-600">Parametre: {(editingModel || selectedModel).params} · Başarım: {(editingModel || selectedModel).accuracy} · Giriş: {(editingModel || selectedModel).res}</div>
            </div>
            <div className="flex gap-2">
              {editingModel && <Button variant="success" onClick={() => { setEditingModel(null); onAction('Model düzenlemesi kaydedildi', `${editingModel.name} için metaveri değişiklikleri UI içinde kaydedildi.`, 'green'); }}>Kaydet</Button>}
              <Button variant="outline" onClick={() => { setSelectedModel(null); setEditingModel(null); }}>Kapat</Button>
            </div>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {models.map((model: ModelItem) => (
          <Card key={model.id} className="overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-md">
            <div className="p-6">
              <div className="mb-6 flex items-start justify-between">
                <StatusPill tone={model.type === 'Sınıflandırma' ? 'blue' : 'green'}>{model.type}</StatusPill>
                <button onClick={() => onAction('Model aksiyon menüsü açıldı', `${model.name} için hızlı işlem menüsü görüntülendi.`, 'slate')} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><MoreVertical className="h-5 w-5" /></button>
              </div>
              <h3 className="mb-5 truncate font-mono text-lg font-bold text-slate-950">{model.name}</h3>
              <div className="grid grid-cols-2 gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
                <div>
                  <div className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-500">Parametre</div>
                  <div className="font-bold text-slate-900">{model.params}</div>
                </div>
                <div>
                  <div className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-500">Doğruluk</div>
                  <div className="font-bold text-emerald-700">{model.accuracy}</div>
                </div>
                <div className="col-span-2">
                  <div className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-500">Giriş Çözünürlüğü</div>
                  <div className="font-bold text-slate-900">{model.res}</div>
                </div>
              </div>
            </div>
            <div className="flex gap-2 border-t border-slate-200 bg-slate-50 p-4">
              <Button variant="outline" className="h-9 flex-1 px-3 text-xs" onClick={() => { setSelectedModel(model); setEditingModel(null); onAction('Model detayı açıldı', `${model.name} teknik etiketleriyle görüntülendi.`, 'blue'); }}><Eye className="mr-2 h-3.5 w-3.5" /> Gör</Button>
              <Button variant="outline" className="h-9 flex-1 px-3 text-xs" onClick={() => { setEditingModel(model); setSelectedModel(null); onAction('Model düzenleme açıldı', `${model.name} için UI düzenleme paneli açıldı.`, 'amber'); }}><Edit3 className="mr-2 h-3.5 w-3.5" /> Düzenle</Button>
              <Button variant="danger" className="h-9 px-3 text-xs" onClick={() => deleteModel(model)}><Trash2 className="h-4 w-4" /></Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
};

const InferenceView = ({ apiCreated, dockerReady, binaryReady, setApiCreated, setDockerReady, setBinaryReady, onAction }: any) => (
  <div>
    <div className="mb-8">
      <h2 className="mb-2 text-2xl font-bold tracking-tight text-slate-950">Dağıtım ve Çıkarım</h2>
      <p className="text-sm text-slate-600">Eğitilen modelleri bulut servislerine veya kontrollü fabrika ortamlarına dağıtın.</p>
    </div>

    <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
      <Card className="flex h-full flex-col p-10 transition-all hover:shadow-md">
        <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-xl border border-blue-200 bg-blue-50">
          <Cloud className="h-7 w-7 text-blue-700" />
        </div>
        <h3 className="mb-3 text-2xl font-bold text-slate-950">Bulut API</h3>
        <p className="mb-10 flex-1 leading-relaxed text-slate-600">Modelinizi anında REST API olarak servis edin. Web uygulamaları, dashboardlar ve bulut entegrasyonları için uygundur.</p>
        <div className="mb-10 space-y-4 rounded-2xl border border-slate-200 bg-slate-50 p-6">
          <div className="flex items-center gap-4 text-sm font-semibold text-slate-700"><CheckCircle2 className="h-5 w-5 text-emerald-700" /> %99.9 çalışma süresi SLA</div>
          <div className="flex items-center gap-4 text-sm font-semibold text-slate-700"><CheckCircle2 className="h-5 w-5 text-emerald-700" /> Otomatik ölçeklenen GPU endpointleri</div>
          <div className="flex items-center gap-4 text-sm font-semibold text-slate-700"><CheckCircle2 className="h-5 w-5 text-emerald-700" /> Yönetilen API geçidi</div>
        </div>
        {apiCreated && <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 font-mono text-sm font-semibold text-emerald-800">POST /api/inference/prj-8821/predict</div>}
        <Button className="h-12 w-full text-base" onClick={() => { setApiCreated(true); onAction('Bulut API oluşturuldu', 'PRJ-8821 modeli için tahmin endpointi hazırlandı.', 'green'); }}>{apiCreated ? 'Endpoint Aktif' : 'Endpoint Oluştur'}</Button>
      </Card>

      <Card className="flex h-full flex-col p-10 transition-all hover:shadow-md">
        <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-xl border border-slate-200 bg-slate-100">
          <Download className="h-7 w-7 text-slate-700" />
        </div>
        <h3 className="mb-3 text-2xl font-bold text-slate-950">Docker / Binary</h3>
        <p className="mb-10 flex-1 leading-relaxed text-slate-600">Fabrika sahası, gömülü cihazlar ve kapalı ağ üretim sistemleri için derlenmiş model paketini indirin.</p>
        <div className="mb-10 space-y-4 rounded-2xl border border-slate-200 bg-slate-50 p-6">
          <div className="flex items-center gap-4 text-sm font-semibold text-slate-700"><ShieldCheck className="h-5 w-5 text-slate-600" /> ONNX / TensorRT formatları</div>
          <div className="flex items-center gap-4 text-sm font-semibold text-slate-700"><ShieldCheck className="h-5 w-5 text-slate-600" /> Çevrimdışı çalışabilir</div>
          <div className="flex items-center gap-4 text-sm font-semibold text-slate-700"><ShieldCheck className="h-5 w-5 text-slate-600" /> Düşük gecikmeli edge çıkarım</div>
        </div>
        {(dockerReady || binaryReady) && <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm font-semibold text-blue-800">{dockerReady && 'Docker imajı hazır. '} {binaryReady && 'Binary paket hazır.'}</div>}
        <div className="flex gap-4">
          <Button variant="secondary" className="h-12 flex-1 text-base" onClick={() => { setDockerReady(true); onAction('Docker imajı hazırlandı', 'visiondock/prj-8821:latest paketi indirme için hazırlandı.', 'green'); }}><Download className="mr-2 h-5 w-5" /> Docker İmajı</Button>
          <Button variant="outline" className="h-12 flex-1 text-base" onClick={() => { setBinaryReady(true); onAction('Binary paket hazırlandı', 'TensorRT binary paketi indirme için hazırlandı.', 'green'); }}>Binary Paket</Button>
        </div>
      </Card>
    </div>
  </div>
);

const HomeView = ({ navigateTo, events, onAction }: any) => (
  <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr]">
    <Card className="p-10">
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-900">
        <Activity className="h-8 w-8 text-white" />
      </div>
      <h2 className="mb-4 text-3xl font-bold tracking-tight text-slate-950">Endüstriyel ekipler için kodsuz görsel model eğitimi</h2>
      <p className="mb-8 max-w-2xl text-base leading-relaxed text-slate-600">VisionDock; otomasyon ekiplerinin görev tanımlamasını, veri seti yüklemesini, model seçmesini ve çıkarım dağıtımını makine öğrenimi altyapısı yönetmeden yapmasını sağlar.</p>
      <div className="flex gap-3">
        <Button onClick={() => navigateTo('projects')} className="h-12 px-8 text-base">Aktif Projeyi Aç</Button>
        <Button variant="outline" onClick={() => onAction('Hızlı başlangıç açıldı', 'Platform turu ve önerilen iş akışı kullanıcıya gösterildi.', 'blue')} className="h-12 px-8 text-base">Hızlı Başlangıç</Button>
      </div>
    </Card>

    <Card className="p-6">
      <div className="mb-5 flex items-center justify-between">
        <h3 className="text-lg font-bold text-slate-950">Proje Panosu</h3>
        <StatusPill tone="slate">3 Proje</StatusPill>
      </div>
      <div className="space-y-4">
        {recentProjects.map((project) => (
          <button key={project.id} onClick={() => { navigateTo('projects'); onAction('Proje açıldı', `${project.name} çalışma alanı görüntülendi.`, 'blue'); }} className="w-full rounded-xl border border-slate-200 bg-slate-50 p-4 text-left transition-all hover:border-blue-300 hover:bg-white hover:shadow-sm">
            <div className="mb-2 flex items-center justify-between">
              <div>
                <div className="font-bold text-slate-950">{project.name}</div>
                <div className="font-mono text-xs font-semibold text-slate-500">{project.id}</div>
              </div>
              <StatusPill tone={project.status === 'Tamamlandı' ? 'green' : project.status === 'Eğitimde' ? 'amber' : 'slate'}>{project.status}</StatusPill>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-200">
              <div className="h-full rounded-full bg-blue-700" style={{ width: `${project.progress}%` }} />
            </div>
          </button>
        ))}
      </div>
    </Card>

    <div className="lg:col-span-2">
      <AuditLog events={events} />
    </div>
  </div>
);

const BillingView = ({ selectedPlan, setSelectedPlan, paymentVerified, setPaymentVerified, invoiceCreated, setInvoiceCreated, onAction }: any) => {
  const plans = [
    { name: 'Başlangıç', price: '$249', gpu: '20 GPU saat/ay', storage: '250 GB veri saklama', support: 'E-posta destek', tone: 'slate' as EventTone },
    { name: 'Profesyonel', price: '$890', gpu: '120 GPU saat/ay', storage: '2 TB veri saklama', support: 'Öncelikli destek', tone: 'blue' as EventTone },
    { name: 'Kurumsal', price: 'Özel', gpu: 'Sınırsız ölçek', storage: 'Özel veri bölgesi', support: 'SLA ve hesap yöneticisi', tone: 'green' as EventTone },
  ];

  const selectPlan = (plan: string) => {
    setSelectedPlan(plan);
    onAction('Plan seçildi', `${plan} planı ödeme ekranında seçildi.`, 'blue');
  };

  const verifyPayment = () => {
    setPaymentVerified(true);
    onAction('Ödeme yöntemi doğrulandı', 'Kurumsal Visa kartı UI içinde doğrulanmış olarak işaretlendi.', 'green');
  };

  const createInvoice = () => {
    setInvoiceCreated(true);
    onAction('Fatura oluşturuldu', `${selectedPlan} planı için örnek fatura oluşturuldu ve ödeme geçmişine eklendi.`, 'green');
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="mb-2 text-2xl font-bold tracking-tight text-slate-950">Ödeme ve Planlar</h2>
          <p className="text-sm text-slate-600">Plan seçimi, ödeme yöntemi, kullanım maliyeti ve fatura geçmişi için UI akışı.</p>
        </div>
        <StatusPill tone={paymentVerified ? 'green' : 'amber'}>{paymentVerified ? 'Ödeme yöntemi doğrulandı' : 'Ödeme bekliyor'}</StatusPill>
      </div>

      <div className="grid grid-cols-3 gap-5">
        <Card className="p-5">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Bu ay GPU maliyeti</div>
          <div className="mt-3 text-2xl font-bold text-slate-950">$184.20</div>
          <div className="mt-2 text-sm text-slate-500">Eğitim ve çıkarım tüketimi</div>
        </Card>
        <Card className="p-5">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Kullanılan GPU saati</div>
          <div className="mt-3 text-2xl font-bold text-slate-950">42.8 saat</div>
          <div className="mt-2 text-sm text-slate-500">120 saatlik paketin %36’sı</div>
        </Card>
        <Card className="p-5">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Sonraki fatura</div>
          <div className="mt-3 text-2xl font-bold text-slate-950">15 Mayıs</div>
          <div className="mt-2 text-sm text-slate-500">Tahmini toplam $1,074.20</div>
        </Card>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {plans.map((plan) => (
          <Card key={plan.name} className={`p-6 transition-all hover:-translate-y-0.5 hover:shadow-md ${selectedPlan === plan.name ? 'border-blue-400 ring-4 ring-blue-100' : ''}`}>
            <div className="mb-5 flex items-center justify-between">
              <h3 className="text-lg font-bold text-slate-950">{plan.name}</h3>
              <StatusPill tone={plan.tone}>{selectedPlan === plan.name ? 'Seçili' : 'Plan'}</StatusPill>
            </div>
            <div className="mb-6 text-3xl font-bold text-slate-950">{plan.price}<span className="text-sm font-semibold text-slate-500">{plan.price !== 'Özel' ? '/ay' : ''}</span></div>
            <div className="mb-6 space-y-3 text-sm font-medium text-slate-600">
              <div className="flex items-center gap-3"><CheckCircle2 className="h-4 w-4 text-emerald-700" /> {plan.gpu}</div>
              <div className="flex items-center gap-3"><CheckCircle2 className="h-4 w-4 text-emerald-700" /> {plan.storage}</div>
              <div className="flex items-center gap-3"><CheckCircle2 className="h-4 w-4 text-emerald-700" /> {plan.support}</div>
            </div>
            <Button variant={selectedPlan === plan.name ? 'success' : 'outline'} className="w-full" onClick={() => selectPlan(plan.name)}>
              {selectedPlan === plan.name ? 'Plan Seçildi' : 'Planı Seç'}
            </Button>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-[0.9fr_1.1fr] gap-6">
        <Card className="p-6">
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-900 text-white">
              <WalletCards className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-950">Ödeme Yöntemi</h3>
              <p className="text-sm text-slate-500">UI-only kart doğrulama ekranı</p>
            </div>
          </div>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-500">Kart üzerindeki isim</label>
              <input className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" value="VisionDock Sanayi A.Ş." readOnly />
            </div>
            <div>
              <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-500">Kart numarası</label>
              <input className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" value="4242 4242 4242 4242" readOnly />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <input className="rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" value="12/29" readOnly />
              <input className="rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" value="123" readOnly />
            </div>
            <Button variant={paymentVerified ? 'success' : 'secondary'} className="w-full" onClick={verifyPayment}>
              <CreditCard className="mr-2 h-4 w-4" /> {paymentVerified ? 'Kart Doğrulandı' : 'Ödeme Yöntemini Doğrula'}
            </Button>
          </div>
        </Card>

        <Card className="p-6">
          <div className="mb-5 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold text-slate-950">Fatura Geçmişi</h3>
              <p className="text-sm text-slate-500">Ödeme ve kullanım faturaları</p>
            </div>
            <Button onClick={createInvoice} disabled={!paymentVerified} className="disabled:cursor-not-allowed">
              <ReceiptText className="mr-2 h-4 w-4" /> Fatura Oluştur
            </Button>
          </div>
          <div className="overflow-hidden rounded-xl border border-slate-200">
            <div className="grid grid-cols-4 bg-slate-50 px-4 py-3 text-xs font-bold uppercase tracking-wider text-slate-500">
              <span>Fatura</span>
              <span>Plan</span>
              <span>Tutar</span>
              <span>Durum</span>
            </div>
            {invoiceCreated && (
              <div className="grid grid-cols-4 border-t border-slate-200 px-4 py-3 text-sm">
                <span className="font-mono font-semibold text-slate-900">INV-2026-041</span>
                <span>{selectedPlan}</span>
                <span className="font-bold">$1,074.20</span>
                <StatusPill tone="green">Ödendi</StatusPill>
              </div>
            )}
            <div className="grid grid-cols-4 border-t border-slate-200 px-4 py-3 text-sm">
              <span className="font-mono font-semibold text-slate-900">INV-2026-040</span>
              <span>Profesyonel</span>
              <span className="font-bold">$890.00</span>
              <StatusPill tone="green">Ödendi</StatusPill>
            </div>
            <div className="grid grid-cols-4 border-t border-slate-200 px-4 py-3 text-sm">
              <span className="font-mono font-semibold text-slate-900">INV-2026-039</span>
              <span>Başlangıç</span>
              <span className="font-bold">$249.00</span>
              <StatusPill tone="slate">Arşiv</StatusPill>
            </div>
          </div>
          {!paymentVerified && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm font-semibold text-amber-800">Fatura oluşturmak için önce ödeme yöntemini doğrulayın.</div>}
        </Card>
      </div>
    </div>
  );
};

const MainContent = (props: any) => (
  <main className="flex-1 overflow-y-auto bg-slate-50 p-8">
    <div className="mx-auto max-w-6xl space-y-8 pb-12">
      {props.currentView === 'home' && <HomeView navigateTo={props.navigateTo} events={props.events} onAction={props.onAction} />}
      {props.currentView === 'projects' && <ProjectsView {...props} />}
      {props.currentView === 'models' && <ModelsView {...props} />}
      {props.currentView === 'inference' && <InferenceView {...props} />}
      {props.currentView === 'billing' && <BillingView {...props} />}
    </div>
  </main>
);

export function VisionDockSPA() {
  const [currentView, setCurrentView] = useState<ViewState>('projects');
  const [workflowStep, setWorkflowStep] = useState<WorkflowStep>(1);
  const [taskText, setTaskText] = useState('');
  const [datasetUploaded, setDatasetUploaded] = useState(false);
  const [syntheticGenerated, setSyntheticGenerated] = useState(false);
  const [trainingStarted, setTrainingStarted] = useState(false);
  const [apiCreated, setApiCreated] = useState(false);
  const [dockerReady, setDockerReady] = useState(false);
  const [binaryReady, setBinaryReady] = useState(false);
  const [models, setModels] = useState<ModelItem[]>(initialModels);
  const [selectedModel, setSelectedModel] = useState<ModelItem | null>(null);
  const [editingModel, setEditingModel] = useState<ModelItem | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>(initialEvents);
  const [notice, setNotice] = useState('');

  const time = useMemo(() => new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }), []);

  const onAction = (title: string, detail: string, tone: EventTone = 'blue') => {
    setNotice(title);
    setEvents((current) => [{ id: Date.now(), title, detail, time, tone }, ...current].slice(0, 6));
  };

  const handleNotify = () => onAction('Bildirim merkezi açıldı', 'Son sistem bildirimleri ve kullanıcı hesabı paneli görüntülendi.', 'slate');

  return (
    <div className="flex h-screen w-full overflow-hidden bg-white font-sans text-slate-900 selection:bg-blue-100 selection:text-blue-900">
      <Sidebar currentView={currentView} navigateTo={setCurrentView} workflowStep={workflowStep} />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <Header currentView={currentView} notice={notice} onNotify={handleNotify} />
        <MainContent
          currentView={currentView}
          workflowStep={workflowStep}
          setWorkflowStep={setWorkflowStep}
          taskText={taskText}
          setTaskText={setTaskText}
          datasetUploaded={datasetUploaded}
          syntheticGenerated={syntheticGenerated}
          setDatasetUploaded={setDatasetUploaded}
          setSyntheticGenerated={setSyntheticGenerated}
          trainingStarted={trainingStarted}
          setTrainingStarted={setTrainingStarted}
          apiCreated={apiCreated}
          dockerReady={dockerReady}
          binaryReady={binaryReady}
          setApiCreated={setApiCreated}
          setDockerReady={setDockerReady}
          setBinaryReady={setBinaryReady}
          models={models}
          setModels={setModels}
          modelCount={models.length}
          selectedModel={selectedModel}
          setSelectedModel={setSelectedModel}
          editingModel={editingModel}
          setEditingModel={setEditingModel}
          events={events}
          onAction={onAction}
          navigateTo={setCurrentView}
        />
      </div>
    </div>
  );
}
