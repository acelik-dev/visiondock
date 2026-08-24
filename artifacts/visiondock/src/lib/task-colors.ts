import type { TaskType } from "@/lib/project-spec";

/** Shared task-type badge styling for marketplace & project views. */
export const TASK_BADGE_CLASSES: Record<string, string> = {
  classification: "bg-violet-500/10 text-violet-700 border-violet-500/20 dark:text-violet-300",
  multi_label: "bg-fuchsia-500/10 text-fuchsia-700 border-fuchsia-500/20 dark:text-fuchsia-300",
  regression: "bg-amber-500/10 text-amber-800 border-amber-500/20 dark:text-amber-300",
  object_localization: "bg-cyan-500/10 text-cyan-800 border-cyan-500/20 dark:text-cyan-300",
  object_detection: "bg-emerald-500/10 text-emerald-800 border-emerald-500/20 dark:text-emerald-300",
};

export function taskBadgeClass(taskType: TaskType | string): string {
  return TASK_BADGE_CLASSES[taskType] ?? "bg-muted text-muted-foreground border-border";
}
