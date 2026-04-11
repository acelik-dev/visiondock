import React, { useState } from 'react';
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
  Search,
  Server,
  Settings,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
  User,
} from 'lucide-react';

type ViewState = 'home' | 'projects' | 'models' | 'inference';
type WorkflowStep = 1 | 2 | 3;

const modelLibrary = [
  { id: 1, name: 'beit_base_patch16_224', type: 'Classification', params: '86.5M', accuracy: '85.2%', res: '224px' },
  { id: 2, name: 'convnext_base', type: 'Classification', params: '88.6M', accuracy: '83.8%', res: '224px' },
  { id: 3, name: 'vit_large_patch16_384', type: 'Classification', params: '304M', accuracy: '87.1%', res: '384px' },
  { id: 4, name: 'resnet50', type: 'Classification', params: '25.6M', accuracy: '79.8%', res: '224px' },
  { id: 5, name: 'yolov8_m', type: 'Object Detection', params: '25.9M', accuracy: '50.2 mAP', res: '640px' },
  { id: 6, name: 'efficientdet_d3', type: 'Object Detection', params: '12.0M', accuracy: '45.4 mAP', res: '512px' },
];

const recentProjects = [
  { id: 'PRJ-8821', name: 'Defect Detection - Assembly Line A', status: 'Training', progress: 68 },
  { id: 'PRJ-8820', name: 'Packaging Verification', status: 'Done', progress: 100 },
  { id: 'PRJ-8819', name: 'Safety Gear Compliance', status: 'Created', progress: 0 },
];

