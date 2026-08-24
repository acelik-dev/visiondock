import type { ProjectSpec, TaskType } from "@/lib/project-spec";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Sparkles } from "lucide-react";

type Props = {
  config: ProjectSpec;
  onChange?: (next: ProjectSpec) => void;
  readOnly?: boolean;
  rationale?: string | null;
  tuning?: boolean;
};

const DETECTION_TASKS: TaskType[] = ["object_detection", "object_localization"];
const VISION_TASKS: TaskType[] = ["classification", "multi_label", "regression"];

export function ConfigPipelineEditor({
  config,
  onChange,
  readOnly = false,
  rationale,
  tuning = false,
}: Props) {
  const pre = config.preprocessing ?? {};
  const post = config.postprocessing ?? {};
  const train = config.training_config ?? {};
  const task = config.task_type ?? "classification";
  const isDetection = DETECTION_TASKS.includes(task);
  const isVision = VISION_TASKS.includes(task);
  const disabled = readOnly || tuning;

  const patchPre = (partial: Partial<NonNullable<ProjectSpec["preprocessing"]>>) => {
    if (disabled || !onChange) return;
    onChange({ ...config, preprocessing: { ...pre, ...partial } });
  };

  const patchPost = (partial: Partial<NonNullable<ProjectSpec["postprocessing"]>>) => {
    if (disabled || !onChange) return;
    onChange({ ...config, postprocessing: { ...post, ...partial } });
  };

  const patchTrain = (partial: Partial<NonNullable<ProjectSpec["training_config"]>>) => {
    if (disabled || !onChange) return;
    onChange({ ...config, training_config: { ...train, ...partial } });
  };

  return (
    <div className="space-y-4 border-t border-border/60 pt-4 mt-4">
      <div className="flex items-start gap-2 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2">
        <Sparkles className="h-4 w-4 shrink-0 text-violet-600 mt-0.5" />
        <div className="min-w-0">
          <p className="text-xs font-semibold text-violet-900">
            {tuning
              ? "Analyzing dataset images…"
              : readOnly
                ? "AI-configured from your dataset"
                : "Pipeline — review before training"}
          </p>
          {rationale && !tuning && (
            <p className="text-[11px] text-violet-800 mt-0.5">
              {rationale.replace(/\s+-\s+/g, " — ")}
            </p>
          )}
          {tuning && (
            <p className="text-[11px] text-violet-700 mt-0.5">
              Vision model is inspecting sample images to set training and inference options.
            </p>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-border/50 bg-card p-3 space-y-3 opacity-100">
        <p className="text-xs font-semibold text-foreground/80">Training</p>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-muted-foreground">
            Epochs
            <Input
              type="number"
              min={1}
              disabled={disabled}
              className="mt-1 h-8 text-sm bg-muted/40"
              value={train.epochs ?? (isDetection ? 100 : 30)}
              onChange={(e) => patchTrain({ epochs: parseInt(e.target.value, 10) || 30 })}
            />
          </label>
          <label className="text-xs text-muted-foreground">
            Batch size
            <Input
              type="number"
              min={1}
              disabled={disabled}
              className="mt-1 h-8 text-sm bg-muted/40"
              value={train.batch_size ?? 16}
              onChange={(e) => patchTrain({ batch_size: parseInt(e.target.value, 10) || 16 })}
            />
          </label>
          <label className="text-xs text-muted-foreground col-span-2">
            Image size
            <Input
              disabled={disabled}
              className="mt-1 h-8 text-sm bg-muted/40"
              value={train.image_size ?? (isDetection ? "640x640" : "224x224")}
              onChange={(e) => patchTrain({ image_size: e.target.value })}
            />
          </label>
        </div>
        {isVision && (
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch
                disabled={disabled}
                checked={train.augmentation !== false}
                onCheckedChange={(v) => patchTrain({ augmentation: v })}
              />
              RandAugment
            </label>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch
                disabled={disabled}
                checked={!!train.mixup}
                onCheckedChange={(v) => patchTrain({ mixup: v })}
              />
              Mixup
            </label>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch
                disabled={disabled}
                checked={!!train.cutmix}
                onCheckedChange={(v) => patchTrain({ cutmix: v })}
              />
              CutMix
            </label>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border/60 bg-muted/40 p-3 space-y-3">
        <p className="text-xs font-semibold text-foreground/80">Preprocessing</p>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-muted-foreground">
            Resize
            <Input
              disabled={disabled}
              className="mt-1 h-8 text-sm bg-card"
              value={pre.resize ?? ""}
              onChange={(e) => patchPre({ resize: e.target.value })}
            />
          </label>
          <div className="flex items-end gap-4 col-span-2 flex-wrap">
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch disabled={disabled} checked={!!pre.grayscale} onCheckedChange={(v) => patchPre({ grayscale: v })} />
              Grayscale
            </label>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch disabled={disabled} checked={!!pre.denoise} onCheckedChange={(v) => patchPre({ denoise: v })} />
              Denoise
            </label>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch
                disabled={disabled}
                checked={!!pre.contrast_enhancement}
                onCheckedChange={(v) => patchPre({ contrast_enhancement: v })}
              />
              Contrast boost
            </label>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch
                disabled={disabled}
                checked={pre.auto_orientation !== false}
                onCheckedChange={(v) => patchPre({ auto_orientation: v })}
              />
              Auto-orient
            </label>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-border/60 bg-muted/40 p-3 space-y-3">
        <p className="text-xs font-semibold text-foreground/80">Postprocessing</p>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-muted-foreground">
            Confidence
            <Input
              type="text"
              inputMode="decimal"
              disabled={disabled}
              className="mt-1 h-8 text-sm bg-card"
              value={String(post.confidence_threshold ?? 0.5)}
              onChange={(e) => {
                const raw = e.target.value.trim().replace(",", ".");
                if (raw === "" || raw === "." || raw === "0.") {
                  patchPost({ confidence_threshold: raw === "" ? 0 : Number(raw) || 0 });
                  return;
                }
                const n = Number(raw);
                if (!Number.isNaN(n)) {
                  patchPost({ confidence_threshold: Math.min(1, Math.max(0, n)) });
                }
              }}
            />
          </label>
          {isDetection && (
            <label className="text-xs text-muted-foreground">
              NMS IoU
              <Input
                type="text"
                inputMode="decimal"
                disabled={disabled}
                className="mt-1 h-8 text-sm bg-card"
                value={String(post.nms_iou_threshold ?? 0.5)}
                onChange={(e) => {
                  const raw = e.target.value.trim().replace(",", ".");
                  const n = Number(raw);
                  if (!Number.isNaN(n)) {
                    patchPost({ nms_iou_threshold: Math.min(1, Math.max(0, n)) });
                  }
                }}
              />
            </label>
          )}
        </div>
        <div className="flex flex-wrap gap-4">
          {isDetection && (
            <>
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <Switch disabled={disabled} checked={!!post.tta} onCheckedChange={(v) => patchPost({ tta: v })} />
                TTA
              </label>
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <Switch disabled={disabled} checked={!!post.sahi} onCheckedChange={(v) => patchPost({ sahi: v })} />
                SAHI
              </label>
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <Switch
                  disabled={disabled}
                  checked={!!post.ensemble}
                  onCheckedChange={(v) => patchPost({ ensemble: v })}
                />
                Ensemble
              </label>
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <Switch
                  disabled={disabled}
                  checked={post.auto_tune_thresholds !== false}
                  onCheckedChange={(v) => patchPost({ auto_tune_thresholds: v })}
                />
                Auto-tune
              </label>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
