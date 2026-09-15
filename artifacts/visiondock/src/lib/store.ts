import { create } from 'zustand';
import { toast } from 'sonner';
import { navigateToView, initialWorkflowStepFromUrl, navigateToProjectsStep, pathToView } from '@/lib/navigation';

export type ViewState =
  | "home"
  | "projects"
  | "models"
  | "datasets"
  | "inference"
  | "billing"
  | "admin"
  | "admin-users"
  | "admin-ledger"
  | "admin-credits"
  | "admin-membership"
  | "admin-projects"
  | "admin-marketplace"
  | "admin-system"
  | "skills";
export type WorkflowStep = 1 | 2 | 3;
export type EventTone = 'blue' | 'green' | 'amber' | 'red' | 'slate';

export type AuditEvent = {
  id: number;
  title: string;
  detail: string;
  time: string;
  tone: EventTone;
};

const initialEvents: AuditEvent[] = [];

export type VisionDockStore = {
  currentView: ViewState;
  workflowStep: WorkflowStep;
  datasetUploaded: boolean;
  syntheticGenerated: boolean;
  trainingStarted: boolean;
  taskText: string;
  events: AuditEvent[];
  activePlan: string;
  activeProjectId: string | null;
  activeProjectName: string | null;
  pendingNewProject: boolean;
  marketplaceSpecBootstrap: Record<string, unknown> | null;
  setMarketplaceSpecBootstrap: (spec: Record<string, unknown> | null) => void;
  setPendingNewProject: (pending: boolean) => void;
  setCurrentView: (view: ViewState) => void;
  setActiveProject: (id: string | null, name: string | null) => void;
  setWorkflowStep: (step: WorkflowStep) => void;
  setDatasetUploaded: (uploaded: boolean) => void;
  setSyntheticGenerated: (generated: boolean) => void;
  setTrainingStarted: (started: boolean) => void;
  setTaskText: (text: string) => void;
  setActivePlan: (plan: string) => void;
  addEvent: (title: string, detail: string, tone: EventTone) => void;
  notify: (message: string) => void;
};

export const useStore = create<VisionDockStore>((set) => ({
  currentView: typeof window !== 'undefined' ? pathToView(window.location.pathname) : 'home',
  workflowStep: initialWorkflowStepFromUrl(),
  datasetUploaded: false,
  syntheticGenerated: false,
  trainingStarted: false,
  taskText: '',
  events: initialEvents,
  activePlan: 'free',
  activeProjectId: null,
  activeProjectName: null,
  pendingNewProject: false,
  marketplaceSpecBootstrap: null,
  setMarketplaceSpecBootstrap: (spec) => set({ marketplaceSpecBootstrap: spec }),
  setPendingNewProject: (pending) => set({ pendingNewProject: pending }),
  setCurrentView: (view) => {
    set({ currentView: view });
    navigateToView(view);
  },
  setActiveProject: (id, name) => set({ activeProjectId: id, activeProjectName: name }),
  setWorkflowStep: (step) => {
    const { activeProjectId } = useStore.getState();
    set({ workflowStep: step });
    navigateToProjectsStep(step, activeProjectId);
  },
  setDatasetUploaded: (uploaded) => set({ datasetUploaded: uploaded }),
  setSyntheticGenerated: (generated) => set({ syntheticGenerated: generated }),
  setTrainingStarted: (started) => set({ trainingStarted: started }),
  setTaskText: (text) => set({ taskText: text }),
  setActivePlan: (plan) => set({ activePlan: plan }),
  addEvent: (title, detail, tone) => set((state) => ({
    events: [
      {
        id: Date.now(),
        title,
        detail,
        time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
        tone,
      },
      ...state.events,
    ],
  })),
  notify: (message) => {
    toast(message);
  },
}));
