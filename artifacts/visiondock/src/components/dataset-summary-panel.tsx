import { AlertTriangle, CheckCircle2, Database } from "lucide-react";
import { friendlyValidationMessage } from "@/lib/dataset-templates";
import type { DatasetValidation } from "@/lib/projects-api";
import type { TaskType } from "@/lib/project-spec";
import { TASK_LABELS } from "@/lib/project-spec";

type Props = {
  taskType: TaskType;
  validated?: boolean;
  validation?: DatasetValidation | null;
  classCounts?: Record<string, number>;
  totalImages?: number;
};

export function DatasetSummaryPanel({
  taskType,
  validated,
  validation,
  classCounts = {},
  totalImages = 0,
}: Props) {
  const stats = validation?.stats ?? {};
  const errors = (validation?.errors ?? []).map(friendlyValidationMessage);
  const warnings = (validation?.warnings ?? []).map(friendlyValidationMessage);

  const imageCount =
    totalImages ||
    (typeof stats.image_count === "number" ? stats.image_count : 0) ||
    Object.values(classCounts).reduce((a, b) => a + b, 0);

  const labelDist = stats.label_distribution as Record<string, number> | undefined;
  const classStats = (stats.class_counts as Record<string, number>) || classCounts;
  const annotationCount = typeof stats.annotation_count === "number" ? stats.annotation_count : null;

  return (
    <div className="rounded-xl border border-border/50 bg-muted/40 p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Database className="h-4 w-4 text-primary" />
        <h5 className="text-sm font-semibold text-foreground/80">Your photos</h5>
        <span className="text-xs text-muted-foreground ml-1">({TASK_LABELS[taskType]})</span>
        {validated && (
          <span className="ml-auto text-xs font-medium text-emerald-600 bg-emerald-100 px-2 py-0.5 rounded-full">
            Ready
          </span>
        )}
        {!validated && imageCount > 0 && (
          <span className="ml-auto text-xs font-medium text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
            Not ready yet
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Photos" value={imageCount.toLocaleString()} />
        {taskType === "classification" && (
          <Stat
            label="Groups"
            value={String(Object.keys(classStats).length || stats.classes_with_data || "—")}
          />
        )}
        {taskType === "multi_label" && (
          <Stat label="Tags" value={String(stats.label_count ?? "—")} />
        )}
        {taskType === "regression" && (
          <>
            <Stat
              label="Number range"
              value={
                stats.target_min != null && stats.target_max != null
                  ? `${stats.target_min} – ${stats.target_max}`
                  : "—"
              }
            />
            <Stat label="Rows in list" value={String(stats.target_rows ?? "—")} />
          </>
        )}
        {(taskType === "object_detection" || taskType === "object_localization") && (
          <>
            <Stat label="Boxes found" value={annotationCount != null ? String(annotationCount) : "—"} />
            <Stat label="Object types" value={String(stats.class_count ?? "—")} />
          </>
        )}
      </div>

      {Object.keys(classStats).length > 0 && taskType === "classification" && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground mb-2">Photos per group</p>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {Object.entries(classStats).map(([cls, count]) => (
              <div key={cls} className="flex justify-between text-xs text-muted-foreground">
                <span>{cls}</span>
                <span>{count} photos</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {labelDist && Object.keys(labelDist).length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground mb-2">How often each tag appears</p>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {Object.entries(labelDist)
              .slice(0, 15)
              .map(([lbl, count]) => (
                <div key={lbl} className="flex justify-between text-xs text-muted-foreground">
                  <span>{lbl}</span>
                  <span>{count}</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {errors.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
          <div className="flex items-center gap-1.5 font-semibold mb-1">
            <AlertTriangle className="h-3.5 w-3.5" />
            Needs a fix
          </div>
          <ul className="list-disc pl-4 space-y-0.5">
            {errors.map((e: string, i: number) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <div className="flex items-center gap-1.5 font-semibold mb-1">
            <AlertTriangle className="h-3.5 w-3.5" />
            Heads-up
          </div>
          <ul className="list-disc pl-4 space-y-0.5">
            {warnings.map((w: string, i: number) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {!validated && !errors.length && imageCount === 0 && (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <CheckCircle2 className="h-3.5 w-3.5 text-muted-foreground/70" />
          Add your photos to see a summary here.
        </p>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-card border border-border/60 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground/70">{label}</p>
      <p className="text-sm font-semibold text-foreground/90">{value}</p>
    </div>
  );
}
