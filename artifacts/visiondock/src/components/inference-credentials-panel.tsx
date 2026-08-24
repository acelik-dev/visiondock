import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { InferenceMeta } from "@/lib/inference-api";
import { Copy, Key, RefreshCw, Cloud } from "lucide-react";

type Props = {
  projectId: string | null;
  inference: InferenceMeta | null | undefined;
  onRotateKey?: () => Promise<void>;
  compact?: boolean;
};

function CopyField({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <div className="space-y-1">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="flex items-center gap-2 rounded-lg border border-border/60 bg-slate-900 px-3 py-2">
        <span className={`flex-1 truncate text-xs text-slate-200 ${mono ? "font-mono" : ""}`}>
          {value}
        </span>
        <button
          type="button"
          onClick={copy}
          className="shrink-0 text-muted-foreground/70 hover:text-white"
          title="Copy"
        >
          <Copy className="h-3.5 w-3.5" />
        </button>
      </div>
      {copied && <p className="text-[10px] text-emerald-600">Copied</p>}
    </div>
  );
}

export function InferenceCredentialsPanel({
  projectId,
  inference,
  onRotateKey,
  compact = false,
}: Props) {
  const [rotating, setRotating] = useState(false);

  if (!projectId) {
    return (
      <p className="text-sm text-muted-foreground">Select a project to view inference credentials.</p>
    );
  }

  const status = inference?.status ?? "not_deployed";

  if (status === "deploying") {
    return (
      <div className="rounded-lg border border-primary/20 bg-primary/8 px-4 py-3 text-sm text-primary flex items-center gap-2">
        <RefreshCw className="h-4 w-4 animate-spin" />
        Deploying Azure ML endpoint… this can take 10–20 minutes.
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        Inference deploy failed: {inference?.error || "Unknown error"}
      </div>
    );
  }

  if (status !== "deployed") {
    return (
      <p className="text-sm text-muted-foreground">
        {compact
          ? "Complete training to deploy an inference endpoint."
          : "Train a model first, then deploy from the Inference page or wait for auto-deploy after training."}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Cloud className="h-4 w-4 text-primary" />
        Cloud inference — {projectId}
      </div>

      {inference?.scoring_uri && (
        <CopyField label="REST endpoint (Azure ML)" value={inference.scoring_uri} />
      )}
      {inference?.aml_primary_key && (
        <CopyField label="Azure ML API key (Authorization: Bearer)" value={inference.aml_primary_key} />
      )}
      {inference?.api_key && (
        <CopyField label="VisionDock API key (edge / integrations)" value={inference.api_key} />
      )}

      {!compact && (
        <p className="text-[11px] text-muted-foreground border-t border-border/40 pt-3">
          Send JSON:{" "}
          <code className="text-foreground/80">{`{"image_base64": "...", "confidence": ${inference?.confidence_threshold ?? 0.5}}`}</code>
          {" "}with header{" "}
          <code className="text-foreground/80">Authorization: Bearer &lt;Azure ML key&gt;</code>
        </p>
      )}

      {onRotateKey && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={rotating}
          onClick={() => {
            setRotating(true);
            void onRotateKey().finally(() => setRotating(false));
          }}
        >
          <Key className="mr-1.5 h-3.5 w-3.5" />
          {rotating ? "Rotating…" : "Rotate VisionDock API key"}
        </Button>
      )}
    </div>
  );
}
