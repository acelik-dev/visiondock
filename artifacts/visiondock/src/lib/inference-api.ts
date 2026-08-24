import { resolveApiBase } from "@/lib/api-base";
import { parseJsonResponse } from "@/lib/projects-api";

const API_BASE = resolveApiBase();

export type InferenceMeta = {
  status?: "not_deployed" | "deploying" | "deployed" | "failed";
  job_id?: string;
  task_type?: "classification" | "multi_label" | "regression" | "object_detection" | string;
  endpoint_name?: string;
  scoring_uri?: string;
  swagger_uri?: string;
  aml_primary_key?: string;
  api_key?: string;
  api_key_created_at?: string;
  confidence_threshold?: number;
  nms_iou_threshold?: number;
  deployed_at?: string;
  error?: string;
  model_name?: string;
  model_version?: string;
};

export type InferenceStatusResponse = {
  project_id: string;
  project_status?: string;
  training_status?: string;
  training_job_id?: string;
  inference: InferenceMeta;
  model?: Record<string, unknown>;
  can_deploy: boolean;
};

export async function fetchInferenceStatus(projectId: string): Promise<InferenceStatusResponse> {
  const res = await fetch(`${API_BASE}/api/inference/${projectId}`, { credentials: "include" });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : "Failed to load inference status");
  }
  return data as InferenceStatusResponse;
}

export async function deployInference(projectId: string) {
  const res = await fetch(`${API_BASE}/api/inference/${projectId}/deploy`, {
    method: "POST",
    credentials: "include",
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const detail = data.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
          ? String((detail as { message?: string }).message)
          : "Deploy failed";
    throw new Error(msg);
  }
  return data;
}

export async function rotateInferenceApiKey(projectId: string) {
  const res = await fetch(`${API_BASE}/api/inference/${projectId}/api-key`, {
    method: "POST",
    credentials: "include",
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : "API key rotation failed");
  }
  return data as { success: boolean; api_key: string; inference: InferenceMeta };
}

export function edgeBundleUrl(projectId: string): string {
  return `${API_BASE}/api/inference/${projectId}/edge-bundle`;
}

export type ClassPrediction = {
  class_id: number;
  class_name: string;
  confidence: number;
};

export type Detection = {
  class_id: number;
  class_name: string;
  confidence: number;
  bbox_xyxy: [number, number, number, number];
};

export type ClassificationPredictResponse = {
  predictions: ClassPrediction[];
  top_class: ClassPrediction | null;
  count: number;
};

export type DetectionPredictResponse = {
  detections: Detection[];
  count: number;
};

export type MultiLabelPrediction = {
  label: string;
  confidence: number;
};

export type RegressionPredictResponse = {
  target_name: string;
  target_unit: string;
  value: number;
  prediction: number;
};

export type PredictResponse = {
  kind: "classification" | "detection" | "multi_label" | "regression";
  predictions: ClassPrediction[];
  top_class: ClassPrediction | null;
  detections: Detection[];
  multi_labels: MultiLabelPrediction[];
  regression: RegressionPredictResponse | null;
  count: number;
};

function isClassificationPayload(data: Record<string, unknown>): boolean {
  return Array.isArray(data.predictions) || data.top_class != null;
}

export function normalizePredictResponse(data: Record<string, unknown>): PredictResponse {
  const taskType = String(data.task_type ?? "");

  if (taskType === "regression" || data.value != null) {
    const value = Number(data.value ?? data.prediction ?? 0);
    return {
      kind: "regression",
      predictions: [],
      top_class: null,
      detections: [],
      multi_labels: [],
      regression: {
        target_name: String(data.target_name ?? "target"),
        target_unit: String(data.target_unit ?? ""),
        value,
        prediction: Number(data.prediction ?? value),
      },
      count: 1,
    };
  }

  if (taskType === "multi_label" || Array.isArray(data.labels)) {
    const multi_labels = (data.labels as MultiLabelPrediction[]) ?? [];
    return {
      kind: "multi_label",
      predictions: [],
      top_class: null,
      detections: [],
      multi_labels,
      regression: null,
      count: typeof data.count === "number" ? data.count : multi_labels.length,
    };
  }

  if (isClassificationPayload(data)) {
    const predictions = (data.predictions as ClassPrediction[]) ?? [];
    const top_class = (data.top_class as ClassPrediction | null) ?? predictions[0] ?? null;
    return {
      kind: "classification",
      predictions,
      top_class,
      detections: [],
      multi_labels: [],
      regression: null,
      count: typeof data.count === "number" ? data.count : predictions.length,
    };
  }

  const detections = (data.detections as Detection[]) ?? [];
  return {
    kind: "detection",
    predictions: [],
    top_class: null,
    detections,
    multi_labels: [],
    regression: null,
    count: typeof data.count === "number" ? data.count : detections.length,
  };
}

export async function predictInference(
  projectId: string,
  file: File,
  topK = 5,
): Promise<PredictResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/inference/${projectId}/predict`, {
    method: "POST",
    body: form,
    credentials: "include",
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const detail = data.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
          ? String((detail as { message?: string }).message)
          : "Inference failed";
    throw new Error(msg);
  }
  if (data.credits && typeof data.credits === "object") {
    const { announceCreditSpend } = await import("@/hooks/use-credits");
    const { toast } = await import("sonner");
    announceCreditSpend(
      data.credits as { balance?: number; debited?: number },
      (msg) => toast(msg),
    );
  }
  return normalizePredictResponse(data as Record<string, unknown>);
}

export function buildAmlCurlCommand(
  inference: InferenceMeta,
  imageBase64Preview?: string,
): string {
  const uri = inference.scoring_uri ?? "https://<scoring-uri>";
  const key = inference.aml_primary_key ?? "<aml-primary-key>";
  const b64 =
    imageBase64Preview && imageBase64Preview.length > 0
      ? `${imageBase64Preview.slice(0, 48)}…`
      : "<base64-encoded-image>";
  const isClassification = inference.task_type === "classification";
  const isMultiLabel = inference.task_type === "multi_label";
  const isRegression = inference.task_type === "regression";
  const body = isRegression
    ? JSON.stringify({ image_base64: b64 })
    : isMultiLabel
      ? JSON.stringify({ image_base64: b64, confidence: inference.confidence_threshold ?? 0.5 })
      : isClassification
        ? JSON.stringify({ image_base64: b64, top_k: 5 })
        : JSON.stringify({ image_base64: b64, confidence: inference.confidence_threshold ?? 0.5 });
  return [
    `curl -X POST '${uri}' \\`,
    `  -H 'Content-Type: application/json' \\`,
    `  -H 'Authorization: Bearer ${key}' \\`,
    `  -d '${body}'`,
  ].join("\n");
}

export function buildProxyCurlCommand(projectId: string): string {
  const base = API_BASE || "https://visiondock-api.azurewebsites.net";
  return [
    `curl -X POST '${base}/api/inference/${projectId}/predict' \\`,
    `  -b 'session=<your-session-cookie>' \\`,
    `  -F 'file=@/path/to/image.jpg'`,
  ].join("\n");
}
