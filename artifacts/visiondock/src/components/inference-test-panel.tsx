import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { SpotlightCard } from "@/components/premium/spotlight-card";
import {
  buildAmlCurlCommand,
  buildProxyCurlCommand,
  predictInference,
  type InferenceMeta,
  type PredictResponse,
} from "@/lib/inference-api";
import { Copy, ImageIcon, Loader2, Play, Terminal, Upload, X } from "lucide-react";
import { useCredits } from "@/hooks/use-credits";
import { costLabel } from "@/lib/credits-api";

type Props = {
  projectId: string | null;
  inference: InferenceMeta | null | undefined;
  onNotify?: (message: string) => void;
};

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.split(",")[1] ?? "");
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function CopyBlock({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:text-primary"
        >
          <Copy className="h-3 w-3" />
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto rounded-lg border border-border/60 bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-200">
        {value}
      </pre>
    </div>
  );
}

function PredictionBars({ result }: { result: PredictResponse }) {
  if (result.kind === "regression" && result.regression) {
    const { target_name, target_unit, value } = result.regression;
    const unit = target_unit ? ` ${target_unit}` : "";
    return (
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-center">
        <p className="text-xs uppercase tracking-wide text-emerald-700">{target_name}</p>
        <p className="mt-1 text-2xl font-semibold text-emerald-900">
          {value.toFixed(3)}
          {unit}
        </p>
      </div>
    );
  }

  if (result.kind === "multi_label") {
    if (result.multi_labels.length === 0) {
      return <p className="text-sm text-muted-foreground">No labels above threshold.</p>;
    }
    return (
      <div className="space-y-3">
        {result.multi_labels.map((item, i) => (
          <div key={`${item.label}-${i}`} className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-foreground/90">{item.label}</span>
              <span className="font-mono text-muted-foreground">{(item.confidence * 100).toFixed(1)}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-violet-500 to-primary"
                initial={{ width: 0 }}
                animate={{ width: `${Math.min(100, item.confidence * 100)}%` }}
                transition={{ type: "spring", stiffness: 80, damping: 18, delay: i * 0.05 }}
              />
            </div>
          </div>
        ))}
      </div>
    );
  }

  const items = result.kind === "classification" ? result.predictions : result.detections;
  if (items.length === 0) return null;

  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={`${item.class_id}-${i}`} className="space-y-1">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-foreground/90">{item.class_name}</span>
            <span className="font-mono text-muted-foreground">{(item.confidence * 100).toFixed(1)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-primary to-cyan-500"
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(100, item.confidence * 100)}%` }}
              transition={{ type: "spring", stiffness: 80, damping: 18, delay: i * 0.05 }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function InferenceTestPanel({ projectId, inference, onNotify }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [imageBase64, setImageBase64] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PredictResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const { account, canAfford, cost } = useCredits();
  const predictCost = cost("inference_predict");

  const isDeployed = inference?.status === "deployed";
  const canRun = Boolean(projectId && isDeployed && imageFile && canAfford("inference_predict"));

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const setImage = async (file: File) => {
    if (!file.type.startsWith("image/")) {
      onNotify?.("Please select an image file");
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setImageFile(file);
    setPreviewUrl(URL.createObjectURL(file));
    setResult(null);
    setError(null);
    try {
      const b64 = await fileToBase64(file);
      setImageBase64(b64);
    } catch {
      setImageBase64("");
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void setImage(file);
    e.target.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void setImage(file);
  };

  const clearImage = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setImageFile(null);
    setPreviewUrl(null);
    setImageBase64("");
    setResult(null);
    setError(null);
  };

  const handleRun = async () => {
    if (!projectId || !imageFile) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const data = await predictInference(projectId, imageFile);
      setResult(data);
      if (data.kind === "classification" && data.top_class) {
        onNotify?.(
          `Top class: ${data.top_class.class_name} (${(data.top_class.confidence * 100).toFixed(0)}%)`,
        );
      } else if (data.kind === "multi_label") {
        onNotify?.(
          `${data.count} label${data.count === 1 ? "" : "s"} above threshold`,
        );
      } else if (data.kind === "regression" && data.regression) {
        const unit = data.regression.target_unit ? ` ${data.regression.target_unit}` : "";
        onNotify?.(`${data.regression.target_name}: ${data.regression.value.toFixed(3)}${unit}`);
      } else {
        onNotify?.(`Found ${data.count} detection${data.count === 1 ? "" : "s"}`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Inference failed";
      setError(msg);
      onNotify?.(msg);
    } finally {
      setRunning(false);
    }
  };

  if (!projectId) {
    return (
      <p className="text-sm text-muted-foreground">Select a project to test cloud inference.</p>
    );
  }

  if (!isDeployed) {
    return null;
  }

  const amlCurl = buildAmlCurlCommand(inference ?? {}, imageBase64);
  const proxyCurl = buildProxyCurlCommand(projectId);
  const topClass = result?.top_class;

  return (
    <SpotlightCard>
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-bold text-foreground">Test cloud inference</h3>
        <p className="text-sm text-muted-foreground">
          Upload an image and run image recognition against your deployed Azure ML endpoint.
        </p>
      </div>

      <motion.div
        role="button"
        tabIndex={0}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
        }}
        animate={{
          borderColor: dragOver ? "hsl(var(--primary))" : "hsl(var(--border))",
          scale: dragOver ? 1.01 : 1,
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 transition-colors ${
          dragOver ? "bg-primary/5" : "bg-muted/20 hover:bg-primary/5"
        }`}
      >
        {previewUrl ? (
          <div className="relative w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <img
              src={previewUrl}
              alt="Upload preview"
              className="max-h-48 w-full rounded-lg object-contain"
            />
            <button
              type="button"
              onClick={clearImage}
              className="absolute right-2 top-2 rounded-full bg-slate-900/70 p-1 text-white hover:bg-slate-900"
              title="Remove image"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <>
            <Upload className="mb-3 h-8 w-8 text-muted-foreground/70" />
            <p className="text-sm font-medium text-foreground/80">Drop an image here or click to browse</p>
            <p className="mt-1 text-xs text-muted-foreground">PNG, JPG, WEBP</p>
          </>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFileChange}
        />
      </motion.div>

      <Button
        onClick={() => void handleRun()}
        disabled={!canRun || running}
        className="w-full  disabled:opacity-50"
      >
        {running ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Running inference…
          </>
        ) : (
          <>
            <Play className="mr-2 h-4 w-4" />
            Run inference
          </>
        )}
      </Button>
      <p className="text-xs text-muted-foreground text-center -mt-1">
        Uses {costLabel(account?.costs, "inference_predict")}
        {` · balance ${(account?.balance ?? 0).toLocaleString()}`}
        {!canAfford("inference_predict")
          ? ` · need ${predictCost} more`
          : ""}
      </p>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {result && previewUrl && (
        <AnimatePresence>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          {result.kind === "classification" && topClass ? (
            <div className="rounded-lg border border-primary/20 bg-primary/8 px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-primary">
                Top prediction
              </p>
              <p className="mt-1 text-lg font-bold text-foreground">{topClass.class_name}</p>
              <p className="text-sm font-mono text-primary">
                {(topClass.confidence * 100).toFixed(1)}% confidence
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <ImageIcon className="h-4 w-4 text-primary" />
              {result.count} detection{result.count === 1 ? "" : "s"}
            </div>
          )}

          {previewUrl && result.kind === "classification" && (
            <img
              src={previewUrl}
              alt="Inference preview"
              className="max-h-64 w-full rounded-lg border border-border/60 object-contain bg-muted/40"
            />
          )}

          {result.predictions.length > 0 || result.detections.length > 0 ? (
            <>
              <PredictionBars result={result} />
              <div className="overflow-hidden rounded-lg border border-border/60">
                <table className="w-full text-left text-sm">
                  <thead className="bg-muted/40 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2">Class</th>
                      <th className="px-3 py-2">Confidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(result.kind === "classification" ? result.predictions : result.detections).map(
                      (item, i) => (
                        <tr key={i} className="text-foreground/80">
                          <td className="px-3 py-2 font-medium">{item.class_name}</td>
                          <td className="px-3 py-2 font-mono">{(item.confidence * 100).toFixed(1)}%</td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No predictions returned.</p>
          )}
        </motion.div>
        </AnimatePresence>
      )}

      <div className="space-y-4 border-t border-border/40 pt-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          cURL examples
        </div>
        <CopyBlock label="Direct Azure ML (Bearer key)" value={amlCurl} />
        <CopyBlock label="VisionDock proxy (multipart upload)" value={proxyCurl} />
        <p className="text-[11px] text-muted-foreground">
          Replace truncated base64 in the AML curl with your full encoded image, or use the proxy curl
          with an authenticated session cookie.
        </p>
      </div>
    </div>
    </SpotlightCard>
  );
}
