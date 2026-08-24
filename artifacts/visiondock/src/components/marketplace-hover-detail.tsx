import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { TaskType } from "@/lib/project-spec";
import {
  fetchDatasetPreviews,
  fetchModelPreviews,
  marketplaceDatasetPreviewUrl,
  taskTypeLabel,
} from "@/lib/marketplace-api";
import { getDatasetCopy, getModelCopy } from "@/lib/marketplace-copy";
import {
  getActiveMarketplaceHoverKey,
  setActiveMarketplaceHoverKey,
  subscribeMarketplaceHover,
} from "@/lib/marketplace-hover-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Info } from "lucide-react";

type PreviewCache = {
  previews: string[];
  classes: string[];
  previewDatasetId?: string | null;
  imageCount?: number;
  classCount?: number;
  license?: string;
  format?: string;
};

const previewCache = new Map<string, PreviewCache>();

type MarketplaceHoverDetailProps = {
  kind: "dataset" | "model";
  itemId: string;
  name: string;
  taskType: TaskType;
  classes?: string[] | null;
  imageCount?: number | null;
  classCount?: number | null;
  license?: string;
  format?: string;
  children: ReactNode;
};

function cacheKey(kind: string, itemId: string) {
  return `${kind}:${itemId}`;
}

function safeClasses(value: string[] | null | undefined): string[] {
  return Array.isArray(value) ? value : [];
}