const Button = ({ children, variant = 'primary', className = '', ...props }: any) => {
  const base = 'inline-flex items-center justify-center rounded-lg text-sm font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:pointer-events-none disabled:opacity-50 h-10 px-4 py-2';
  const variants = {
    primary: 'bg-blue-700 text-white hover:bg-blue-800 shadow-sm border border-blue-700',
    secondary: 'bg-slate-900 text-white hover:bg-slate-800 border border-slate-900 shadow-sm',
    outline: 'border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 shadow-sm',
    ghost: 'hover:bg-slate-100 text-slate-600',
    danger: 'bg-white text-red-700 hover:bg-red-50 border border-red-200',
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

const StatusPill = ({ children, tone = 'blue' }: { children: React.ReactNode; tone?: 'blue' | 'green' | 'amber' | 'slate' }) => {
  const tones = {
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    slate: 'bg-slate-100 text-slate-700 border-slate-200',
  };

  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
};

const Sidebar = ({ currentView, navigateTo, workflowStep }: { currentView: ViewState; navigateTo: (v: ViewState) => void; workflowStep: WorkflowStep }) => {
  const items = [
    { id: 'home' as ViewState, label: 'Home', icon: Home },
    { id: 'projects' as ViewState, label: 'Projects', icon: FolderGit2 },
    { id: 'models' as ViewState, label: 'Model Library', icon: Library },
    { id: 'inference' as ViewState, label: 'Inference', icon: Cpu },
  ];

  return (
    <aside className="flex w-72 flex-col border-r border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-3 border-b border-slate-200 px-6 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 shadow-sm">
          <Activity className="h-5 w-5 text-white" />
        </div>
        <div>
          <div className="text-lg font-bold tracking-tight text-slate-950">VisionDock</div>
          <div className="text-xs font-medium text-slate-500">Computer Vision Platform</div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-4 py-6">
        <div className="mb-3 px-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Workspace</div>
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
        <div className="mb-3 px-1 text-[11px] font-bold uppercase tracking-widest text-slate-400">Active Project</div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-1 text-sm font-bold text-slate-950">Defect Detection</div>
          <div className="mb-5 font-mono text-xs font-semibold text-blue-700">PRJ-8821</div>

          <div className="space-y-4">
            {[1, 2, 3].map((step) => {
              const labels = ['Task', 'Dataset', 'Recommend'];
              const active = workflowStep >= step;
              const completed = workflowStep > step;
              return (
                <div key={step} className="relative flex items-center gap-3">
                  {step > 1 && <div className={`absolute -top-4 left-3 h-4 w-px ${active ? 'bg-blue-500' : 'bg-slate-200'}`} />}
                  <div className={`flex h-6 w-6 items-center justify-center rounded-full border text-[11px] font-bold ${active ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300 bg-white text-slate-400'}`}>
                    {completed ? <CheckCircle2 className="h-3.5 w-3.5" /> : step}
                  </div>
                  <span className={`text-xs font-semibold ${active ? 'text-slate-900' : 'text-slate-400'}`}>Step {step} {labels[step - 1]}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </aside>
  );
};

const Header = ({ currentView }: { currentView: ViewState }) => {
  const titles = {
    home: 'Home',
    projects: 'Projects',
    models: 'Model Library',
    inference: 'Inference',
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
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search resources..."
            className="w-72 rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-4 text-sm text-slate-900 shadow-sm outline-none transition-all placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
        </div>
        <button className="relative rounded-lg border border-slate-200 bg-white p-2 text-slate-500 shadow-sm transition-colors hover:bg-slate-50 hover:text-slate-900">
          <Bell className="h-5 w-5" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-red-500 ring-2 ring-white" />
        </button>
        <button className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-700 shadow-sm hover:bg-white">
          <User className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
};

const ProjectDashboard = () => (
  <div className="grid grid-cols-4 gap-5">
    <Card className="p-5">
      <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Status</div>
      <div className="mt-3 flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
        <span className="text-lg font-bold text-slate-950">Configuring</span>
      </div>
    </Card>
    <Card className="p-5">
      <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Project ID</div>
      <div className="mt-3 font-mono text-lg font-bold text-blue-700">PRJ-8821</div>
    </Card>
    <Card className="p-5">
      <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Created Models</div>
      <div className="mt-3 text-lg font-bold text-slate-950">0</div>
    </Card>
    <Card className="p-5">
      <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Dataset Size</div>
      <div className="mt-3 text-lg font-bold text-slate-400">Not uploaded</div>
    </Card>
  </div>
);

const TaskStep = ({ taskText, setTaskText, setWorkflowStep }: any) => (
  <Card className="overflow-hidden">
    <div className="border-b border-slate-200 bg-slate-50 px-8 py-5">
      <h3 className="flex items-center gap-3 text-xl font-bold text-slate-950">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-700 text-sm font-bold text-white">1</span>
        Task Definition
      </h3>
      <p className="mt-2 max-w-2xl text-sm text-slate-600">Problemi doğal dille tarif edin. VisionDock, task tipini ve uygun model ailesini buna göre önerir.</p>
    </div>
    <div className="p-8">
      <textarea
        value={taskText}
        onChange={(e) => setTaskText(e.target.value)}
        placeholder="Örn. Montaj hattındaki metal parçalarda çizik, göçük ve eksik vida durumlarını tespit et..."
        className="h-36 w-full resize-none rounded-xl border border-slate-300 bg-white p-5 text-base text-slate-900 shadow-sm outline-none transition-all placeholder:text-slate-400 focus:border-blue-600 focus:ring-4 focus:ring-blue-100"
      />

      <div className="mt-8">
        <h4 className="mb-4 text-xs font-bold uppercase tracking-widest text-slate-500">Examples</h4>
        <div className="grid grid-cols-3 gap-5">
          <button onClick={() => setTaskText("Classify products as 'Pass' or 'Fail' based on visual quality criteria.")} className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md">
            <Layers className="mb-3 h-6 w-6 text-blue-700" />
            <div className="mb-1 text-sm font-bold text-slate-950">Classification</div>
            <div className="text-xs text-slate-500">Categorize entire images</div>
          </button>
          <button onClick={() => setTaskText('Detect and draw bounding boxes around forklifts, operators, and safety cones.')} className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md">
            <BoxSelect className="mb-3 h-6 w-6 text-cyan-700" />
            <div className="mb-1 text-sm font-bold text-slate-950">Object Detection</div>
            <div className="text-xs text-slate-500">Locate specific items</div>
          </button>
          <button onClick={() => setTaskText('Identify visual anomalies that deviate from the normal production baseline.')} className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md">
            <AlertCircle className="mb-3 h-6 w-6 text-red-600" />
            <div className="mb-1 text-sm font-bold text-slate-950">Anomaly Detection</div>
            <div className="text-xs text-slate-500">Find unexpected defects</div>
          </button>
        </div>
      </div>

      <div className="mt-10 flex justify-end border-t border-slate-200 pt-6">
        <Button onClick={() => setWorkflowStep(2)} className="w-40 group">Next Step <ChevronRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" /></Button>
      </div>
    </div>
  </Card>
);

const DatasetStep = ({ setWorkflowStep }: any) => (
  <Card className="overflow-hidden">
    <div className="border-b border-slate-200 bg-slate-50 px-8 py-5">
      <h3 className="flex items-center gap-3 text-xl font-bold text-slate-950">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-700 text-sm font-bold text-white">2</span>
        Dataset Upload
      </h3>
      <p className="mt-2 text-sm text-slate-600">Upload images and labels. <span className="font-bold text-amber-700">Limit 32GB per .zip</span></p>
    </div>
    <div className="p-8">
      <div className="flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50 p-12 text-center transition-all hover:border-blue-400 hover:bg-blue-50/40">
        <div className="mb-5 flex h-20 w-20 items-center justify-center rounded-full border border-slate-200 bg-white shadow-sm">
          <UploadCloud className="h-10 w-10 text-blue-700" />
        </div>
        <h4 className="mb-2 text-lg font-bold text-slate-950">Drag and drop your dataset here</h4>
        <p className="mb-6 text-sm text-slate-500">Supports YOLO format, COCO JSON, or structured image folders.</p>
        <Button variant="outline">Browse Files</Button>
      </div>

      <div className="mt-8 grid grid-cols-5 gap-6">
        <div className="col-span-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h5 className="mb-4 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-500"><Database className="h-4 w-4 text-blue-700" /> Folder Detection</h5>
          <div className="space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-sm text-slate-600">
            <div className="flex items-center gap-2"><Folder className="h-4 w-4 text-slate-500" /> dataset/</div>
            <div className="flex items-center gap-2 pl-6"><Folder className="h-4 w-4 text-blue-700" /> images/</div>
            <div className="flex items-center gap-2 pl-12"><FileImage className="h-4 w-4 text-slate-400" /> img_001.jpg</div>
            <div className="flex items-center gap-2 pl-12"><FileImage className="h-4 w-4 text-slate-400" /> img_002.jpg</div>
            <div className="flex items-center gap-2 pl-6"><Folder className="h-4 w-4 text-emerald-700" /> labels/</div>
            <div className="flex items-center gap-2 pl-12"><FileJson className="h-4 w-4 text-slate-400" /> img_001.txt</div>
            <div className="flex items-center gap-2 pl-12"><FileJson className="h-4 w-4 text-slate-400" /> img_002.txt</div>
          </div>
        </div>

        <div className="col-span-2 flex flex-col justify-center rounded-2xl border border-blue-200 bg-blue-50 p-6 text-center shadow-sm">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-xl border border-blue-200 bg-white shadow-sm">
            <Sparkles className="h-7 w-7 text-blue-700" />
          </div>
          <h5 className="mb-2 text-base font-bold text-slate-950">Verin yetersiz mi?</h5>
          <p className="mb-6 text-sm leading-relaxed text-slate-600">Üretken yapay zeka ile sentetik veri üret.</p>
          <Button variant="secondary" className="w-full">Generate Synthetic Data</Button>
        </div>
      </div>

      <div className="mt-10 flex items-center justify-between border-t border-slate-200 pt-6">
        <Button variant="ghost" onClick={() => setWorkflowStep(1)}>Back</Button>
        <Button onClick={() => setWorkflowStep(3)} className="w-40 group">Next Step <ChevronRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" /></Button>
      </div>
    </div>
  </Card>
);

const RecommendStep = ({ setWorkflowStep }: any) => (
  <Card className="overflow-hidden">
    <div className="border-b border-slate-200 bg-slate-50 px-8 py-5">
      <h3 className="flex items-center gap-3 text-xl font-bold text-slate-950">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-700 text-sm font-bold text-white">3</span>
        Recommend & Train
      </h3>
      <p className="mt-2 text-sm text-slate-600">Review model recommendation, GPU allocation, and estimated cost before training.</p>
    </div>
    <div className="p-8">
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6">
        <div className="mb-6 flex items-center justify-between border-b border-slate-200 pb-6">
          <div>
            <div className="text-xs font-bold uppercase tracking-widest text-slate-500">Recommended Model Architecture</div>
            <div className="mt-2 text-2xl font-bold text-slate-950">YOLOv8 Medium</div>
          </div>
          <div className="text-right">
            <div className="text-xs font-bold uppercase tracking-widest text-slate-500">Task Type</div>
            <div className="mt-2 text-lg font-bold text-slate-950">Object Detection</div>
          </div>
        </div>

        <h4 className="mb-4 text-xs font-bold uppercase tracking-widest text-slate-500">Resource Allocation</h4>
        <div className="grid grid-cols-3 gap-5">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-500"><Server className="h-4 w-4" /> Compute Node</div>
            <div className="font-bold text-slate-950">1x NVIDIA A100</div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-500"><Clock className="h-4 w-4" /> Est. Duration</div>
            <div className="font-bold text-slate-950">~4.5 Hours</div>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-500"><CircleDollarSign className="h-4 w-4 text-emerald-700" /> Cost Estimate</div>
            <div className="font-bold text-emerald-700">$12.40</div>
          </div>
        </div>
      </div>

      <div className="mt-10 flex items-center justify-between border-t border-slate-200 pt-6">
        <Button variant="ghost" onClick={() => setWorkflowStep(2)}>Back</Button>
        <Button className="h-12 px-8 bg-emerald-700 hover:bg-emerald-800 border-emerald-700"><Play className="mr-2 h-5 w-5 fill-current" /> Start Training</Button>
      </div>
    </div>
  </Card>
);

const ProjectsView = ({ workflowStep, setWorkflowStep, taskText, setTaskText }: any) => (
  <div className="space-y-8">
    <div className="flex items-center justify-between">
      <div>
        <h2 className="mb-2 text-2xl font-bold tracking-tight text-slate-950">Defect Detection - Assembly Line A</h2>
        <p className="text-sm text-slate-600">Configure your vision task and train a custom model.</p>
      </div>
      <Button variant="outline"><Settings className="mr-2 h-4 w-4" /> Project Settings</Button>
    </div>

    <ProjectDashboard />
    {workflowStep === 1 && <TaskStep taskText={taskText} setTaskText={setTaskText} setWorkflowStep={setWorkflowStep} />}
    {workflowStep === 2 && <DatasetStep setWorkflowStep={setWorkflowStep} />}
    {workflowStep === 3 && <RecommendStep setWorkflowStep={setWorkflowStep} />}
  </div>
);

const ModelsView = () => (
  <div>
    <div className="mb-8 flex items-center justify-between">
      <div>
        <h2 className="mb-2 text-2xl font-bold tracking-tight text-slate-950">Model Library</h2>
        <p className="text-sm text-slate-600">Pre-trained base models available for fine-tuning and production deployment.</p>
      </div>
      <div className="flex gap-3">
        <Button variant="outline"><Search className="mr-2 h-4 w-4" /> Filter</Button>
        <Button><Plus className="mr-2 h-4 w-4" /> Import Custom</Button>
      </div>
    </div>

    <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
      {modelLibrary.map((model) => (
        <Card key={model.id} className="overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-md">
          <div className="p-6">
            <div className="mb-6 flex items-start justify-between">
              <StatusPill tone={model.type === 'Classification' ? 'blue' : 'green'}>{model.type}</StatusPill>
              <button className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><MoreVertical className="h-5 w-5" /></button>
            </div>
            <h3 className="mb-5 truncate font-mono text-lg font-bold text-slate-950">{model.name}</h3>
            <div className="grid grid-cols-2 gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
              <div>
                <div className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-500">Parameters</div>
                <div className="font-bold text-slate-900">{model.params}</div>
              </div>
              <div>
                <div className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-500">Accuracy</div>
                <div className="font-bold text-emerald-700">{model.accuracy}</div>
              </div>
              <div className="col-span-2">
                <div className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-500">Input Resolution</div>
                <div className="font-bold text-slate-900">{model.res}</div>
              </div>
            </div>
          </div>
          <div className="flex gap-2 border-t border-slate-200 bg-slate-50 p-4">
            <Button variant="outline" className="h-9 flex-1 px-3 text-xs"><Eye className="mr-2 h-3.5 w-3.5" /> View</Button>
            <Button variant="outline" className="h-9 flex-1 px-3 text-xs"><Edit3 className="mr-2 h-3.5 w-3.5" /> Edit</Button>
            <Button variant="danger" className="h-9 px-3 text-xs"><Trash2 className="h-4 w-4" /></Button>
          </div>
        </Card>
      ))}
    </div>
  </div>
);

const InferenceView = () => (
  <div>
    <div className="mb-8">
      <h2 className="mb-2 text-2xl font-bold tracking-tight text-slate-950">Deployment & Inference</h2>
      <p className="text-sm text-slate-600">Deploy trained models to cloud services or controlled factory environments.</p>
    </div>

    <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
      <Card className="flex h-full flex-col p-10 transition-all hover:shadow-md">
        <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-xl border border-blue-200 bg-blue-50">
          <Cloud className="h-7 w-7 text-blue-700" />
        </div>
        <h3 className="mb-3 text-2xl font-bold text-slate-950">Cloud API</h3>
        <p className="mb-10 flex-1 leading-relaxed text-slate-600">Serve your model as a REST API instantly. Best for web apps, dashboards, and cloud integrations with managed scaling.</p>
        <div className="mb-10 space-y-4 rounded-2xl border border-slate-200 bg-slate-50 p-6">
          <div className="flex items-center gap-4 text-sm font-semibold text-slate-700"><CheckCircle2 className="h-5 w-5 text-emerald-700" /> 99.9% uptime SLA</div>
          <div className="flex items-center gap-4 text-sm font-semibold text-slate-700"><CheckCircle2 className="h-5 w-5 text-emerald-700" /> Auto-scaling GPU endpoints</div>
          <div className="flex items-center gap-4 text-sm font-semibold text-slate-700"><CheckCircle2 className="h-5 w-5 text-emerald-700" /> Managed API gateway</div>
        </div>
        <Button className="h-12 w-full text-base">Create Endpoint</Button>
      </Card>

      <Card className="flex h-full flex-col p-10 transition-all hover:shadow-md">
        <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-xl border border-slate-200 bg-slate-100">
          <Download className="h-7 w-7 text-slate-700" />
        </div>
        <h3 className="mb-3 text-2xl font-bold text-slate-950">Docker / Binary</h3>
        <p className="mb-10 flex-1 leading-relaxed text-slate-600">Download a compiled model package for factory floors, embedded devices, and air-gapped production systems.</p>
        <div className="mb-10 space-y-4 rounded-2xl border border-slate-200 bg-slate-50 p-6">
          <div className="flex items-center gap-4 text-sm font-semibold text-slate-700"><ShieldCheck className="h-5 w-5 text-slate-600" /> ONNX / TensorRT formats</div>
          <div className="flex items-center gap-4 text-sm font-semibold text-slate-700"><ShieldCheck className="h-5 w-5 text-slate-600" /> Offline capable</div>
          <div className="flex items-center gap-4 text-sm font-semibold text-slate-700"><ShieldCheck className="h-5 w-5 text-slate-600" /> Low-latency edge inference</div>
        </div>
        <div className="flex gap-4">
          <Button variant="secondary" className="h-12 flex-1 text-base"><Download className="mr-2 h-5 w-5" /> Docker Image</Button>
          <Button variant="outline" className="h-12 flex-1 text-base">Binary Package</Button>
        </div>
      </Card>
    </div>
  </div>
);

const HomeView = ({ navigateTo }: any) => (
  <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr]">
    <Card className="p-10">
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-900">
        <Activity className="h-8 w-8 text-white" />
      </div>
      <h2 className="mb-4 text-3xl font-bold tracking-tight text-slate-950">No-code vision model training for industrial teams</h2>
      <p className="mb-8 max-w-2xl text-base leading-relaxed text-slate-600">VisionDock helps automation teams define tasks, upload datasets, select model architectures, and deploy inference endpoints without managing machine learning infrastructure.</p>
      <Button onClick={() => navigateTo('projects')} className="h-12 px-8 text-base">Open Active Project</Button>
    </Card>

    <Card className="p-6">
      <div className="mb-5 flex items-center justify-between">
        <h3 className="text-lg font-bold text-slate-950">Project Dashboard</h3>
        <StatusPill tone="slate">3 Projects</StatusPill>
      </div>
      <div className="space-y-4">
        {recentProjects.map((project) => (
          <div key={project.id} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="mb-2 flex items-center justify-between">
              <div>
                <div className="font-bold text-slate-950">{project.name}</div>
                <div className="font-mono text-xs font-semibold text-slate-500">{project.id}</div>
              </div>
              <StatusPill tone={project.status === 'Done' ? 'green' : project.status === 'Training' ? 'amber' : 'slate'}>{project.status}</StatusPill>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-200">
              <div className="h-full rounded-full bg-blue-700" style={{ width: `${project.progress}%` }} />
            </div>
          </div>
        ))}
      </div>
    </Card>
  </div>
);

const MainContent = ({ currentView, workflowStep, setWorkflowStep, taskText, setTaskText, navigateTo }: any) => (
  <main className="flex-1 overflow-y-auto bg-slate-50 p-8">
    <div className="mx-auto max-w-6xl space-y-8 pb-12">
      {currentView === 'home' && <HomeView navigateTo={navigateTo} />}
      {currentView === 'projects' && <ProjectsView workflowStep={workflowStep} setWorkflowStep={setWorkflowStep} taskText={taskText} setTaskText={setTaskText} />}
      {currentView === 'models' && <ModelsView />}
      {currentView === 'inference' && <InferenceView />}
    </div>
  </main>
);

export function VisionDockSPA() {
  const [currentView, setCurrentView] = useState<ViewState>('projects');
  const [workflowStep, setWorkflowStep] = useState<WorkflowStep>(1);
  const [taskText, setTaskText] = useState('');

  return (
    <div className="flex h-screen w-full overflow-hidden bg-white font-sans text-slate-900 selection:bg-blue-100 selection:text-blue-900">
      <Sidebar currentView={currentView} navigateTo={setCurrentView} workflowStep={workflowStep} />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <Header currentView={currentView} />
        <MainContent
          currentView={currentView}
          workflowStep={workflowStep}
          setWorkflowStep={setWorkflowStep}
          taskText={taskText}
          setTaskText={setTaskText}
          navigateTo={setCurrentView}
        />
      </div>
    </div>
  );
}
