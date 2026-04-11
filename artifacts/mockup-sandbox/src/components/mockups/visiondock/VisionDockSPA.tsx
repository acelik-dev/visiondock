import React, { useState } from 'react';
import { 
  Home, 
  FolderGit2, 
  Library, 
  Cpu, 
  Settings, 
  Plus, 
  Search, 
  Bell, 
  User, 
  ChevronRight, 
  UploadCloud, 
  Folder, 
  FileImage, 
  FileJson, 
  Database,
  Sparkles,
  Play,
  Server,
  Download,
  AlertCircle,
  CheckCircle2,
  Clock,
  Activity,
  MoreVertical,
  Layers,
  BoxSelect,
  Eye,
  Trash2,
  TerminalSquare
} from 'lucide-react';

// --- Types & Data ---

type ViewState = 'home' | 'projects' | 'models' | 'inference';
type WorkflowStep = 1 | 2 | 3;

const MODEL_LIBRARY = [
  { id: 1, name: 'beit_base_patch16_224', type: 'Classification', params: '86M', accuracy: '85.2%', res: '224x224' },
  { id: 2, name: 'convnext_base', type: 'Classification', params: '89M', accuracy: '83.8%', res: '224x224' },
  { id: 3, name: 'vit_large_patch16_384', type: 'Classification', params: '304M', accuracy: '87.1%', res: '384x384' },
  { id: 4, name: 'resnet50', type: 'Classification', params: '25M', accuracy: '79.8%', res: '224x224' },
  { id: 5, name: 'yolov8_m', type: 'Object Detection', params: '25.9M', accuracy: '50.2 mAP', res: '640x640' },
  { id: 6, name: 'efficientdet_d3', type: 'Object Detection', params: '12M', accuracy: '45.4 mAP', res: '512x512' },
];

const RECENT_PROJECTS = [
  { id: 'PRJ-8821', name: 'Defect Detection - Assembly Line A', status: 'Training', progress: 68 },
  { id: 'PRJ-8820', name: 'Packaging Verification', status: 'Done', progress: 100 },
  { id: 'PRJ-8819', name: 'Safety Gear Compliance', status: 'Created', progress: 0 },
];

// --- Shared UI Components ---

const Button = ({ children, variant = 'primary', className = '', ...props }: any) => {
  const base = "inline-flex items-center justify-center rounded-md text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:pointer-events-none disabled:opacity-50 h-10 px-4 py-2";
  const variants = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-500 shadow-[0_0_15px_rgba(79,70,229,0.3)] border border-indigo-500",
    secondary: "bg-[#1e1b4b] text-indigo-200 hover:bg-[#312e81] border border-indigo-900 shadow-[0_0_10px_rgba(30,27,75,0.5)]",
    outline: "border border-slate-700 bg-transparent hover:bg-slate-800 text-slate-200",
    ghost: "hover:bg-slate-800 hover:text-slate-100 text-slate-400",
    danger: "bg-rose-900/30 text-rose-300 hover:bg-rose-900/60 border border-rose-800/50",
  };
  return (
    <button className={`${base} ${variants[variant as keyof typeof variants]} ${className}`} {...props}>
      {children}
    </button>
  );
};

const Card = ({ children, className = '' }: any) => (
  <div className={`rounded-xl border border-slate-800 bg-[#111827]/80 backdrop-blur-sm shadow-lg ${className}`}>
    {children}
  </div>
);

// --- Modular Components ---