export function MarketplaceHoverDetail({
  kind,
  itemId,
  name,
  taskType,
  classes,
  imageCount,
  classCount,
  license,
  format,
  children,
}: MarketplaceHoverDetailProps) {
  const hoverKey = cacheKey(kind, itemId);
  const anchorRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const openTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [, bump] = useState(0);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<PreviewCache | null>(
    () => previewCache.get(hoverKey) ?? null,
  );

  const open = getActiveMarketplaceHoverKey() === hoverKey;

  useEffect(() => subscribeMarketplaceHover(() => bump((n) => n + 1)), []);

  const copy = kind === "dataset" ? getDatasetCopy(itemId, name) : getModelCopy(itemId, name);
  const initialClasses = safeClasses(classes);

  const clearTimers = () => {
    if (openTimer.current) {
      clearTimeout(openTimer.current);
      openTimer.current = null;
    }
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  const updatePosition = useCallback(() => {
    const el = anchorRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const panelWidth = 420;
    const gap = 12;
    let left = rect.right + gap;
    if (left + panelWidth > window.innerWidth - 16) {
      left = Math.max(16, rect.left - panelWidth - gap);
    }
    const top = Math.min(Math.max(16, rect.top), window.innerHeight - 320);
    setPosition({ top, left });
  }, []);

  const loadPreviews = useCallback(async () => {
    const cached = previewCache.get(hoverKey);
    if (cached) {
      setDetail(cached);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data =
        kind === "dataset"
          ? await fetchDatasetPreviews(itemId)
          : await fetchModelPreviews(itemId);
      const next: PreviewCache = {
        previews: Array.isArray(data.previews) ? data.previews : [],
        classes: safeClasses(data.classes),
        previewDatasetId:
          kind === "dataset" ? itemId : data.preview_dataset_id ?? null,
        imageCount: data.image_count ?? undefined,
        classCount: data.class_count ?? safeClasses(data.classes).length,
        license: data.license,
        format: data.format,
      };
      previewCache.set(hoverKey, next);
      setDetail(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load preview");
    } finally {
      setLoading(false);
    }
  }, [hoverKey, kind, itemId]);

  useEffect(() => {
    if (!open) return;
    updatePosition();
    void loadPreviews();
    const onScroll = () => updatePosition();
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open, updatePosition, loadPreviews]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (anchorRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      if (getActiveMarketplaceHoverKey() === hoverKey) {
        setActiveMarketplaceHoverKey(null);
      }
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    return () => document.removeEventListener("pointerdown", onPointerDown, true);
  }, [open, hoverKey]);

  const scheduleOpen = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    openTimer.current = setTimeout(() => {
      updatePosition();
      setActiveMarketplaceHoverKey(hoverKey);
    }, 180);
  };

  const scheduleClose = () => {
    if (openTimer.current) {
      clearTimeout(openTimer.current);
      openTimer.current = null;
    }
    closeTimer.current = setTimeout(() => {
      if (getActiveMarketplaceHoverKey() === hoverKey) {
        setActiveMarketplaceHoverKey(null);
      }
    }, 200);
  };

  const keepOpen = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    if (getActiveMarketplaceHoverKey() !== hoverKey) {
      setActiveMarketplaceHoverKey(hoverKey);
    }
  };

  useEffect(() => () => clearTimers(), []);

  const previewDatasetId = detail?.previewDatasetId ?? (kind === "dataset" ? itemId : null);
  const previewFiles = detail?.previews ?? [];
  const allClasses = detail?.classes?.length ? detail.classes : initialClasses;
  const showClasses = allClasses.length > 0 && taskType !== "regression";

  const panel = open ? (
    <div
      ref={panelRef}
      className="fixed z-[100] w-[min(420px,calc(100vw-2rem))] vd-panel shadow-xl"
      style={{ top: position.top, left: position.left }}
      onMouseEnter={keepOpen}
      onMouseLeave={scheduleClose}
      role="tooltip"
    >
      <div className="p-4 space-y-3 max-h-[min(70vh,560px)] overflow-y-auto">
        <div>
          <p className="text-sm font-semibold text-foreground">{name}</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">{taskTypeLabel(taskType)}</p>
          {copy.detailBlurb ? (
            <p className="text-xs text-muted-foreground mt-2 leading-relaxed">{copy.detailBlurb}</p>
          ) : null}
        </div>

        {loading ? (
          <div className="grid grid-cols-4 gap-1.5">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="aspect-square rounded-md" />
            ))}
          </div>
        ) : error ? (
          <p className="text-xs text-red-600 bg-red-50 rounded-md px-3 py-2">{error}</p>
        ) : previewFiles.length > 0 && previewDatasetId ? (
          <div className="grid grid-cols-4 gap-1.5">
            {previewFiles.slice(0, 8).map((filename) => (
              <div
                key={filename}
                className="aspect-square rounded-md overflow-hidden bg-muted/60 border border-border/60"
              >
                <img
                  src={marketplaceDatasetPreviewUrl(previewDatasetId, filename)}
                  alt=""
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground bg-muted/40 rounded-md px-3 py-2">
            No sample images available yet.
          </p>
        )}

        <div className="grid grid-cols-2 gap-2 text-xs">
          {kind === "dataset" && (detail?.imageCount ?? imageCount) != null ? (
            <div className="bg-muted/40 rounded-md px-2.5 py-2">
              <span className="text-muted-foreground block text-[10px] uppercase font-semibold">Photos</span>
              <span className="font-semibold text-foreground">
                {(detail?.imageCount ?? imageCount ?? 0).toLocaleString()}
              </span>
            </div>
          ) : null}
          {showClasses ? (
            <div className="bg-primary/8 rounded-md px-2.5 py-2">
              <span className="text-primary block text-[10px] uppercase font-semibold">Categories</span>
              <span className="font-semibold text-primary">
                {detail?.classCount ?? classCount ?? allClasses.length}
              </span>
            </div>
          ) : null}
          {(detail?.license ?? license) ? (
            <div className="bg-muted/40 rounded-md px-2.5 py-2">
              <span className="text-muted-foreground block text-[10px] uppercase font-semibold">License</span>
              <span className="font-semibold text-foreground">{detail?.license ?? license}</span>
            </div>
          ) : null}
          {(detail?.format ?? format) ? (
            <div className="bg-muted/40 rounded-md px-2.5 py-2">
              <span className="text-muted-foreground block text-[10px] uppercase font-semibold">Format</span>
              <span className="font-semibold text-foreground truncate block">
                {(detail?.format ?? format)?.replace(/_/g, " ")}
              </span>
            </div>
          ) : null}
        </div>

        {showClasses ? (
          <div>
            <p className="text-[11px] font-semibold text-muted-foreground mb-1.5">
              {copy.classHint ?? "All categories:"}
            </p>
            <div className="max-h-36 overflow-y-auto rounded-md border border-border/60 bg-muted/40 p-2">
              <div className="flex flex-wrap gap-1">
                {allClasses.map((cls) => (
                  <span
                    key={cls}
                    className="inline-flex rounded-md bg-card border border-border/60 px-2 py-0.5 text-[11px] text-foreground/80"
                  >
                    {cls.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ) : taskType === "regression" ? (
          <p className="text-xs text-muted-foreground">{copy.classHint ?? "Predicts a numeric value per image."}</p>
        ) : null}

        <p className="text-[11px] text-muted-foreground leading-relaxed border-t border-border/40 pt-2">
          {copy.goodFor}
        </p>
      </div>
    </div>
  ) : null;

  return (
    <div
      ref={anchorRef}
      className="relative h-full"
      onMouseEnter={scheduleOpen}
      onMouseLeave={scheduleClose}
    >
      {children}
      <span
        className="pointer-events-none absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full bg-card/95 text-muted-foreground/70 border border-border/60 shadow-sm"
        title="More details"
        aria-hidden
      >
        <Info className="h-3.5 w-3.5" />
      </span>
      {typeof document !== "undefined" && panel ? createPortal(panel, document.body) : null}
    </div>
  );
}
