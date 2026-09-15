import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { projectsPath } from "@/lib/navigation";
import { useStore } from "@/lib/store";
import {
  Coins,
  Cpu,
  CreditCard,
  Database,
  FolderGit2,
  Home,
  Library,
  Plus,
  Server,
  Shield,
  Sparkles,
  Users,
  Wand2,
} from "lucide-react";

export function CommandPalette({
  open,
  onOpenChange,
  isAdmin = false,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  isAdmin?: boolean;
}) {
  const [, navigate] = useLocation();
  const { workflowStep, activeProjectId, setCurrentView, setWorkflowStep, setPendingNewProject } = useStore();

  const go = (path: string, view?: Parameters<typeof setCurrentView>[0]) => {
    navigate(path);
    if (view) setCurrentView(view);
    onOpenChange(false);
  };

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [open, onOpenChange]);

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Search pages, actions…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        {isAdmin ? (
          <CommandGroup heading="Admin">
            <CommandItem onSelect={() => go("/admin", "admin")}>
              <Shield className="mr-2 h-4 w-4" /> Overview
            </CommandItem>
            <CommandItem onSelect={() => go("/admin/users", "admin-users")}>
              <Users className="mr-2 h-4 w-4" /> Users
            </CommandItem>
            <CommandItem onSelect={() => go("/admin/ledger", "admin-ledger")}>
              <Coins className="mr-2 h-4 w-4" /> Credit ledger
            </CommandItem>
            <CommandItem onSelect={() => go("/admin/credits", "admin-credits")}>
              <CreditCard className="mr-2 h-4 w-4" /> Credit settings
            </CommandItem>
            <CommandItem onSelect={() => go("/admin/membership", "admin-membership")}>
              <Sparkles className="mr-2 h-4 w-4" /> Membership
            </CommandItem>
            <CommandItem onSelect={() => go("/admin/projects", "admin-projects")}>
              <FolderGit2 className="mr-2 h-4 w-4" /> All projects
            </CommandItem>
            <CommandItem onSelect={() => go("/admin/marketplace", "admin-marketplace")}>
              <Database className="mr-2 h-4 w-4" /> Marketplace
            </CommandItem>
            <CommandItem onSelect={() => go("/skills", "skills")}>
              <Wand2 className="mr-2 h-4 w-4" /> Pipeline Skills
            </CommandItem>
            <CommandItem onSelect={() => go("/admin/system", "admin-system")}>
              <Server className="mr-2 h-4 w-4" /> System
            </CommandItem>
          </CommandGroup>
        ) : (
          <>
            <CommandGroup heading="Navigate">
              <CommandItem onSelect={() => go("/home", "home")}>
                <Home className="mr-2 h-4 w-4" /> Home
              </CommandItem>
              <CommandItem onSelect={() => go(projectsPath(workflowStep, activeProjectId), "projects")}>
                <FolderGit2 className="mr-2 h-4 w-4" /> Discovery & Projects
              </CommandItem>
              <CommandItem onSelect={() => go("/models", "models")}>
                <Library className="mr-2 h-4 w-4" /> Model Library
              </CommandItem>
              <CommandItem onSelect={() => go("/datasets", "datasets")}>
                <Database className="mr-2 h-4 w-4" /> Dataset Library
              </CommandItem>
              <CommandItem onSelect={() => go(activeProjectId ? `/inference/${activeProjectId}` : "/inference", "inference")}>
                <Cpu className="mr-2 h-4 w-4" /> Inference
              </CommandItem>
              <CommandItem onSelect={() => go("/billing", "billing")}>
                <CreditCard className="mr-2 h-4 w-4" /> Billing
              </CommandItem>
            </CommandGroup>
            <CommandSeparator />
            <CommandGroup heading="Actions">
              <CommandItem
                onSelect={() => {
                  setPendingNewProject(true);
                  setWorkflowStep(1);
                  go(projectsPath(1, null), "projects");
                }}
              >
                <Plus className="mr-2 h-4 w-4" /> New workspace
              </CommandItem>
              <CommandItem
                onSelect={() => {
                  setWorkflowStep(1);
                  go(projectsPath(1, activeProjectId), "projects");
                }}
              >
                <Sparkles className="mr-2 h-4 w-4" /> Open discovery
              </CommandItem>
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
}

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  return { open, setOpen };
}
