import { InferenceCredentialsPanel } from "@/components/inference-credentials-panel";
import type { InferenceMeta } from "@/lib/inference-api";
import type { ProjectSpec, TaskType } from "@/lib/project-spec";
import { DATASET_FORMAT_HINTS, TASK_LABELS } from "@/lib/project-spec";
import { sanitizeLabels } from "@/lib/label-sanitize";

const TASK_PLAIN: Record<TaskType, string> = {
  classification: "Put each photo in one group — separate upload per class",
  multi_label: "Give each photo one or more tags",
  regression: "Predict a number for each photo",
  object_localization: "Find one object in each photo",
  object_detection: "Find several objects in each photo",
};

type Props = {
  config: ProjectSpec;
  projectId?: string | null;
  inference?: InferenceMeta | null;
  onRotateApiKey?: () => Promise<void>;
};

export function ConfigSummaryPanel({
  config,
  projectId = null,
  inference = null,
  onRotateApiKey,
}: Props) {
  const classes = sanitizeLabels(config.classes ?? []);
  const taskType = config.task_type ?? "classification";

  return (
    <div className="flex h-full min-h-0 flex-col gap-5">
      <p className="max-w-none text-sm leading-relaxed text-muted-foreground">
        {config.description ||
          "We'll train a model based on your conversation. You upload pre-labeled data in the next step."}
      </p>

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <div className="rounded-xl border border-primary/15 bg-primary/8 px-4 py-4">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
            Task type
          </p>
          <p className="text-base font-medium text-foreground">{TASK_LABELS[taskType]}</p>
          <p className="mt-1.5 text-sm text-muted-foreground">{TASK_PLAIN[taskType]}</p>
          {config.recommended_model && (
            <p className="mt-2 text-sm text-muted-foreground">
              Suggested approach: {config.recommended_model}
            </p>
          )}
        </div>

        <div className="rounded-xl border border-border/60 bg-muted/40 px-4 py-4 xl:col-span-2">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Expected dataset format
          </p>
          <p className="text-sm leading-relaxed text-foreground/80">{DATASET_FORMAT_HINTS[taskType]}</p>
        </div>
      </div>

      {taskType === "regression" && (config.target_name || config.target_unit) && (
        <div className="text-xs text-muted-foreground">
          <span className="font-medium">Target:</span> {config.target_name || "target"}
          {config.target_unit ? ` (${config.target_unit})` : ""}
        </div>
      )}

      {classes.length > 0 && taskType !== "regression" && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground mb-2">
            {taskType === "multi_label" ? "Labels" : "Classes"} ({classes.length})
          </p>
          <div className="flex flex-wrap gap-2">
            {classes.map((cls) => (
              <span
                key={cls}
                className="rounded-full border border-border/60 bg-card px-3 py-1.5 text-sm font-medium text-foreground/80"
              >
                {cls.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
      )}

      {(inference?.status === "deployed" || projectId) && (
        <div className="border-t border-border/40 pt-4 space-y-2">
          <p className="text-xs font-semibold text-muted-foreground">Inference & API keys</p>
          <InferenceCredentialsPanel
            projectId={projectId}
            inference={inference}
            onRotateKey={onRotateApiKey}
            compact
          />
        </div>
      )}

      <p className="text-[11px] text-muted-foreground/70 border-t border-border/40 pt-3">
        VisionDock does not label data — bring your pre-labeled dataset in Step 2, then start training.
      </p>
    </div>
  );
}
