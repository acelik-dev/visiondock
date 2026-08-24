import { useEffect, useState } from "react";
import { fetchTrainingInfo, type TrainingInfo } from "@/lib/training-api";

export function useTrainingInfo(epochs = 100) {
  const [info, setInfo] = useState<TrainingInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchTrainingInfo(epochs)
      .then((data) => {
        if (!cancelled) setInfo(data);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Training info unavailable");
          setInfo(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [epochs]);

  return { info, loading, error, isAzure: info?.mode === "azure" };
}
