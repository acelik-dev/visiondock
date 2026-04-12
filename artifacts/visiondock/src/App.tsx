import { Shell } from "@/components/layout";
import { useStore } from "@/lib/store";
import HomeView from "./pages/home";
import ProjectsView from "./pages/projects";
import ModelsView from "./pages/models";
import InferenceView from "./pages/inference";
import BillingView from "./pages/billing";
import { Toaster } from "@/components/ui/sonner";

export default function App() {
  const currentView = useStore((state) => state.currentView);

  return (
    <>
      <Shell>
        {currentView === 'home' && <HomeView />}
        {currentView === 'projects' && <ProjectsView />}
        {currentView === 'models' && <ModelsView />}
        {currentView === 'inference' && <InferenceView />}
        {currentView === 'billing' && <BillingView />}
      </Shell>
      <Toaster />
    </>
  );
}