const Sidebar = ({ currentView, navigateTo, workflowStep }: { currentView: ViewState, navigateTo: (v: ViewState) => void, workflowStep: WorkflowStep }) => {
  return (
    <div className="w-64 border-r border-slate-800 bg-[#0a0f1c] flex flex-col z-20 shadow-[4px_0_24px_rgba(0,0,0,0.4)]">
      <div className="p-5 flex items-center gap-3 border-b border-slate-800/50">
        <div className="w-8 h-8 rounded bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-[0_0_15px_rgba(99,102,241,0.4)]">
          <Activity className="w-5 h-5 text-white" />
        </div>
        <span className="font-bold text-lg tracking-tight text-white">VisionDock</span>
      </div>
      
      <div className="flex-1 py-6 flex flex-col gap-1.5 px-3">
        <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3 px-3">Workspace</div>
        
        <button onClick={() => navigateTo('home')} className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all ${currentView === 'home' ? 'bg-indigo-900/30 text-indigo-300 border border-indigo-800/50 shadow-[inset_0_0_12px_rgba(79,70,229,0.1)]' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border border-transparent'}`}>
          <Home className="w-4 h-4" /> Home
        </button>
        <button onClick={() => navigateTo('projects')} className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all ${currentView === 'projects' ? 'bg-indigo-900/30 text-indigo-300 border border-indigo-800/50 shadow-[inset_0_0_12px_rgba(79,70,229,0.1)]' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border border-transparent'}`}>
          <FolderGit2 className="w-4 h-4" /> Projects
        </button>
        <button onClick={() => navigateTo('models')} className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all ${currentView === 'models' ? 'bg-indigo-900/30 text-indigo-300 border border-indigo-800/50 shadow-[inset_0_0_12px_rgba(79,70,229,0.1)]' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border border-transparent'}`}>
          <Library className="w-4 h-4" /> Model Library
        </button>
        <button onClick={() => navigateTo('inference')} className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all ${currentView === 'inference' ? 'bg-indigo-900/30 text-indigo-300 border border-indigo-800/50 shadow-[inset_0_0_12px_rgba(79,70,229,0.1)]' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border border-transparent'}`}>
          <Cpu className="w-4 h-4" /> Inference
        </button>
      </div>

      {/* Active Project Widget */}
      <div className="p-4 border-t border-slate-800/80 bg-gradient-to-b from-[#0a0f1c] to-[#070b14]">
        <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3 px-1">Active Session</div>
        <div className="bg-[#111827]/90 border border-indigo-900/30 rounded-xl p-4 shadow-[0_0_20px_rgba(0,0,0,0.5)]">
          <div className="text-sm font-semibold text-white mb-0.5 truncate">Defect Detection</div>
          <div className="text-xs text-indigo-400/80 font-mono mb-5">PRJ-8821</div>
          
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center border ${workflowStep >= 1 ? 'bg-indigo-600 border-indigo-400 text-white shadow-[0_0_10px_rgba(79,70,229,0.5)]' : 'bg-[#0f172a] border-slate-700 text-slate-500'}`}>
                {workflowStep > 1 ? <CheckCircle2 className="w-3.5 h-3.5" /> : <span className="text-[11px] font-bold">1</span>}
              </div>
              <span className={`text-xs font-medium ${workflowStep >= 1 ? 'text-indigo-100' : 'text-slate-500'}`}>Step 1 Task</span>
            </div>
            
            <div className="flex items-center gap-3 relative">
              <div className={`absolute -top-4 left-3 w-px h-4 ${workflowStep >= 2 ? 'bg-indigo-600' : 'bg-slate-800'}`}></div>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center border ${workflowStep >= 2 ? 'bg-indigo-600 border-indigo-400 text-white shadow-[0_0_10px_rgba(79,70,229,0.5)]' : 'bg-[#0f172a] border-slate-700 text-slate-500'}`}>
                {workflowStep > 2 ? <CheckCircle2 className="w-3.5 h-3.5" /> : <span className="text-[11px] font-bold">2</span>}
              </div>
              <span className={`text-xs font-medium ${workflowStep >= 2 ? 'text-indigo-100' : 'text-slate-500'}`}>Step 2 Dataset</span>
            </div>
            
            <div className="flex items-center gap-3 relative">
              <div className={`absolute -top-4 left-3 w-px h-4 ${workflowStep >= 3 ? 'bg-indigo-600' : 'bg-slate-800'}`}></div>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center border ${workflowStep >= 3 ? 'bg-indigo-600 border-indigo-400 text-white shadow-[0_0_10px_rgba(79,70,229,0.5)]' : 'bg-[#0f172a] border-slate-700 text-slate-500'}`}>
                <span className="text-[11px] font-bold">3</span>
              </div>
              <span className={`text-xs font-medium ${workflowStep >= 3 ? 'text-indigo-100' : 'text-slate-500'}`}>Step 3 Recommend</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const Header = ({ currentView }: { currentView: ViewState }) => {
  return (
    <header className="h-16 border-b border-slate-800/80 bg-[#0a0f1c]/80 backdrop-blur-xl flex items-center justify-between px-8 sticky top-0 z-10 shadow-sm">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-semibold text-white capitalize">{currentView}</h1>
        {currentView === 'projects' && (
          <div className="flex items-center gap-2 text-sm">
            <ChevronRight className="w-4 h-4 text-slate-600" />
            <span className="text-indigo-400 font-mono px-2 py-0.5 rounded bg-indigo-950/30 border border-indigo-900/50">PRJ-8821</span>
          </div>
        )}
      </div>
      
      <div className="flex items-center gap-5">
        <div className="relative group">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-indigo-400 transition-colors" />
          <input 
            type="text" 
            placeholder="Search resources..." 
            className="bg-[#111827] border border-slate-800 rounded-md pl-9 pr-4 py-1.5 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 text-white w-64 transition-all shadow-[inset_0_2px_4px_rgba(0,0,0,0.2)]"
          />
        </div>
        <button className="text-slate-400 hover:text-white relative p-1 transition-colors">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1 right-1 w-2 h-2 bg-rose-500 rounded-full border border-[#0a0f1c] shadow-[0_0_5px_rgba(244,63,94,0.5)]"></span>
        </button>
        <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-slate-800 to-slate-700 flex items-center justify-center border border-slate-600 shadow-sm cursor-pointer hover:border-slate-500 transition-colors">
          <User className="w-4 h-4 text-slate-300" />
        </div>
      </div>
    </header>
  );
};

const MainContent = ({ 
  currentView, 
  workflowStep, 
  setWorkflowStep, 
  taskText, 
  setTaskText, 
  navigateTo 
}: any) => {
  return (
    <main className="flex-1 overflow-y-auto p-8 scroll-smooth bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-indigo-950/10 via-[#030712] to-[#030712]">
      <div className="max-w-5xl mx-auto space-y-8 pb-12">
        
        {/* VIEW: PROJECTS */}
        {currentView === 'projects' && (
          <div className="space-y-8">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold text-white mb-2 tracking-tight">Defect Detection - Assembly Line A</h2>
                <p className="text-slate-400 text-sm">Configure your vision task and train a custom model.</p>
              </div>
              <div className="flex gap-3">
                <Button variant="outline"><Settings className="w-4 h-4 mr-2" /> Project Settings</Button>
              </div>
            </div>

            {/* Dashboard Stats */}
            <div className="grid grid-cols-4 gap-5">
              <Card className="p-5 flex flex-col justify-between group hover:border-indigo-500/30 transition-colors">
                <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">Status</div>
                <div className="flex items-center gap-2 mt-3">
                  <div className="w-2 h-2 rounded-full bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.6)]"></div>
                  <span className="text-lg font-semibold text-white">Configuring</span>
                </div>
              </Card>
              <Card className="p-5 flex flex-col justify-between group hover:border-indigo-500/30 transition-colors">
                <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">Project ID</div>
                <div className="text-lg font-mono text-indigo-400 mt-3 font-semibold">PRJ-8821</div>
              </Card>
              <Card className="p-5 flex flex-col justify-between group hover:border-indigo-500/30 transition-colors">
                <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">Created Models</div>
                <div className="text-lg font-semibold text-white mt-3">0</div>
              </Card>
              <Card className="p-5 flex flex-col justify-between group hover:border-indigo-500/30 transition-colors">
                <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">Dataset Size</div>
                <div className="text-lg font-semibold text-slate-500 mt-3">--</div>
              </Card>
            </div>

            {/* Step 1: Task Definition */}
            {workflowStep === 1 && (
              <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                <Card className="p-8 border-indigo-500/30 shadow-[0_0_30px_rgba(79,70,229,0.05)] relative overflow-hidden">
                  <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none">
                    <TerminalSquare className="w-64 h-64" />
                  </div>
                  
                  <div className="relative z-10">
                    <h3 className="text-xl font-bold text-white mb-2 flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-sm shadow-[0_0_15px_rgba(79,70,229,0.4)]">1</div>
                      Define Vision Task
                    </h3>
                    <p className="text-slate-400 text-sm mb-8 max-w-2xl">Describe what you want the AI to detect or classify in natural language. We'll use this to recommend the best model architecture.</p>
                    
                    <div className="relative group">
                      <div className="absolute -inset-0.5 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-lg blur opacity-20 group-focus-within:opacity-40 transition duration-500"></div>
                      <textarea 
                        value={taskText}
                        onChange={(e) => setTaskText(e.target.value)}
                        placeholder="e.g. Detect surface scratches, dents, and missing screws on metallic assembly parts..."
                        className="relative w-full h-36 bg-[#0a0f1c] border border-slate-700/80 rounded-lg p-5 text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 resize-none transition-all shadow-[inset_0_2px_10px_rgba(0,0,0,0.2)] text-base"
                      ></textarea>
                    </div>

                    <div className="mt-8">
                      <h4 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Examples</h4>
                      <div className="grid grid-cols-3 gap-5">
                        <button onClick={() => setTaskText("Classify items into 'Pass' or 'Fail' categories based on visual appearance.")} className="p-4 rounded-xl border border-slate-800 bg-[#111827] hover:border-indigo-500/50 hover:bg-[#1e1b4b]/40 text-left transition-all group shadow-sm hover:shadow-[0_0_20px_rgba(79,70,229,0.1)]">
                          <Layers className="w-6 h-6 text-indigo-400 mb-3 group-hover:text-indigo-300" />
                          <div className="text-sm font-semibold text-white mb-1.5">Classification</div>
                          <div className="text-xs text-slate-400">Categorize entire images</div>
                        </button>
                        <button onClick={() => setTaskText("Detect and draw bounding boxes around pedestrians, forklifts, and safety cones.")} className="p-4 rounded-xl border border-slate-800 bg-[#111827] hover:border-indigo-500/50 hover:bg-[#1e1b4b]/40 text-left transition-all group shadow-sm hover:shadow-[0_0_20px_rgba(79,70,229,0.1)]">
                          <BoxSelect className="w-6 h-6 text-teal-400 mb-3 group-hover:text-teal-300" />
                          <div className="text-sm font-semibold text-white mb-1.5">Object Detection</div>
                          <div className="text-xs text-slate-400">Locate specific items</div>
                        </button>
                        <button onClick={() => setTaskText("Identify anomalous patterns or structural defects that deviate from the standard normal baseline.")} className="p-4 rounded-xl border border-slate-800 bg-[#111827] hover:border-indigo-500/50 hover:bg-[#1e1b4b]/40 text-left transition-all group shadow-sm hover:shadow-[0_0_20px_rgba(79,70,229,0.1)]">
                          <AlertCircle className="w-6 h-6 text-rose-400 mb-3 group-hover:text-rose-300" />
                          <div className="text-sm font-semibold text-white mb-1.5">Anomaly Detection</div>
                          <div className="text-xs text-slate-400">Find unexpected defects</div>
                        </button>
                      </div>
                    </div>

                    <div className="mt-10 flex justify-end border-t border-slate-800/50 pt-6">
                      <Button onClick={() => setWorkflowStep(2)} className="w-40 group h-11 text-base">
                        Next Step <ChevronRight className="w-4 h-4 ml-2 group-hover:translate-x-1.5 transition-transform" />
                      </Button>
                    </div>
                  </div>
                </Card>
              </div>
            )}

            {/* Step 2: Dataset Upload */}
            {workflowStep === 2 && (
              <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                <Card className="p-8 border-indigo-500/30 shadow-[0_0_30px_rgba(79,70,229,0.05)]">
                  <h3 className="text-xl font-bold text-white mb-2 flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-sm shadow-[0_0_15px_rgba(79,70,229,0.4)]">2</div>
                    Dataset Upload
                  </h3>
                  <p className="text-slate-400 text-sm mb-8">Upload your images and annotations. <span className="text-amber-400/80 font-medium">Limit 32GB per .zip</span></p>
                  
                  <div className="border-2 border-dashed border-slate-700 rounded-xl bg-[#0a0f1c] p-12 flex flex-col items-center justify-center text-center hover:border-indigo-500/50 hover:bg-indigo-950/10 transition-all cursor-pointer group">
                    <div className="w-20 h-20 rounded-full bg-slate-800/50 flex items-center justify-center mb-5 group-hover:bg-indigo-900/40 group-hover:shadow-[0_0_20px_rgba(79,70,229,0.2)] transition-all">
                      <UploadCloud className="w-10 h-10 text-slate-400 group-hover:text-indigo-400" />
                    </div>
                    <h4 className="text-lg font-semibold text-white mb-2">Drag and drop your dataset here</h4>
                    <p className="text-sm text-slate-500 mb-6">Supports YOLO format, COCO JSON, or structured Image Folders.</p>
                    <Button variant="secondary" className="px-8">Browse Files</Button>
                  </div>

                  <div className="grid grid-cols-5 gap-6 mt-8">
                    <div className="col-span-3 p-5 rounded-xl bg-[#0a0f1c] border border-slate-800/80 shadow-[inset_0_2px_10px_rgba(0,0,0,0.2)]">
                      <h5 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2"><Database className="w-4 h-4 text-indigo-400" /> Expected Structure</h5>
                      <div className="text-sm font-mono text-slate-400 space-y-1.5 p-2 bg-[#111827] rounded-lg border border-slate-800/50">
                        <div className="flex items-center gap-2"><Folder className="w-4 h-4 text-slate-500" /> dataset/</div>
                        <div className="flex items-center gap-2 pl-6"><Folder className="w-4 h-4 text-indigo-400" /> images/</div>
                        <div className="flex items-center gap-2 pl-12"><FileImage className="w-4 h-4 text-slate-600" /> img1.jpg</div>
                        <div className="flex items-center gap-2 pl-12"><FileImage className="w-4 h-4 text-slate-600" /> img2.jpg</div>
                        <div className="flex items-center gap-2 pl-6"><Folder className="w-4 h-4 text-teal-400" /> labels/</div>
                        <div className="flex items-center gap-2 pl-12"><FileJson className="w-4 h-4 text-slate-600" /> img1.txt</div>
                        <div className="flex items-center gap-2 pl-12"><FileJson className="w-4 h-4 text-slate-600" /> img2.txt</div>
                      </div>
                    </div>

                    <div className="col-span-2 p-6 rounded-xl bg-gradient-to-br from-indigo-950/40 to-[#1e1b4b]/60 border border-indigo-500/20 flex flex-col justify-center items-center text-center shadow-[inset_0_0_20px_rgba(79,70,229,0.05)]">
                      <div className="w-14 h-14 rounded-xl bg-indigo-500/10 flex items-center justify-center mb-4 border border-indigo-500/20">
                        <Sparkles className="w-7 h-7 text-indigo-400" />
                      </div>
                      <h5 className="text-base font-semibold text-indigo-200 mb-2">Verin yetersiz mi?</h5>
                      <p className="text-sm text-slate-400 mb-6 leading-relaxed">Üretken yapay zeka ile sentetik veri üret.</p>
                      <Button variant="secondary" className="w-full">Generate Synthetic Data</Button>
                    </div>
                  </div>

                  <div className="mt-10 flex justify-between items-center border-t border-slate-800/50 pt-6">
                    <Button variant="ghost" onClick={() => setWorkflowStep(1)}>Back</Button>
                    <Button onClick={() => setWorkflowStep(3)} className="w-40 group h-11 text-base">
                      Next Step <ChevronRight className="w-4 h-4 ml-2 group-hover:translate-x-1.5 transition-transform" />
                    </Button>
                  </div>
                </Card>
              </div>
            )}

            {/* Step 3: Recommend & Train */}
            {workflowStep === 3 && (
              <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                <Card className="p-8 border-indigo-500/30 shadow-[0_0_30px_rgba(79,70,229,0.05)]">
                  <h3 className="text-xl font-bold text-white mb-2 flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-sm shadow-[0_0_15px_rgba(79,70,229,0.4)]">3</div>
                    Recommend & Train
                  </h3>
                  <p className="text-slate-400 text-sm mb-8">Review allocation and begin model training.</p>
                  
                  <div className="bg-[#0a0f1c] rounded-xl border border-slate-700/80 p-6 mb-8 shadow-[inset_0_2px_10px_rgba(0,0,0,0.2)]">
                    <div className="flex items-center justify-between mb-6 pb-6 border-b border-slate-800/80">
                      <div>
                        <div className="text-xs font-bold text-slate-500 uppercase tracking-widest">Recommended Model Architecture</div>
                        <div className="text-2xl font-bold text-indigo-300 mt-2">YOLOv8 Medium</div>
                      </div>
                      <div className="text-right">
                        <div className="text-xs font-bold text-slate-500 uppercase tracking-widest">Task Type</div>
                        <div className="text-lg font-semibold text-white mt-2">Object Detection</div>
                      </div>
                    </div>

                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Resource Allocation</h4>
                    <div className="grid grid-cols-3 gap-5">
                      <div className="bg-[#111827] p-4 rounded-lg border border-slate-700/50 shadow-sm">
                        <div className="flex items-center gap-2 text-slate-400 text-sm mb-2"><Server className="w-4 h-4" /> Compute Node</div>
                        <div className="text-base font-semibold text-white">1x NVIDIA A100</div>
                      </div>
                      <div className="bg-[#111827] p-4 rounded-lg border border-slate-700/50 shadow-sm">
                        <div className="flex items-center gap-2 text-slate-400 text-sm mb-2"><Clock className="w-4 h-4" /> Est. Duration</div>
                        <div className="text-base font-semibold text-white">~4.5 Hours</div>
                      </div>
                      <div className="bg-[#111827] p-4 rounded-lg border border-emerald-900/30 bg-emerald-950/10 shadow-sm">
                        <div className="flex items-center gap-2 text-slate-400 text-sm mb-2"><Activity className="w-4 h-4 text-emerald-500" /> Cost Est.</div>
                        <div className="text-base font-bold text-emerald-400">$12.40</div>
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-between items-center mt-10 border-t border-slate-800/50 pt-6">
                    <Button variant="ghost" onClick={() => setWorkflowStep(2)}>Back</Button>
                    <Button className="bg-emerald-600 hover:bg-emerald-500 text-white shadow-[0_0_20px_rgba(16,185,129,0.3)] border border-emerald-500 h-12 px-8 text-base">
                      <Play className="w-5 h-5 mr-2 fill-current" /> Start Training
                    </Button>
                  </div>
                </Card>
              </div>
            )}
          </div>
        )}

        {/* VIEW: MODEL LIBRARY */}
        {currentView === 'models' && (
          <div className="animate-in fade-in duration-500">
            <div className="flex items-center justify-between mb-8">
              <div>
                <h2 className="text-2xl font-bold text-white mb-2 tracking-tight">Model Library</h2>
                <p className="text-slate-400 text-sm">Pre-trained base models available for fine-tuning.</p>
              </div>
              <div className="flex gap-3">
                <Button variant="outline"><Search className="w-4 h-4 mr-2" /> Filter</Button>
                <Button><Plus className="w-4 h-4 mr-2" /> Import Custom</Button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {MODEL_LIBRARY.map((model) => (
                <Card key={model.id} className="flex flex-col overflow-hidden hover:border-indigo-500/40 transition-all hover:-translate-y-1 hover:shadow-[0_10px_30px_rgba(79,70,229,0.1)] group">
                  <div className="p-6 flex-1 bg-gradient-to-b from-[#111827] to-[#0a0f1c]">
                    <div className="flex justify-between items-start mb-6">
                      <div className="px-2.5 py-1 rounded bg-indigo-500/10 text-indigo-300 text-[10px] font-bold uppercase tracking-widest border border-indigo-500/20">
                        {model.type}
                      </div>
                      <button className="text-slate-500 hover:text-white transition-colors"><MoreVertical className="w-5 h-5" /></button>
                    </div>
                    <h3 className="text-lg font-mono font-bold text-white mb-5 truncate">{model.name}</h3>
                    
                    <div className="grid grid-cols-2 gap-4 text-sm bg-[#111827] p-4 rounded-lg border border-slate-800">
                      <div>
                        <div className="text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">Parameters</div>
                        <div className="font-semibold text-slate-200">{model.params}</div>
                      </div>
                      <div>
                        <div className="text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">Accuracy</div>
                        <div className="font-semibold text-emerald-400">{model.accuracy}</div>
                      </div>
                      <div className="col-span-2 mt-2">
                        <div className="text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">Input Res</div>
                        <div className="font-semibold text-slate-200">{model.res}</div>
                      </div>
                    </div>
                  </div>
                  <div className="bg-[#0f172a] border-t border-slate-800/80 p-4 flex justify-end gap-3 opacity-90 group-hover:opacity-100 transition-opacity">
                    <Button variant="outline" className="h-9 px-4 text-xs flex-1"><Eye className="w-3.5 h-3.5 mr-2"/> View</Button>
                    <Button variant="danger" className="h-9 px-3 text-xs"><Trash2 className="w-4 h-4"/></Button>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* VIEW: INFERENCE */}
        {currentView === 'inference' && (
          <div className="animate-in fade-in duration-500">
             <div className="flex items-center justify-between mb-8">
              <div>
                <h2 className="text-2xl font-bold text-white mb-2 tracking-tight">Deployment & Inference</h2>
                <p className="text-slate-400 text-sm">Deploy your trained models to production environments.</p>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <Card className="p-10 border-indigo-500/30 flex flex-col h-full hover:border-indigo-400/50 transition-all hover:shadow-[0_10px_40px_rgba(79,70,229,0.1)] relative overflow-hidden">
                <div className="absolute top-0 right-0 p-10 opacity-[0.03] pointer-events-none">
                  <Cloud className="w-48 h-48" />
                </div>
                <div className="relative z-10 flex flex-col h-full">
                  <div className="w-14 h-14 rounded-xl bg-indigo-600/20 flex items-center justify-center mb-6 border border-indigo-500/40 shadow-[0_0_15px_rgba(79,70,229,0.2)]">
                    <Activity className="w-7 h-7 text-indigo-400" />
                  </div>
                  <h3 className="text-2xl font-bold text-white mb-3">Cloud API</h3>
                  <p className="text-slate-400 mb-10 flex-1 leading-relaxed">Serve your model as a REST API instantly. Best for web apps, dashboards, and cloud integrations. Fully managed scaling.</p>
                  
                  <div className="space-y-4 mb-10 bg-[#0a0f1c] p-6 rounded-xl border border-slate-800/80">
                    <div className="flex items-center gap-4 text-sm font-medium text-slate-300"><CheckCircle2 className="w-5 h-5 text-emerald-500 drop-shadow-[0_0_5px_rgba(16,185,129,0.5)]" /> 99.9% Uptime SLA</div>
                    <div className="flex items-center gap-4 text-sm font-medium text-slate-300"><CheckCircle2 className="w-5 h-5 text-emerald-500 drop-shadow-[0_0_5px_rgba(16,185,129,0.5)]" /> Auto-scaling GPUs</div>
                    <div className="flex items-center gap-4 text-sm font-medium text-slate-300"><CheckCircle2 className="w-5 h-5 text-emerald-500 drop-shadow-[0_0_5px_rgba(16,185,129,0.5)]" /> Managed API Gateway</div>
                  </div>

                  <Button className="w-full h-12 text-base font-semibold">Create Endpoint</Button>
                </div>
              </Card>

              <Card className="p-10 border-slate-700/80 flex flex-col h-full hover:border-slate-500 transition-all hover:shadow-[0_10px_40px_rgba(0,0,0,0.3)]">
                <div className="flex flex-col h-full">
                  <div className="w-14 h-14 rounded-xl bg-[#1e293b] flex items-center justify-center mb-6 border border-slate-600">
                    <Download className="w-7 h-7 text-slate-300" />
                  </div>
                  <h3 className="text-2xl font-bold text-white mb-3">Edge Deployment</h3>
                  <p className="text-slate-400 mb-10 flex-1 leading-relaxed">Download compiled model weights or a Docker container. Best for factory floors, embedded devices, and air-gapped systems.</p>
                  
                  <div className="space-y-4 mb-10 bg-[#0a0f1c] p-6 rounded-xl border border-slate-800/80">
                    <div className="flex items-center gap-4 text-sm font-medium text-slate-300"><CheckCircle2 className="w-5 h-5 text-slate-500" /> ONNX / TensorRT Formats</div>
                    <div className="flex items-center gap-4 text-sm font-medium text-slate-300"><CheckCircle2 className="w-5 h-5 text-slate-500" /> Offline Capable</div>
                    <div className="flex items-center gap-4 text-sm font-medium text-slate-300"><CheckCircle2 className="w-5 h-5 text-slate-500" /> Zero Latency Inference</div>
                  </div>

                  <div className="flex gap-4">
                    <Button variant="secondary" className="flex-1 h-12 text-base"><Download className="w-5 h-5 mr-2"/> Docker Image</Button>
                    <Button variant="outline" className="flex-1 h-12 text-base">Weights Only</Button>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        )}

        {/* Empty States for Home */}
        {currentView === 'home' && (
          <div className="animate-in fade-in duration-500 flex flex-col items-center justify-center h-full min-h-[500px] text-center">
             <div className="w-24 h-24 bg-[#0a0f1c] rounded-2xl flex items-center justify-center mb-8 border border-indigo-500/20 shadow-[0_0_30px_rgba(79,70,229,0.1)]">
                <Activity className="w-12 h-12 text-indigo-400" />
             </div>
             <h2 className="text-3xl font-bold text-white mb-4 tracking-tight">Welcome to VisionDock</h2>
             <p className="text-slate-400 max-w-md mx-auto mb-10 text-base leading-relaxed">Your control room for no-code computer vision. Start by selecting a project or exploring the model library.</p>
             <Button onClick={() => navigateTo('projects')} className="h-12 px-8 text-base shadow-[0_0_20px_rgba(79,70,229,0.3)]">Go to Projects</Button>
          </div>
        )}

      </div>
    </main>
  );
};

// --- Mock Missing Icon ---
const Cloud = ({ className }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>
  </svg>
);

// --- Root Component ---

export function VisionDockSPA() {
  const [currentView, setCurrentView] = useState<ViewState>('projects');
  const [workflowStep, setWorkflowStep] = useState<WorkflowStep>(1);
  const [taskText, setTaskText] = useState('');

  return (
    <div className="flex h-screen w-full bg-[#030712] text-slate-200 font-sans overflow-hidden selection:bg-indigo-500/30 selection:text-indigo-200">
      <Sidebar currentView={currentView} navigateTo={setCurrentView} workflowStep={workflowStep} />
      <div className="flex-1 flex flex-col min-w-0 relative">
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
