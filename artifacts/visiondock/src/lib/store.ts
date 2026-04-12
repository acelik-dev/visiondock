import { useSyncExternalStore } from 'react';
import { toast } from 'sonner';

export type ViewState = 'home' | 'projects' | 'models' | 'inference' | 'billing';
export type WorkflowStep = 1 | 2 | 3;
export type EventTone = 'blue' | 'green' | 'amber' | 'red' | 'slate';

export type AuditEvent = {
  id: number;
  title: string;
  detail: string;
  time: string;
  tone: EventTone;
};

export type ModelItem = {
  id: number;
  name: string;
  type: string;
  params: string;
  accuracy: string;
  res: string;
};

type State = {
  currentView: ViewState;
  workflowStep: WorkflowStep;
  datasetUploaded: boolean;
  syntheticGenerated: boolean;
  trainingStarted: boolean;
  taskText: string;
  models: ModelItem[];
  events: AuditEvent[];
  activePlan: string;
};

type Actions = {
  setCurrentView: (view: ViewState) => void;
  setWorkflowStep: (step: WorkflowStep) => void;
  setDatasetUploaded: (uploaded: boolean) => void;
  setSyntheticGenerated: (generated: boolean) => void;
  setTrainingStarted: (started: boolean) => void;
  setTaskText: (text: string) => void;
  addModel: (model: Omit<ModelItem, 'id'>) => void;
  deleteModel: (id: number) => void;
  setActivePlan: (plan: string) => void;
  addEvent: (title: string, detail: string, tone: EventTone) => void;
  notify: (message: string) => void;
};

export type VisionDockStore = State & Actions;

const initialModels: ModelItem[] = [
  { id: 1, name: 'beit_base_patch16_224', type: 'Sınıflandırma', params: '86.5M', accuracy: '%85.2', res: '224px' },
  { id: 2, name: 'convnext_base', type: 'Sınıflandırma', params: '88.6M', accuracy: '%83.8', res: '224px' },
  { id: 3, name: 'vit_large_patch16_384', type: 'Sınıflandırma', params: '304M', accuracy: '%87.1', res: '384px' },
  { id: 4, name: 'resnet50', type: 'Sınıflandırma', params: '25.6M', accuracy: '%79.8', res: '224px' },
  { id: 5, name: 'yolov8_m', type: 'Nesne Tespiti', params: '25.9M', accuracy: '50.2 mAP', res: '640px' },
  { id: 6, name: 'efficientdet_d3', type: 'Nesne Tespiti', params: '12.0M', accuracy: '45.4 mAP', res: '512px' },
];

const initialEvents: AuditEvent[] = [
  { id: 3, title: 'Eğitim onayı bekliyor', detail: 'GPU tahsisi ve maliyet onayı kullanıcıya gösterildi.', time: '09:24', tone: 'amber' },
  { id: 2, title: 'Görev tanımı kaydedildi', detail: 'Doğal dil açıklaması modele öneri üretmek için hazırlandı.', time: '09:18', tone: 'slate' },
  { id: 1, title: 'Proje oluşturuldu', detail: 'PRJ-8821 için hata tespiti çalışma alanı açıldı.', time: '09:12', tone: 'blue' },
];

const listeners = new Set<() => void>();

const notifyListeners = () => {
  listeners.forEach((listener) => listener());
};

const setState = (updater: Partial<State> | ((state: State) => Partial<State>)) => {
  const patch = typeof updater === 'function' ? updater(store) : updater;
  Object.assign(store, patch);
  notifyListeners();
};

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

const getSnapshot = () => store;

const store: VisionDockStore = {
  currentView: 'home',
  workflowStep: 1,
  datasetUploaded: false,
  syntheticGenerated: false,
  trainingStarted: false,
  taskText: '',
  models: initialModels,
  events: initialEvents,
  activePlan: 'pro',

  setCurrentView: (view) => setState({ currentView: view }),
  setWorkflowStep: (step) => setState({ workflowStep: step }),
  setDatasetUploaded: (uploaded) => setState({ datasetUploaded: uploaded }),
  setSyntheticGenerated: (generated) => setState({ syntheticGenerated: generated }),
  setTrainingStarted: (started) => setState({ trainingStarted: started }),
  setTaskText: (text) => setState({ taskText: text }),
  addModel: (model) => setState((state) => ({ models: [{ ...model, id: Date.now() }, ...state.models] })),
  deleteModel: (id) => setState((state) => ({ models: state.models.filter((model) => model.id !== id) })),
  setActivePlan: (plan) => setState({ activePlan: plan }),
  addEvent: (title, detail, tone) => setState((state) => ({
    events: [
      {
        id: Date.now(),
        title,
        detail,
        time: new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }),
        tone,
      },
      ...state.events,
    ],
  })),
  notify: (message) => {
    toast(message);
  },
};

export function useStore(): VisionDockStore;
export function useStore<T>(selector: (state: VisionDockStore) => T): T;
export function useStore<T>(selector?: (state: VisionDockStore) => T) {
  const state = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return selector ? selector(state) : state;
}
