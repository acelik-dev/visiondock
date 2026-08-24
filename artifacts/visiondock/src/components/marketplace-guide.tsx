import { TASK_TYPE_PLAIN } from "@/lib/marketplace-copy";
import type { TaskType } from "@/lib/project-spec";
import { taskTypeLabel } from "@/lib/marketplace-api";
import { BookOpen, Info, Lightbulb } from "lucide-react";

type PageIntro = {
  title: string;
  body: string;
  startNote: string;
};

export function MarketplacePageIntro({ intro }: { intro: PageIntro }) {
  return (
    <div className="vd-hero space-y-3 p-6">
      <div className="flex items-start gap-4">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg shadow-primary/25">
          <BookOpen className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-foreground">{intro.title}</h2>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{intro.body}</p>
        </div>
      </div>
      <p className="flex items-start gap-2 rounded-lg border border-primary/15 bg-primary/5 px-3 py-2 text-xs text-primary">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>{intro.startNote}</span>
      </p>
    </div>
  );
}

export function MarketplaceTaskGuide({ taskType }: { taskType: TaskType | "all" }) {
  if (taskType === "all") {
    return (
      <div className="rounded-xl border border-border/50 bg-muted/30 p-5">
        <p className="vd-label mb-3">What do these task types mean?</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(Object.keys(TASK_TYPE_PLAIN) as TaskType[]).map((task) => {
            const guide = TASK_TYPE_PLAIN[task];
            return (
              <div key={task} className="rounded-lg border border-border/50 bg-card p-3">
                <p className="text-xs font-semibold text-foreground">{taskTypeLabel(task)}</p>
                <p className="mt-1 text-xs text-muted-foreground">{guide.explanation}</p>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  const guide = TASK_TYPE_PLAIN[taskType];
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/50 bg-muted/30 px-4 py-3">
      <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
      <div className="text-sm">
        <p className="font-semibold text-foreground">{guide.title}</p>
        <p className="mt-0.5 text-muted-foreground">{guide.explanation}</p>
        <p className="mt-1 text-xs italic text-muted-foreground/80">{guide.example}</p>
      </div>
    </div>
  );
}

export function MarketplaceItemExplainer({
  headline,
  whatItIs,
  goodFor,
}: {
  headline?: string;
  whatItIs: string;
  goodFor: string;
}) {
  return (
    <div className="mb-4 space-y-2 rounded-lg border border-border/40 bg-muted/30 p-3">
      {headline ? <p className="text-sm font-semibold text-foreground">{headline}</p> : null}
      <p className="text-xs leading-relaxed text-muted-foreground">{whatItIs}</p>
      <p className="text-xs text-muted-foreground">
        <span className="font-semibold text-foreground/80">Good for: </span>
        {goodFor}
      </p>
    </div>
  );
}
